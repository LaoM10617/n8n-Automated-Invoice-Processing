"""Approved snapshots form the register; explicit selections become immutable Excel batches."""
from contextlib import closing
from datetime import date
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import BackgroundTasks, HTTPException, Query, Request
from fastapi.responses import FileResponse, HTMLResponse, Response
from pydantic import BaseModel, ConfigDict, Field

from backend.exports import Exports, XLSX_TYPE
from backend.invoice_xlsx import MAPPING_VERSION, create_rows_xlsx, verify_rows_xlsx
from backend.reviews import protect_write
from backend.export_register_page import PAGE

MAX_BATCH_ROWS = 500


class BatchRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    event_ids: list[UUID] = Field(min_length=1, max_length=MAX_BATCH_ROWS)
    only_unexported: bool = True


def already_exported(db, invoice_id, revision, excluding=''):
    # A successful generation remains historical even while its file is being repaired.
    return bool(db.execute("""SELECT 1 FROM exports WHERE invoice_id=? AND review_revision=? AND (status='completed' OR file_sha256 IS NOT NULL)
        UNION ALL SELECT 1 FROM export_batch_items i JOIN export_batches b USING(export_id)
        WHERE i.invoice_id=? AND i.review_revision=? AND (b.status='completed' OR b.file_sha256 IS NOT NULL) AND b.export_id!=? LIMIT 1""",
        (invoice_id, revision, invoice_id, revision, excluding)).fetchone())


class ExportBatches(Exports):
    table = 'export_batches'
    directory = 'exports/batches'
    route = '/api/ap/export-batches'

    def context(self, db, row):
        items = db.execute('SELECT * FROM export_batch_items WHERE export_id=? ORDER BY ordinal', (row['export_id'],)).fetchall()
        if not items or len(items) > MAX_BATCH_ROWS:
            raise HTTPException(409, 'Export membership is missing or invalid.')
        records = []
        for item in items:
            task, fields = super().context(db, dict(item))
            records.append((fields, task, {**row, 'invoice_id': item['invoice_id'], 'review_revision': item['review_revision']}))
        identity = hashlib.sha256('\n'.join(sorted(item['event_id'] for item in items)).encode()).hexdigest()
        if identity != row['selection_hash']:
            raise HTTPException(409, 'Export membership does not match its saved identity.')
        return records, None

    def build(self, row, records, unused):
        return create_rows_xlsx(records)

    def verify(self, data, row, records, unused):
        return verify_rows_xlsx(data, records)

    def describe(self, row, records, unused):
        return {**super().describe(row, records, unused), 'row_count': len(records),
                'members': [{'invoice_id': export['invoice_id'], 'review_revision': export['review_revision']}
                            for _, _, export in records]}

    def check_unexported(self, db, items, excluding=''):
        for item in items:
            if already_exported(db, item['invoice_id'], item['review_revision'], excluding):
                raise HTTPException(409, 'A selected record was already exported. Refresh the register or select All approved.')
            active = db.execute("""SELECT b.export_id FROM export_batch_items i JOIN export_batches b USING(export_id)
                WHERE i.invoice_id=? AND i.review_revision=? AND b.export_id!=? AND b.status IN ('pending','writing') LIMIT 1""",
                (item['invoice_id'], item['review_revision'], excluding)).fetchone()
            if active:
                raise HTTPException(409, 'A selected record belongs to an unfinished export. Recover it from export history first.')

    def before_claim(self, db, row):
        # Recovery of a previously completed file is always allowed under the same identity.
        if row['only_unexported'] and not row['file_sha256']:
            items = db.execute('SELECT * FROM export_batch_items WHERE export_id=?', (row['export_id'],)).fetchall()
            self.check_unexported(db, items, row['export_id'])

    def create_batch(self, body):
        event_ids = sorted(str(event_id) for event_id in body.event_ids)
        if len(set(event_ids)) != len(event_ids):
            raise HTTPException(422, 'Select each approved record only once.')
        identity = hashlib.sha256('\n'.join(event_ids).encode()).hexdigest()
        with closing(self.connect()) as db:
            db.execute('BEGIN IMMEDIATE')
            existing = db.execute('SELECT export_id FROM export_batches WHERE selection_hash=?', (identity,)).fetchone()
            if existing:
                export_id = existing['export_id']
            else:
                items = []
                for event_id in event_ids:
                    event, _, _ = self.events.load(db, event_id)
                    if event['event_type'] != 'approved':
                        raise HTTPException(409, 'Only approved snapshots can enter an export batch.')
                    items.append(event)
                if body.only_unexported:
                    self.check_unexported(db, items)
                export_id = str(uuid4())
                db.execute('INSERT INTO export_batches(export_id,selection_hash,mapping_version,only_unexported) VALUES(?,?,?,?)',
                           (export_id, identity, MAPPING_VERSION, int(body.only_unexported)))
                for ordinal, event in enumerate(items):
                    db.execute('INSERT INTO export_batch_items(export_id,ordinal,event_id,invoice_id,review_revision) VALUES(?,?,?,?,?)',
                               (export_id, ordinal, event['event_id'], event['invoice_id'], event['review_revision']))
            db.commit()
        return self.generate(export_id)

    def preview(self, date_from=None, date_to=None, supplier='', currency='', only_unexported=True):
        if date_from and date_to and date_from > date_to:
            raise HTTPException(422, 'Start date must be on or before end date.')
        rows, totals = [], {}
        with closing(self.connect()) as db:
            db.execute('BEGIN')
            # No copied register or backfill: the approval transaction already saves these rows.
            events = db.execute("""SELECT e.event_id FROM review_events e JOIN review_tasks t USING(review_id)
                WHERE e.event_type='approved' AND t.status='approved' AND e.review_revision=t.current_revision
                ORDER BY t.decided_at,e.event_id""").fetchall()
            for reference in events:
                event, task, snapshot = self.events.load(db, reference['event_id'])
                fields = json.loads(snapshot['fields_json'])
                invoice_date = date.fromisoformat(fields['invoice_date'])
                if ((date_from and invoice_date < date_from) or (date_to and invoice_date > date_to)
                        or supplier.casefold() not in fields['supplier_name'].casefold()
                        or (currency and fields['currency'] != currency.upper())):
                    continue
                exported = already_exported(db, event['invoice_id'], event['review_revision'])
                if only_unexported and exported:
                    continue
                rows.append({**fields, 'event_id': event['event_id'], 'invoice_id': event['invoice_id'],
                             'review_revision': event['review_revision'], 'approved_at': task['decided_at'],
                             'approval_method': task['approval_method'], 'exported': exported})
                unit = fields['currency']
                totals[unit] = totals.get(unit, Decimal(0)) + Decimal(fields['total_amount'])
        return {'rows': rows, 'count': len(rows), 'totals_by_currency': {k: str(v) for k, v in sorted(totals.items())},
                'max_batch_rows': MAX_BATCH_ROWS}

    def history(self):
        with closing(self.connect()) as db:
            return [dict(row) for row in db.execute('''SELECT b.*,COUNT(i.event_id) AS row_count
                FROM export_batches b JOIN export_batch_items i USING(export_id)
                GROUP BY b.export_id ORDER BY b.created_at DESC,b.export_id DESC LIMIT 30''')]


