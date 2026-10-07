"""Persistent notification attempts; Legacy endpoints and compact stage service share the same claims."""
from contextlib import closing
from typing import Literal
from uuid import uuid4

from fastapi import HTTPException
from pydantic import BaseModel, Field


class NotificationResult(BaseModel):
    status: Literal['sent', 'failed', 'unknown']
    message_id: str | None = Field(default=None, max_length=500)
    error_code: str | None = Field(default=None, max_length=100)


def register_notifications(app, connect, get_invoice):
    with closing(connect()) as db:
        db.executescript('''
            CREATE TABLE IF NOT EXISTS notification_attempts (
                notification_id TEXT PRIMARY KEY,
                invoice_id TEXT NOT NULL REFERENCES invoices,
                review_id TEXT NOT NULL REFERENCES review_tasks(review_id),
                status TEXT NOT NULL CHECK(status IN ('sending','sent','failed','unknown')),
                message_id TEXT, error_code TEXT,
                created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
                updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
            );
        ''')

    @app.get('/api/ap/invoices/{invoice_id}/notifications')
    def notifications(invoice_id: str):
        get_invoice(invoice_id)
        with closing(connect()) as db:
            return [dict(r) for r in db.execute(
                'SELECT * FROM notification_attempts WHERE invoice_id=? ORDER BY rowid', (invoice_id,))]

    @app.post('/api/ap/invoices/{invoice_id}/notifications/claim')
    def claim(invoice_id: str):
        invoice = get_invoice(invoice_id)
        if invoice['review_status'] != 'pending' or invoice['processing_status'] != 'processed':
            raise HTTPException(409, 'A successfully processed pending review is required.')
        with closing(connect()) as db:
            db.execute('BEGIN IMMEDIATE')
            previous = db.execute('SELECT * FROM notification_attempts WHERE invoice_id=? ORDER BY rowid DESC LIMIT 1', (invoice_id,)).fetchone()
            if previous and previous['status'] != 'failed':
                return {'send_required': False, **dict(previous), 'review_url': invoice['review_url']}
            notification_id = str(uuid4())
            db.execute("INSERT INTO notification_attempts(notification_id,invoice_id,review_id,status) VALUES(?,?,?,'sending')",
                       (notification_id, invoice_id, invoice['review_id']))
            db.commit()
        fields = invoice['extracted_fields']
        issues = ', '.join(issue['code'] for issue in invoice['validation_issues']) or 'No rule exceptions; extraction still requires human review.'
        text = '\n'.join([
            'AP invoice ready for review. Compare, save changes, then approve or reject.', f'Invoice ID: {invoice_id}',
            f"Supplier: {fields.get('supplier_name') or 'Unknown'}",
            f"Invoice number: {fields.get('invoice_number') or 'Unknown'}",
            f"Amount: {fields.get('total_amount') or 'Unknown'} {fields.get('currency') or ''}",
            f'Exceptions: {issues}', f"Review: {invoice['review_url']}",
            f'Notification ID: {notification_id}',
            'Status: pending. No approval, export or payment has occurred.',
        ])
        return {'send_required': True, 'notification_id': notification_id,
                'invoice_id': invoice_id, 'status': 'sending', 'review_url': invoice['review_url'],
                'subject': f'[AP Review] {invoice_id}', 'text': text}

    @app.post('/api/ap/notifications/{notification_id}/result')
    def record_result(notification_id: str, result: NotificationResult):
        with closing(connect()) as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT * FROM notification_attempts WHERE notification_id=?', (notification_id,)).fetchone()
            if row is None:
                raise HTTPException(404, 'Notification attempt not found')
            if row['status'] == result.status:
                return dict(row)
            if row['status'] not in ('sending', 'unknown'):
                raise HTTPException(409, 'Notification result is already final.')
            if result.status == 'sent' and not result.message_id:
                raise HTTPException(422, 'SMTP message ID is required for a sent result.')
            db.execute("UPDATE notification_attempts SET status=?,message_id=?,error_code=?,updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE notification_id=?",
                       (result.status, result.message_id, result.error_code, notification_id))
            db.commit()
            return dict(db.execute('SELECT * FROM notification_attempts WHERE notification_id=?', (notification_id,)).fetchone())

    return claim, record_result
