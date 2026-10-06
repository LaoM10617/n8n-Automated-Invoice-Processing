"""Local AP intake and processing service. Review remains a separate step."""

import hashlib
from contextlib import closing
import io
import json
import os
from pathlib import Path
import sqlite3
import subprocess
from typing import Annotated, Literal
from uuid import uuid4

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse, HTMLResponse, Response
from PIL import Image, UnidentifiedImageError
from pypdf import PdfReader

from backend.document_text import ProcessingError, QUALITY_VERSION, ocr_available, read_pages
from backend.extraction import extract_fields, grounded_fields, model_configured
from backend.validation import duplicate_candidates, validate
from backend.review_page import render_review

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
            CREATE TABLE IF NOT EXISTS processing_attempts (
                attempt_id INTEGER PRIMARY KEY AUTOINCREMENT,
                invoice_id TEXT NOT NULL REFERENCES invoices,
                status TEXT NOT NULL, result_json TEXT, error_code TEXT, error_message TEXT,
                created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
            );
            CREATE TABLE IF NOT EXISTS review_tasks (
                review_id TEXT PRIMARY KEY,
                invoice_id TEXT UNIQUE NOT NULL REFERENCES invoices,
                status TEXT NOT NULL DEFAULT 'pending' CHECK(status='pending'),
                created_attempt_id INTEGER NOT NULL REFERENCES processing_attempts(attempt_id),
                created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
            );
        ''')
        # This demo runs one application worker. Preserve interrupted attempts for audit.
        db.execute("UPDATE processing_attempts SET status='failed', error_code='PROCESS_INTERRUPTED', error_message='Application restarted during processing.' WHERE status='processing'")
        db.commit()

    app = FastAPI(title='AP Intake Demo', version='0.1.0')

    def review_info(task):
        return {'review_id': task['review_id'] if task else None,
                'review_status': task['status'] if task else 'not_created',
                'review_url': os.environ.get('AP_PUBLIC_BASE_URL', 'http://127.0.0.1:8000').rstrip('/') + '/reviews/' + task['invoice_id'] if task else None}

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
        return {'status': 'ok', 'capabilities': {'intake': True, 'extraction': model_configured(), 'ocr': ocr_available(), 'review': True, 'review_decisions': False}}

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
        current = get_invoice(invoice_id)
        return JSONResponse(status_code=200 if delivery_duplicate else 201, content={
            'receipt_id': receipt_id, 'invoice_id': invoice_id, 'direction': 'AP',
            'delivery_duplicate': delivery_duplicate, 'content_duplicate': content_duplicate,
            'business_duplicate_status': current['business_duplicate_status'], 'processing_status': current['processing_status'],
            **{k: current[k] for k in ('review_id', 'review_status', 'review_url')}, 'is_mock': False,
            'sha256': digest, 'inspection': inspection,
            'original_ref': f'/api/ap/invoices/{invoice_id}/original',
        })

    @app.get('/api/ap/invoices/{invoice_id}')
    def get_invoice(invoice_id: str):
        row = invoice_row(invoice_id)
        with closing(connect()) as db:
            receipts = [dict(r) for r in db.execute('SELECT * FROM receipts WHERE invoice_id=? ORDER BY created_at,receipt_id', (invoice_id,))]
            attempt = db.execute('SELECT * FROM processing_attempts WHERE invoice_id=? ORDER BY attempt_id DESC LIMIT 1', (invoice_id,)).fetchone()
            task = db.execute('SELECT * FROM review_tasks WHERE invoice_id=?', (invoice_id,)).fetchone()
            others = db.execute("SELECT invoice_id,result_json FROM processing_attempts WHERE status='processed' AND invoice_id<>? AND attempt_id IN (SELECT MAX(attempt_id) FROM processing_attempts GROUP BY invoice_id)", (invoice_id,)).fetchall()
        result = json.loads(attempt['result_json']) if attempt and attempt['result_json'] else {}
        fields = result.get('fields')
        duplicate_status, candidates = duplicate_candidates(fields, [(r['invoice_id'], json.loads(r['result_json'])['fields']) for r in others]) if fields else ('not_checked', [])
        issues = list(result.get('validation_issues', []))
        if fields is not None:
            if duplicate_status == 'candidate':
                issues.append({'code': 'BUSINESS_DUPLICATE_CANDIDATE', 'field': 'invoice_number', 'message': 'Potential duplicate; preserve both records for manual review.'})
            elif duplicate_status == 'not_evaluable':
                issues.append({'code': 'DUPLICATE_CHECK_INCOMPLETE', 'field': 'supplier', 'message': 'Reliable supplier identity or invoice number is missing.'})
        return {
            'invoice_id': invoice_id, 'direction': 'AP', 'sha256': row['sha256'],
            'media_type': row['media_type'], 'created_at': row['created_at'],
            'inspection': json.loads(row['inspection']), 'receipts': receipts,
            'processing_status': attempt['status'] if attempt else 'received', 'business_duplicate_status': duplicate_status,
            **review_info(task),
            'extracted_fields': fields, 'validation_issues': issues if fields is not None else None,
            'duplicate_candidates': candidates, 'processing_result': result or None,
            'processing_error': {'code': attempt['error_code'], 'message': attempt['error_message']} if attempt and attempt['error_code'] else None,
            'processing_attempt_id': attempt['attempt_id'] if attempt else None,
            'review_required': True if fields is not None else None,
            'original_ref': f'/api/ap/invoices/{invoice_id}/original', 'is_mock': False,
        }

    @app.get('/api/ap/invoices/{invoice_id}/original')
    def original(invoice_id: str):
        row = invoice_row(invoice_id)
        path = originals / row['stored_name']
        if not path.is_file():
            raise HTTPException(503, 'Stored original is unavailable')
        return FileResponse(path, media_type=row['media_type'], headers={'X-Content-Type-Options': 'nosniff'})

    @app.get('/api/ap/invoices/{invoice_id}/preview/{page}')
    def preview_page(invoice_id: str, page: int):
        row = invoice_row(invoice_id)
        if row['media_type'] != 'application/pdf' or not 1 <= page <= json.loads(row['inspection'])['page_count']:
            raise HTTPException(404, 'PDF page not found')
        try:
            output = subprocess.run(['pdftoppm', '-f', str(page), '-l', str(page),
                                     '-singlefile', '-scale-to', '1600', '-png',
                                     str(originals / row['stored_name'])],
                                    check=True, capture_output=True, timeout=30).stdout
        except (OSError, subprocess.SubprocessError) as exc:
            raise HTTPException(503, 'Preview unavailable; open the original document.') from exc
        return Response(output, media_type='image/png', headers={'Cache-Control': 'private, max-age=3600', 'X-Content-Type-Options': 'nosniff'})

    @app.post('/api/ap/invoices/{invoice_id}/review-task')
    def create_review_task(invoice_id: str):
        invoice_row(invoice_id)
        with closing(connect()) as db:
            db.execute('BEGIN IMMEDIATE')
            attempt = db.execute('SELECT * FROM processing_attempts WHERE invoice_id=? ORDER BY attempt_id DESC LIMIT 1', (invoice_id,)).fetchone()
            if not attempt or attempt['status'] != 'processed' or not json.loads(attempt['result_json'] or '{}').get('fields'):
                raise HTTPException(409, 'Complete processing before creating a review task.')
            task = db.execute('SELECT * FROM review_tasks WHERE invoice_id=?', (invoice_id,)).fetchone()
            created = task is None
            if created:
                db.execute('INSERT INTO review_tasks(review_id,invoice_id,created_attempt_id) VALUES(?,?,?)', (str(uuid4()), invoice_id, attempt['attempt_id']))
                task = db.execute('SELECT * FROM review_tasks WHERE invoice_id=?', (invoice_id,)).fetchone()
            db.commit()
        return JSONResponse(status_code=201 if created else 200, content={
            'invoice_id': invoice_id, 'direction': 'AP', **review_info(task),
            'created_at': task['created_at'], 'created_attempt_id': task['created_attempt_id'], 'is_mock': False})

    @app.get('/reviews/{invoice_id}', response_class=HTMLResponse)
    def review_page(invoice_id: str):
        with closing(connect()) as db:
            task = db.execute('SELECT * FROM review_tasks WHERE invoice_id=?', (invoice_id,)).fetchone()
        if task is None:
            raise HTTPException(404, 'Review task not found')
        return HTMLResponse(render_review(get_invoice(invoice_id), dict(task)), headers={
            'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff',
            'Content-Security-Policy': "default-src 'none'; style-src 'unsafe-inline'; img-src 'self'; frame-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'self'"})

    @app.post('/api/ap/invoices/{invoice_id}/process')
    def process(invoice_id: str):
        row = invoice_row(invoice_id)
        with closing(connect()) as db:
            db.execute('BEGIN IMMEDIATE')
            previous = db.execute('SELECT * FROM processing_attempts WHERE invoice_id=? ORDER BY attempt_id DESC LIMIT 1', (invoice_id,)).fetchone()
            cached_config = json.loads(previous['result_json']) if previous and previous['result_json'] else {}
            if (previous and previous['status'] == 'processed'
                    and cached_config.get('pipeline_version') == 'step4-layout-v1'
                    and cached_config.get('model') == os.environ.get('AP_LLM_MODEL')
                    and cached_config.get('model_base_url') == os.environ.get('AP_LLM_BASE_URL')):
                db.rollback()
                return get_invoice(invoice_id)
            if previous and previous['status'] == 'processing':
                db.rollback()
                raise HTTPException(409, 'Invoice processing is already in progress.')
            cursor = db.execute("INSERT INTO processing_attempts(invoice_id,status) VALUES(?,'processing')", (invoice_id,))
            attempt_id = cursor.lastrowid
            db.commit()
        result = {'pipeline_version': 'step4-layout-v1', 'model': os.environ.get('AP_LLM_MODEL'),
                  'model_base_url': os.environ.get('AP_LLM_BASE_URL'), 'pages': []}
        try:
            cached = json.loads(previous['result_json']) if previous and previous['result_json'] else {}
            cached_pages = cached.get('pages') or []
            result['pages'] = cached_pages if cached_pages and all(p.get('quality_rule') == QUALITY_VERSION for p in cached_pages) else read_pages(originals / row['stored_name'], row['media_type'])
            result['raw_extraction'] = extract_fields(result['pages'])
            grounded, evidence_issues = grounded_fields(result['raw_extraction'], result['pages'])
            result['fields'], issues, result['arithmetic_check'] = validate(grounded)
            issues.extend(evidence_issues)
            for uncertainty in result['raw_extraction']['uncertainties']:
                issues.append({'code': 'EXTRACTION_UNCERTAINTY', 'field': 'document', 'message': uncertainty})
            for page in result['pages']:
                if page['ocr_confidence'] is not None and page['ocr_confidence'] < 80:
                    issues.append({'code': 'OCR_LOW_CONFIDENCE', 'field': f"page_{page['page']}", 'message': 'OCR word confidence is low; compare with the original.'})
            result['validation_issues'] = issues
            with closing(connect()) as db:
                db.execute("UPDATE processing_attempts SET status='processed',result_json=? WHERE attempt_id=?", (json.dumps(result), attempt_id))
                db.commit()
        except Exception as exc:
            error = exc if isinstance(exc, ProcessingError) else ProcessingError('PROCESSING_FAILED', 'Processing failed; inspect backend diagnostics.')
            with closing(connect()) as db:
                db.execute("UPDATE processing_attempts SET status='failed',result_json=?,error_code=?,error_message=? WHERE attempt_id=?", (json.dumps(result), error.code, str(error), attempt_id))
                db.commit()
            status = 429 if error.code in ('MODEL_LOCAL_RATE_LIMIT', 'MODEL_RATE_LIMITED') else (503 if error.code in ('MODEL_NOT_CONFIGURED', 'OCR_DEPENDENCY_MISSING', 'ORIGINAL_UNAVAILABLE') else 502)
            raise HTTPException(status,
                                {'code': error.code, 'message': str(error), 'invoice_id': invoice_id}) from exc
        return get_invoice(invoice_id)

    return app
