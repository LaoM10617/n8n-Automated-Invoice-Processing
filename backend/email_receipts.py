"""Source-level email attachment outcomes for batch reconciliation."""
from contextlib import closing
from typing import Literal
from fastapi import HTTPException
from pydantic import BaseModel, Field


class EmailOutcome(BaseModel):
    source_namespace: str = Field(min_length=1, max_length=200)
    source_id: str = Field(min_length=1, max_length=200)
    attachment_id: str = Field(min_length=1, max_length=200)
    batch_id: str = Field(pattern=r'^[A-Za-z0-9_-]{1,80}$')
    case_id: str = Field(pattern=r'^[A-Za-z0-9_-]{1,80}$')
    status: Literal['skipped', 'intake_failed', 'processing_failed', 'review_failed', 'review_ready']
    reason_code: str = Field(max_length=100)
    receipt_id: str | None = None
    invoice_id: str | None = None


def register_email_receipts(app, connect):
    with closing(connect()) as db:
        db.executescript('''CREATE TABLE IF NOT EXISTS email_outcomes (
            source_namespace TEXT NOT NULL, source_id TEXT NOT NULL, attachment_id TEXT NOT NULL,
            batch_id TEXT NOT NULL, case_id TEXT NOT NULL, status TEXT NOT NULL, reason_code TEXT NOT NULL,
            receipt_id TEXT REFERENCES receipts, invoice_id TEXT REFERENCES invoices,
            updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
            PRIMARY KEY(source_namespace,source_id,attachment_id)
        );''')

    @app.post('/api/ap/email-outcomes')
    def save_outcome(outcome: EmailOutcome):
        values = outcome.model_dump()
        with closing(connect()) as db:
            if outcome.receipt_id:
                receipt = db.execute('SELECT * FROM receipts WHERE receipt_id=?', (outcome.receipt_id,)).fetchone()
                if not receipt or any(receipt[k] != values[k] for k in ('source_namespace','source_id','attachment_id','invoice_id')) or receipt['source_type'] != 'email':
                    raise HTTPException(409, 'Email outcome does not match its receipt.')
            db.execute('''INSERT INTO email_outcomes(source_namespace,source_id,attachment_id,batch_id,case_id,status,reason_code,receipt_id,invoice_id)
                VALUES(:source_namespace,:source_id,:attachment_id,:batch_id,:case_id,:status,:reason_code,:receipt_id,:invoice_id)
                ON CONFLICT(source_namespace,source_id,attachment_id) DO UPDATE SET
                status=excluded.status,reason_code=excluded.reason_code,receipt_id=excluded.receipt_id,
                invoice_id=excluded.invoice_id,updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now')''', values)
            db.commit()
        return values

    @app.get('/api/ap/email-batches/{batch_id}')
    def batch(batch_id: str):
        with closing(connect()) as db:
            outcomes = [dict(r) for r in db.execute('SELECT * FROM email_outcomes WHERE batch_id=? ORDER BY source_id,attachment_id', (batch_id,))]
            invoices = {r['invoice_id'] for r in outcomes if r['invoice_id']}
            tasks = [dict(r) for r in db.execute('SELECT review_id,invoice_id,status FROM review_tasks') if r['invoice_id'] in invoices]
            notifications = [dict(r) for r in db.execute('SELECT notification_id,invoice_id,status,message_id,error_code FROM notification_attempts') if r['invoice_id'] in invoices]
        return {'batch_id':batch_id,'messages':len({(r['source_namespace'],r['source_id']) for r in outcomes}),
                'receipts':len({r['receipt_id'] for r in outcomes if r['receipt_id']}),
                'unique_invoices':len(invoices),'review_tasks':len(tasks),
                'failed_items':sum(r['status'].endswith('_failed') for r in outcomes),
                'skipped_items':sum(r['status']=='skipped' for r in outcomes),
                'outcomes':outcomes,'tasks':tasks,'notifications':notifications,
                'notification_scope':'All attempts for linked invoices, including earlier batches; not new-email count.'}

    return save_outcome
