"""Local AP intake service. Extraction and review are not implemented yet."""

import hashlib
from contextlib import closing
import io
import json
import os
from pathlib import Path
import sqlite3
from typing import Annotated, Literal
from uuid import uuid4

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from PIL import Image, UnidentifiedImageError
from pypdf import PdfReader

MAX_BYTES = 20 * 1024 * 1024


def inspect_document(data: bytes) -> tuple[str, dict]:
    if data.startswith(b'%PDF-'):
        try:
            reader = PdfReader(io.BytesIO(data))
            if reader.is_encrypted or not reader.pages:
                raise ValueError('Encrypted or empty PDF')
            if len(reader.pages) > 50:
                raise ValueError('PDF exceeds 50 pages')
            counts = [len((page.extract_text() or '').strip()) for page in reader.pages]
        except Exception as exc:
            raise HTTPException(422, 'Unreadable, encrypted, empty or oversized PDF') from exc
        return 'application/pdf', {
            'page_count': len(counts), 'page_text_characters': counts,
            'ocr_required': any(count == 0 for count in counts),
            'text_quality_assessed': False,
        }
    try:
        with Image.open(io.BytesIO(data)) as image:
            if image.format not in ('JPEG', 'PNG'):
                raise HTTPException(415, 'Only PDF, JPEG and PNG are supported')
            media_type = Image.MIME[image.format]
            image.verify()
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as exc:
        raise HTTPException(422, 'Invalid or unsupported image') from exc
    return media_type, {
        'page_count': 1, 'page_text_characters': [0],
        'ocr_required': True, 'text_quality_assessed': False,
    }