def register_export_register(app, connect, root, on_export=None):
    service = ExportBatches(connect, root)

    @app.get('/exports', response_class=HTMLResponse)
    def page():
        return HTMLResponse(PAGE, headers={'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff',
            'Content-Security-Policy': "default-src 'none'; script-src 'self'; connect-src 'self'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'; frame-ancestors 'self'"})

    @app.get('/static/export_register.js')
    def script():
        return FileResponse(Path(__file__).with_name('export_register.js'), media_type='text/javascript', headers={'Cache-Control': 'no-store'})

    @app.get('/api/ap/export-register')
    def preview(date_from: date | None = None, date_to: date | None = None,
                supplier: str = Query('', max_length=200), currency: str = Query('', max_length=3), only_unexported: bool = True):
        return service.preview(date_from, date_to, supplier, currency, only_unexported)

    @app.get('/api/ap/export-batches')
    def history():
        return service.history()

    @app.post('/api/ap/export-batches')
    def create(body: BatchRequest, request: Request, background: BackgroundTasks):
        protect_write(request)
        result = service.create_batch(body)
        if on_export and os.environ.get('AP_OUTCOME_AUTODISPATCH') == '1':
            background.add_task(on_export, result['export_id'])
        return result

    @app.get('/api/ap/export-batches/{export_id}')
    def read(export_id: UUID):
        return service.read(str(export_id))

    @app.post('/api/ap/export-batches/{export_id}/retry')
    def retry(export_id: UUID, request: Request, background: BackgroundTasks):
        protect_write(request)
        result = service.generate(str(export_id))
        if on_export and os.environ.get('AP_OUTCOME_AUTODISPATCH') == '1':
            background.add_task(on_export, result['export_id'])
        return result

    @app.get('/api/ap/export-batches/{export_id}/files/xlsx')
    def download(export_id: UUID):
        return Response(service.download(str(export_id)), media_type=XLSX_TYPE,
                        headers={'Content-Disposition': f'attachment; filename="invoices-{export_id}.xlsx"', 'Cache-Control': 'no-store'})

    return service
