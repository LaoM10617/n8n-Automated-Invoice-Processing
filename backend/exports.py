"""Snapshot-only Excel exports with durable identity, bounded retries and atomic files."""
from contextlib import closing
from datetime import datetime, timezone, timedelta
import json
import os
from pathlib import Path
import sqlite3
from uuid import UUID, uuid4
from zipfile import BadZipFile
from openpyxl.utils.exceptions import IllegalCharacterError

from fastapi import HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict

from backend.invoice_xlsx import MAPPING_VERSION, create_xlsx, verify_xlsx
from backend.review_events import ReviewEvents, protect_event
from backend.reviews import protect_write

MAX_ATTEMPTS = 5
LEASE_SECONDS = 60
XLSX_TYPE = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'


class ExportRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    event_id: UUID


class Exports:
    table = 'exports'
    directory = 'exports'
    route = '/api/ap/exports'

    def __init__(self, connect, data_dir):
        self.connect = connect
        self.root = Path(data_dir).resolve()
        self.events = ReviewEvents(connect)

    def path(self, row):
        name = str(UUID(row['export_id'])) + '.xlsx'
        expected = self.root / self.directory / name
        if expected.resolve() != expected or (row['file_path'] and row['file_path'] != self.directory + '/' + name):
            raise ValueError('UNSAFE_EXPORT_PATH')
        return expected

    def context(self, db, row):
        event, task, snapshot = self.events.load(db, row['event_id'])
        if event['event_type'] != 'approved' or row['invoice_id'] != event['invoice_id'] or row['review_revision'] != event['review_revision']:
            raise HTTPException(409, 'Export requires the current approved snapshot.')
        return dict(task), json.loads(snapshot['fields_json'])

    def load(self, db, export_id):
        row = db.execute(f'SELECT * FROM {self.table} WHERE export_id=?', (export_id,)).fetchone()
        if not row:
            raise HTTPException(404, 'Export not found.')
        row = dict(row)
        task, fields = self.context(db, row)
        return row, task, fields

    def build(self, row, task, fields):
        return create_xlsx(fields, task, row)

    def verify(self, data, row, task, fields):
        return verify_xlsx(data, fields, task, row)

    def before_claim(self, db, row):
        pass

    def check_file(self, row, task, fields):
        path = self.path(row)
        if not path.is_file():
            raise ValueError('EXPORT_FILE_MISSING')
        if path.stat().st_size > 16_000_000:
            raise ValueError('INVALID_WORKBOOK')
        data = path.read_bytes()
        import hashlib
        if row['file_sha256'] and hashlib.sha256(data).hexdigest() != row['file_sha256']:
            raise ValueError('EXPORT_HASH_MISMATCH')
        try:
            digest = self.verify(data, row, task, fields)
        except Exception:
            raise ValueError('INVALID_WORKBOOK') from None
        return data, digest

    def describe(self, row, task, fields):
        result = {**row, 'max_attempts': MAX_ATTEMPTS, 'download_url': None, 'file_health': 'not_ready'}
        if row['status'] == 'completed':
            try:
                self.check_file(row, task, fields)
                result.update(file_health='verified', download_url=f"{self.route}/{row['export_id']}/files/xlsx")
            except (OSError, ValueError, BadZipFile, KeyError):
                result['file_health'] = 'missing_or_invalid'
        return result

    def read(self, export_id):
        with closing(self.connect()) as db:
            db.execute('BEGIN')
            return self.describe(*self.load(db, export_id))

    def download(self, export_id):
        with closing(self.connect()) as db:
            db.execute('BEGIN')
            row, task, fields = self.load(db, export_id)
            if row['status'] != 'completed' or not row['file_sha256']:
                raise HTTPException(409, 'Export is not complete. Generate or retry explicitly.')
            try:
                data, _ = self.check_file(row, task, fields)
                return data
            except (OSError, ValueError, BadZipFile, KeyError):
                raise HTTPException(409, 'Export file is missing or invalid. Retry the same event explicitly.') from None

    def write_file(self, path, data):
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix('.tmp')
        if temporary.is_symlink():
            raise ValueError('UNSAFE_EXPORT_PATH')
        try:
            with temporary.open('wb') as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
            if os.name != 'nt':
                directory = os.open(path.parent, os.O_RDONLY)
                try:
                    os.fsync(directory)
                finally:
                    os.close(directory)
        finally:
            if temporary.exists():
                temporary.unlink()

    def complete(self, db, row, digest):
        db.execute(f"""UPDATE {self.table} SET status='completed',file_path=?,file_sha256=?,last_error=NULL,
                   updated_at=? WHERE export_id=?""",
                   (self.directory + '/' + row['export_id'] + '.xlsx', digest, datetime.now(timezone.utc).isoformat(), row['export_id']))

    def create(self, event_id):
        with closing(self.connect()) as db:
            db.execute('BEGIN IMMEDIATE')
            event, _, _ = self.events.load(db, event_id)
            if event['event_type'] != 'approved':
                raise HTTPException(409, 'Only an approved decision can be exported.')
            # The unique key excludes mapping_version; a deployment cannot create a second export.
            db.execute('''INSERT INTO exports(export_id,event_id,invoice_id,review_revision,mapping_version)
                       VALUES(?,?,?,?,?) ON CONFLICT(invoice_id,review_revision,target) DO NOTHING''',
                       (str(uuid4()), event_id, event['invoice_id'], event['review_revision'], MAPPING_VERSION))
            row = dict(db.execute("SELECT * FROM exports WHERE invoice_id=? AND review_revision=? AND target='excel'",
                                  (event['invoice_id'], event['review_revision'])).fetchone())
            db.commit()
        return self.generate(row['export_id'])

    def generate(self, export_id):
        now = datetime.now(timezone.utc)
        with closing(self.connect()) as db:
            db.execute('BEGIN IMMEDIATE')
            row, task, fields = self.load(db, export_id)
            current = self.describe(row, task, fields)
            if current['download_url']:
                db.commit()
                return current
            if row['status'] == 'writing' and datetime.fromisoformat(row['updated_at']) > now - timedelta(seconds=LEASE_SECONDS):
                raise HTTPException(409, 'Export is being written. Retry after the 60-second lease if interrupted.')
            if row['attempts'] >= MAX_ATTEMPTS:
                raise HTTPException(409, 'Export attempt limit reached. Inspect the saved export before operator recovery.')
            self.before_claim(db, row)
            row.update(attempts=row['attempts'] + 1, status='writing', updated_at=now.isoformat())
            db.execute(f"UPDATE {self.table} SET status='writing',attempts=?,updated_at=?,last_error=NULL WHERE export_id=?",
                       (row['attempts'], row['updated_at'], row['export_id']))
            db.commit()  # Export identity and attempt survive file/commit interruption.
        try:
            with closing(self.connect()) as db:
                # Hold the write lock during this small file operation to fence off an expired writer.
                db.execute('BEGIN IMMEDIATE')
                latest, task, fields = self.load(db, row['export_id'])
                if latest['attempts'] != row['attempts'] or latest['status'] != 'writing':
                    raise HTTPException(409, 'A newer export attempt owns this record.')
                path = self.path(row)
                try:
                    _, digest = self.check_file(row, task, fields)
                except (OSError, ValueError, BadZipFile, KeyError):
                    data = self.build(row, task, fields)
                    digest = self.verify(data, row, task, fields)
                    if row['file_sha256'] and digest != row['file_sha256']:
                        raise ValueError('RECOVERY_HASH_MISMATCH')
                    self.write_file(path, data)
                    _, digest = self.check_file(row, task, fields)
                self.complete(db, row, digest)
                db.commit()
        except (OSError, ValueError, ArithmeticError, IllegalCharacterError, BadZipFile, KeyError, sqlite3.Error) as exc:
            code = str(exc) if isinstance(exc, ValueError) and str(exc).isupper() and len(str(exc)) < 80 else 'EXPORT_WRITE_OR_VERIFY_FAILED'
            with closing(self.connect()) as db:
                db.execute(f"UPDATE {self.table} SET status='failed',last_error=?,updated_at=? WHERE export_id=? AND attempts=? AND status='writing'",
                           (code, datetime.now(timezone.utc).isoformat(), row['export_id'], row['attempts']))
                db.commit()
            raise HTTPException(503, {'export_id': row['export_id'], 'error': code, 'message': 'Approval is retained. Retry the same event explicitly.'}) from None
        return self.read(row['export_id'])


def register_exports(app, connect, root):
    service = Exports(connect, root)

    @app.post('/api/ap/exports')
    def create(body: ExportRequest, request: Request):
        if request.headers.get('x-ap-event-token') is not None:
            protect_event(request)
        else:
            protect_write(request)
        return service.create(str(body.event_id))

    @app.get('/api/ap/exports/{export_id}')
    def read(export_id: UUID):
        return service.read(str(export_id))

    @app.get('/api/ap/exports/{export_id}/files/xlsx')
    def download(export_id: UUID):
        return Response(service.download(str(export_id)), media_type=XLSX_TYPE,
                        headers={'Content-Disposition': f'attachment; filename="invoice-{export_id}.xlsx"', 'Cache-Control': 'no-store'})

    return service