def create_app(data_dir: Path | None = None) -> FastAPI:
    root = Path(data_dir or os.environ.get('AP_DATA_DIR', 'data/ap')).resolve()
    originals = root / 'originals'
    originals.mkdir(parents=True, exist_ok=True)
    database = root / 'invoices.sqlite3'

    def connect():
        db = sqlite3.connect(database, timeout=30)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys = ON')
        return db

    with closing(connect()) as db:
        db.executescript('''
            CREATE TABLE IF NOT EXISTS invoices (
                invoice_id TEXT PRIMARY KEY, sha256 TEXT UNIQUE NOT NULL,
                stored_name TEXT NOT NULL, media_type TEXT NOT NULL,
                inspection TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
            );
            CREATE TABLE IF NOT EXISTS receipts (
                receipt_id TEXT PRIMARY KEY, invoice_id TEXT NOT NULL REFERENCES invoices,
                source_type TEXT NOT NULL, source_namespace TEXT NOT NULL,
                source_id TEXT NOT NULL, attachment_id TEXT NOT NULL,
                original_filename TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
                UNIQUE(source_type, source_namespace, source_id, attachment_id)
            );
        ''')

    app = FastAPI(title='AP Intake Demo', version='0.1.0')

    def invoice_row(invoice_id):
        with closing(connect()) as db:
            row = db.execute('SELECT * FROM invoices WHERE invoice_id=?', (invoice_id,)).fetchone()
        if row is None:
            raise HTTPException(404, 'Invoice not found')
        return row

    @app.get('/health')
    def health():
        with closing(connect()) as db:
            db.execute('SELECT 1').fetchone()
        return {'status': 'ok', 'capabilities': {'intake': True, 'extraction': False, 'ocr': False, 'review': False}}

    @app.post('/api/ap/intakes')
    def intake(
        file: Annotated[UploadFile, File()],
        source_type: Annotated[Literal['upload', 'email'], Form()],
        source_namespace: Annotated[str, Form(min_length=1, max_length=200)],
        source_id: Annotated[str, Form(min_length=1, max_length=200)],
        attachment_id: Annotated[str, Form(min_length=1, max_length=200)],
    ):
        key = (source_type, source_namespace, source_id, attachment_id)
        if any(not value.strip() for value in key):
            raise HTTPException(422, 'Source identifiers must not be blank')
        data = file.file.read(MAX_BYTES + 1)
        if not data or len(data) > MAX_BYTES:
            raise HTTPException(413, 'File must contain 1 byte to 20 MiB')
        digest = hashlib.sha256(data).hexdigest()
        media_type, inspection = inspect_document(data)
        db = connect()
        new_path = None
        try:
            db.execute('BEGIN IMMEDIATE')
            previous = db.execute('''SELECT r.*, i.sha256 FROM receipts r
                JOIN invoices i USING(invoice_id) WHERE source_type=? AND source_namespace=?
                AND source_id=? AND attachment_id=?''', key).fetchone()
            if previous:
                if previous['sha256'] != digest:
                    raise HTTPException(409, 'Source key already belongs to different file bytes')
                invoice_id, receipt_id = previous['invoice_id'], previous['receipt_id']
                delivery_duplicate, content_duplicate = True, True
            else:
                existing = db.execute('SELECT invoice_id FROM invoices WHERE sha256=?', (digest,)).fetchone()
                content_duplicate = existing is not None
                invoice_id = existing['invoice_id'] if existing else str(uuid4())
                if not existing:
                    extension = {'application/pdf': '.pdf', 'image/png': '.png', 'image/jpeg': '.jpg'}[media_type]
                    stored_name = invoice_id + extension
                    new_path = originals / stored_name
                    with new_path.open('xb') as output:
                        output.write(data)
                        output.flush()
                        os.fsync(output.fileno())
                    db.execute('INSERT INTO invoices(invoice_id,sha256,stored_name,media_type,inspection) VALUES(?,?,?,?,?)',
                               (invoice_id, digest, stored_name, media_type, json.dumps(inspection)))
                receipt_id = str(uuid4())
                db.execute('''INSERT INTO receipts(receipt_id,invoice_id,source_type,source_namespace,
                    source_id,attachment_id,original_filename) VALUES(?,?,?,?,?,?,?)''',
                    (receipt_id, invoice_id, *key, file.filename or 'unnamed'))
                delivery_duplicate = False
            db.commit()
        except Exception:
            db.rollback()
            if new_path is not None:
                new_path.unlink(missing_ok=True)
            raise
        finally:
            db.close()
        return JSONResponse(status_code=200 if delivery_duplicate else 201, content={
            'receipt_id': receipt_id, 'invoice_id': invoice_id, 'direction': 'AP',
            'delivery_duplicate': delivery_duplicate, 'content_duplicate': content_duplicate,
            'business_duplicate_status': 'not_checked', 'processing_status': 'received',
            'review_status': 'not_created', 'review_url': None, 'is_mock': False,
            'sha256': digest, 'inspection': inspection,
            'original_ref': f'/api/ap/invoices/{invoice_id}/original',
        })

    @app.get('/api/ap/invoices/{invoice_id}')
    def get_invoice(invoice_id: str):
        row = invoice_row(invoice_id)
        with closing(connect()) as db:
            receipts = [dict(r) for r in db.execute('SELECT * FROM receipts WHERE invoice_id=? ORDER BY created_at,receipt_id', (invoice_id,))]
        return {
            'invoice_id': invoice_id, 'direction': 'AP', 'sha256': row['sha256'],
            'media_type': row['media_type'], 'created_at': row['created_at'],
            'inspection': json.loads(row['inspection']), 'receipts': receipts,
            'processing_status': 'received', 'business_duplicate_status': 'not_checked',
            'review_status': 'not_created', 'review_url': None,
            'extracted_fields': None, 'validation_issues': None,
            'original_ref': f'/api/ap/invoices/{invoice_id}/original', 'is_mock': False,
        }

    @app.get('/api/ap/invoices/{invoice_id}/original')
    def original(invoice_id: str):
        row = invoice_row(invoice_id)
        path = originals / row['stored_name']
        if not path.is_file():
            raise HTTPException(503, 'Stored original is unavailable')
        return FileResponse(path, media_type=row['media_type'], headers={'X-Content-Type-Options': 'nosniff'})

    @app.post('/api/ap/invoices/{invoice_id}/process')
    def process(invoice_id: str):
        invoice_row(invoice_id)
        raise HTTPException(501, {'code': 'PROCESSING_NOT_IMPLEMENTED',
                                  'message': 'OCR, extraction and business validation are not connected.'})

    return app
