"""Fixed intake membership, live review counts and one local notice per batch phase."""
from contextlib import closing
from email.message import EmailMessage
import json
from typing import Literal
from uuid import UUID, uuid4

from fastapi import HTTPException, Request
from pydantic import BaseModel, Field

from backend.outcomes import local_smtp
from backend.review_events import protect_event


class BatchMembers(BaseModel):
    run_ids: list[UUID] = Field(min_length=1, max_length=500)


class IntakeBatches:
    def __init__(self, connect, sender=local_smtp):
        self.connect, self.sender = connect, sender

    def create(self, body):
        members = sorted(set(str(value) for value in body.run_ids))
        encoded = json.dumps(members)
        with closing(self.connect()) as db:
            db.execute('BEGIN IMMEDIATE')
            for run_id in members:
                row = db.execute('SELECT result_json FROM intake_runs WHERE run_id=?', (run_id,)).fetchone()
                if not row:
                    raise HTTPException(404, 'Intake run not found.')
                if json.loads(row['result_json'])['outcome'] == 'continue':
                    raise HTTPException(409, 'Finish processing every attachment before waiting for review.')
            row = db.execute('SELECT batch_id FROM intake_batches WHERE run_ids_json=?', (encoded,)).fetchone()
            batch_id = row['batch_id'] if row else str(uuid4())
            if not row:
                db.execute('INSERT INTO intake_batches(batch_id,run_ids_json) VALUES(?,?)', (batch_id, encoded))
            db.commit()
        return self.read(batch_id)

    def read(self, batch_id):
        with closing(self.connect()) as db:
            db.execute('BEGIN')
            batch = db.execute('SELECT * FROM intake_batches WHERE batch_id=?', (batch_id,)).fetchone()
            if not batch:
                raise HTTPException(404, 'Intake batch not found.')
            runs = [json.loads(db.execute('SELECT result_json FROM intake_runs WHERE run_id=?', (run_id,)).fetchone()[0])
                    for run_id in json.loads(batch['run_ids_json'])]
            records, events = {}, []
            counts = dict(approved=0, rejected=0, pending=0, unresolved=0)
            for run in runs:
                invoice_id = run.get('invoice_id')
                if not invoice_id or invoice_id in records or run['outcome'] in ('failed', 'skipped'):
                    continue
                task = db.execute('SELECT * FROM review_tasks WHERE invoice_id=?', (invoice_id,)).fetchone()
                status = task['status'] if task else 'unresolved'
                if status not in counts:
                    status = 'unresolved'
                counts[status] += 1
                records[invoice_id] = {'invoice_id': invoice_id, 'status': status,
                    'review_url': 'http://127.0.0.1:8000/reviews/' + invoice_id}
                if task and status in ('approved', 'rejected'):
                    event = db.execute('SELECT event_id FROM review_events WHERE invoice_id=? AND review_revision=? AND event_type=?',
                                       (invoice_id, task['current_revision'], status)).fetchone()
                    if event:
                        events.append(event['event_id'])
            notices = {row['phase']: dict(row) for row in db.execute('SELECT * FROM intake_batch_notices WHERE batch_id=?', (batch_id,))}
        invoice_ids = {run['invoice_id'] for run in runs if run.get('invoice_id')}
        new_ids = {run['invoice_id'] for run in runs if run.get('new_invoice') and run.get('invoice_id')}
        return {'batch_id': batch_id, 'source_batches': sorted({r['source']['batch_id'] for r in runs if r['source'].get('batch_id')}),
                'attachments': len(runs), 'unique_invoices': len(invoice_ids), 'new_invoices': len(new_ids),
                'reused_invoices': len(invoice_ids - new_ids), **counts,
                'failed_items': sum(r['outcome'] == 'failed' for r in runs),
                'skipped_items': sum(r['outcome'] == 'skipped' for r in runs),
                'complete': not counts['pending'] and not counts['unresolved'],
                'reviews': list(records.values()), 'event_ids': events, 'notices': notices,
                'export_url': 'http://127.0.0.1:8000/exports'}

    def notify(self, batch_id, phase):
        state = self.read(batch_id)
        if phase == 'summary' and not state['complete']:
            raise HTTPException(409, 'The batch still has pending or unresolved reviews.')
        if phase == 'pending' and not state['pending']:
            return state
        with closing(self.connect()) as db:
            db.execute('BEGIN IMMEDIATE')
            notice = db.execute('SELECT * FROM intake_batch_notices WHERE batch_id=? AND phase=?', (batch_id, phase)).fetchone()
            if notice:
                if notice['status'] != 'sent':
                    raise HTTPException(409, 'Batch notice failed or delivery is uncertain. Inspect Mailpit and the saved notice; do not resend automatically.')
                return self.read(batch_id)
            message_id = f'<ap-intake-{batch_id}-{phase}@example.invalid>'
            db.execute("INSERT INTO intake_batch_notices(batch_id,phase,status,message_id,snapshot_json) VALUES(?,?,'sending',?,?)",
                       (batch_id, phase, message_id, json.dumps(state)))
            db.commit()
        message = EmailMessage()
        message['From'], message['To'] = 'ap-results@example.invalid', 'reviewer@example.invalid'
        message['Message-ID'] = message_id
        label = f"{state['pending']} invoices need review" if phase == 'pending' else 'Batch processing complete'
        message['Subject'] = f'[AP Batch] {label} — {batch_id}'
        lines = [f'Intake batch: {batch_id}',
                 f"New invoice records: {state['new_invoices']}; reused records: {state['reused_invoices']}.",
                 f"Approved: {state['approved']}; rejected: {state['rejected']}; pending: {state['pending']}.",
                 f"Processing failures: {state['failed_items']}; skipped attachments: {state['skipped_items']}."]
        if phase == 'pending':
            lines += ['Compare the original, save changes, then approve or reject.']
            lines += [row['review_url'] for row in state['reviews'] if row['status'] == 'pending']
        lines += [f"Export register: {state['export_url']}",
                  'Approved invoices are already selectable. Select rows to create Excel when needed.',
                  'Local demo only. No payment or accounting submission. Counts apply only to this intake batch.']
        message.set_content('\n'.join(lines))
        status, error = self.sender(message)
        with closing(self.connect()) as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('UPDATE intake_batch_notices SET status=?,error_code=? WHERE batch_id=? AND phase=?',
                       (status, error, batch_id, phase))
            if status == 'sent' and phase == 'summary':
                for event_id in state['event_ids']:
                    db.execute("UPDATE review_events SET status='processed',processed_at=COALESCE(processed_at,strftime('%Y-%m-%dT%H:%M:%fZ','now')),last_error=NULL WHERE event_id=?", (event_id,))
            db.commit()
        if status != 'sent':
            raise HTTPException(503, 'Batch notification was not confirmed. Inspect the saved notice before recovery.')
        return self.read(batch_id)


def register_intake_batches(app, connect):
    with closing(connect()) as db:
        db.executescript('''CREATE TABLE IF NOT EXISTS intake_batches (
            batch_id TEXT PRIMARY KEY, run_ids_json TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
        ); CREATE TABLE IF NOT EXISTS intake_batch_notices (
            batch_id TEXT NOT NULL REFERENCES intake_batches, phase TEXT NOT NULL,
            status TEXT NOT NULL, message_id TEXT NOT NULL, snapshot_json TEXT NOT NULL,
            error_code TEXT, PRIMARY KEY(batch_id,phase)
        );''')
    service = IntakeBatches(connect)

    @app.post('/api/ap/intake-batches')
    def create(body: BatchMembers, request: Request):
        protect_event(request)
        return service.create(body)

    @app.get('/api/ap/intake-batches/{batch_id}')
    def read(batch_id: UUID):
        return service.read(str(batch_id))

    @app.post('/api/ap/intake-batches/{batch_id}/notify/{phase}')
    def notify(batch_id: UUID, phase: Literal['pending', 'summary'], request: Request):
        protect_event(request)
        return service.notify(str(batch_id), phase)
