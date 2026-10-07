"""Persisted business stages for the compact n8n canvas; no agent implementation."""
from contextlib import closing
from email.message import EmailMessage
from email.utils import make_msgid
import json
import os
import smtplib
import threading
from typing import Annotated, Literal
from uuid import uuid4
from fastapi import File, Form, HTTPException, UploadFile, Request
from pydantic import BaseModel, ConfigDict, Field, model_validator
from backend.document_text import ProcessingError
from backend.email_receipts import EmailOutcome
from backend.notifications import NotificationResult
from backend.reviews import protect_write
from backend.review_events import protect_event


class Source(BaseModel):
    model_config = ConfigDict(extra='forbid')
    source_type: Literal['upload', 'email']
    source_namespace: str = Field(min_length=1, max_length=200)
    source_id: str = Field(min_length=1, max_length=200)
    attachment_id: str = Field(min_length=1, max_length=200)
    batch_id: str | None = Field(default=None, pattern=r'^[A-Za-z0-9_-]{1,80}$')
    case_id: str | None = Field(default=None, pattern=r'^[A-Za-z0-9_-]{1,80}$')

    @model_validator(mode='after')
    def email_batch(self):
        if self.source_type == 'email' and not (self.batch_id and self.case_id):
            raise ValueError('Email inputs require batch_id and case_id.')
        if any(not getattr(self, key).strip() for key in ('source_namespace','source_id','attachment_id')):
            raise ValueError('Source identifiers must not be blank.')
        return self


class StageResult(BaseModel):
    contract_version: str = 'ap-stage-v1'
    run_id: str
    source: Source
    stage: str = 'archive'
    outcome: Literal['continue','review_ready','decision_ready','skipped','failed'] = 'continue'
    receipt_id: str | None = None
    invoice_id: str | None = None
    analysis_run_id: int | None = None
    review_id: str | None = None
    review_url: str | None = None
    issue_codes: list[str] = Field(default_factory=list)
    error_code: str | None = None
    retryable: bool = False
    notification_status: str = 'not_started'
    extractor: str = 'python_langchain_agent'
    analysis_cached: bool = False
    analysis_source: str = 'provider_analysis'
    review_status: str | None = None
    approval_method: str | None = None
    event_id: str | None = None
    event_delivery_status: str | None = None
    event_delivery_error: str | None = None


def unpack(value):
    return json.loads(value.body) if hasattr(value, 'body') else value


def send_local_notification(claim, record, invoice_id):
    notice = claim(invoice_id)
    if not notice['send_required']:
        return notice
    message = EmailMessage()
    message['From'], message['To'] = 'ap-review@example.invalid', 'reviewer@example.invalid'
    message['Subject'], message['Message-ID'] = notice['subject'], make_msgid(domain='example.invalid')
    message.set_content(notice['text'])
    # No credentials or external SMTP configuration: this demo sends to local Mailpit.
    host = os.environ.get('AP_MAILPIT_HOST', 'mailpit')
    if host not in ('mailpit', 'localhost', '127.0.0.1'):
        return record(notice['notification_id'], NotificationResult(status='failed', error_code='LOCAL_SMTP_REQUIRED'))
    sending = False
    smtp = None
    try:
        smtp = smtplib.SMTP(host, 1025, timeout=10)
        sending = True
        refused = smtp.send_message(message)
        if refused:
            result = NotificationResult(status='failed', error_code='SMTP_RECIPIENT_REJECTED')
        else:
            result = NotificationResult(status='sent', message_id=message['Message-ID'])
    except (smtplib.SMTPRecipientsRefused, smtplib.SMTPSenderRefused, smtplib.SMTPDataError):
        result = NotificationResult(status='failed', error_code='SMTP_REJECTED')
    except (OSError, smtplib.SMTPException):
        result = NotificationResult(status='unknown' if sending else 'failed', error_code='SMTP_DELIVERY_UNCERTAIN' if sending else 'SMTP_CONNECTION_FAILED')
    finally:
        if smtp is not None:
            smtp.close()
    return record(notice['notification_id'], result)


def register_intake_stages(app, connect, intake, documents, review, notifications, save_outcome, reviews=None, on_decision=None):
    lock = threading.RLock()
    with closing(connect()) as db:
        db.executescript('''CREATE TABLE IF NOT EXISTS intake_runs (
            run_id TEXT PRIMARY KEY, result_json TEXT NOT NULL,
            updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
        ); CREATE TABLE IF NOT EXISTS intake_stage_events (
            event_id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL REFERENCES intake_runs,
            stage TEXT NOT NULL, result_json TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
        );''')
        db.commit()

    def save(result):
        encoded = result.model_dump_json()
        with closing(connect()) as db:
            db.execute("INSERT INTO intake_runs(run_id,result_json) VALUES(?,?) ON CONFLICT(run_id) DO UPDATE SET result_json=excluded.result_json,updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now')", (result.run_id, encoded))
            db.execute('INSERT INTO intake_stage_events(run_id,stage,result_json) VALUES(?,?,?)', (result.run_id,result.stage,encoded))
            db.commit()
        if result.source.source_type == 'email' and result.outcome != 'continue':
            status = 'skipped' if result.outcome == 'skipped' else 'decision_ready' if result.outcome == 'decision_ready' else 'review_ready' if result.outcome == 'review_ready' else 'intake_failed' if result.receipt_id is None else 'review_failed' if result.stage == 'validate' else 'processing_failed'
            save_outcome(EmailOutcome(**{k:v for k,v in result.source.model_dump().items() if k!='source_type'}, status=status,
                reason_code=result.error_code or ('DECISION_SAVED' if result.outcome == 'decision_ready' else 'PENDING_REVIEW'), receipt_id=result.receipt_id, invoice_id=result.invoice_id))
        return result

    def load(run_id):
        with closing(connect()) as db:
            row = db.execute('SELECT result_json FROM intake_runs WHERE run_id=?', (run_id,)).fetchone()
        if not row:
            raise HTTPException(404, 'Intake run not found.')
        return StageResult.model_validate_json(row['result_json'])

    def failure(result, exc):
        result.outcome = 'failed'
        if isinstance(exc, ProcessingError):
            result.error_code = exc.code
        elif isinstance(exc, HTTPException):
            result.error_code = exc.detail.get('code', f'HTTP_{exc.status_code}') if isinstance(exc.detail,dict) else f'HTTP_{exc.status_code}'
        else:
            result.error_code = 'STAGE_FAILED'
        result.retryable = result.error_code in ('MODEL_LOCAL_RATE_LIMIT','MODEL_RATE_LIMITED','MODEL_UNAVAILABLE','PROCESS_INTERRUPTED','HTTP_503','HTTP_502','STAGE_FAILED')
        return save(result)

    @app.post('/api/ap/stages/archive', response_model=StageResult)
    def archive(metadata: Annotated[str, Form()], file: Annotated[UploadFile | None, File()] = None):
        try:
            source = Source.model_validate_json(metadata)
        except ValueError as exc:
            raise HTTPException(422, 'Invalid source metadata.') from exc
        result = StageResult(run_id=str(uuid4()), source=source)
        save(result)
        no_attachment = file is None or (source.attachment_id == 'none' and file.content_type == 'application/x-ap-no-attachment')
        if no_attachment or file.content_type not in ('application/pdf','image/png','image/jpeg'):
            result.outcome = 'skipped'
            result.error_code = 'NO_ATTACHMENTS' if no_attachment else 'UNSUPPORTED_ATTACHMENT'
            return save(result)
        try:
            saved = unpack(intake(file=file, **{k:v for k,v in source.model_dump().items() if k not in ('batch_id','case_id')}))
            result.receipt_id, result.invoice_id = saved['receipt_id'], saved['invoice_id']
            save(result)
            documents.read(result.invoice_id)
            result.stage = 'read'
            return save(result)
        except Exception as exc:
            return failure(result, exc)

    @app.get('/api/ap/stages/{run_id}', response_model=StageResult)
    def state(run_id: str):
        return load(run_id)

    @app.post('/api/ap/stages/{run_id}/analyze', response_model=StageResult)
    def analyze(run_id: str):
        with lock:
            result = load(run_id)
            if result.outcome != 'continue' or result.stage in ('analyze','validate','notify'):
                return result
            if result.stage != 'read':
                raise HTTPException(409, 'Complete document reading first.')
            result.stage = 'analyze'
            try:
                previous = documents.latest(result.invoice_id)
                result.analysis_cached = documents.reusable(previous)
                result.analysis_run_id = documents.analyze(result.invoice_id, wait_for_slot=True)
                saved = documents.latest(result.invoice_id)
                result.analysis_source = json.loads(saved['result_json'] or '{}').get('analysis_source', 'provider_analysis')
                return save(result)
            except Exception as exc:
                return failure(result, exc)

    @app.post('/api/ap/stages/{run_id}/validate', response_model=StageResult)
    def finalize(run_id: str):
        return finalize_run(run_id, False)

    @app.post('/api/ap/stages/{run_id}/validate-policy', response_model=StageResult)
    def finalize_policy(run_id: str, request: Request):
        protect_write(request)
        return finalize_run(run_id, True)

    def finalize_run(run_id, apply_policy):
        with lock:
            result = load(run_id)
            if result.outcome != 'continue':
                return result
            if result.stage != 'analyze' or result.analysis_run_id is None:
                raise HTTPException(409, 'Complete analysis first.')
            result.stage = 'validate'
            try:
                invoice = documents.finalize(result.invoice_id, result.analysis_run_id)
                if apply_policy:
                    task = reviews.automatic(result.invoice_id, new_only=True)
                    result.review_id = task['review_id']
                    result.review_url = os.environ.get('AP_PUBLIC_BASE_URL', 'http://127.0.0.1:8000').rstrip('/') + '/reviews/' + result.invoice_id
                    result.review_status, result.approval_method = task['status'], task['approval_method']
                    result.event_id = task['event']['event_id'] if task['event'] else None
                else:
                    task = unpack(review(result.invoice_id))
                    result.review_id, result.review_url = task['review_id'], task['review_url']
                    result.review_status = task['review_status']
                result.issue_codes = sorted({i['code'] for i in invoice['validation_issues']})
                result.outcome = 'review_ready' if result.review_status == 'pending' else 'decision_ready'
                if not apply_policy and result.outcome == 'decision_ready':
                    result.outcome, result.error_code = 'skipped', 'REVIEW_ALREADY_FINAL'
                return save(result)
            except Exception as exc:
                return failure(result, exc)

    @app.post('/api/ap/stages/{run_id}/notify', response_model=StageResult)
    def notify(run_id: str):
        with lock:
            result = load(run_id)
            if result.outcome != 'review_ready':
                raise HTTPException(409, 'A pending review is required.')
            result.stage = 'notify'
            # SMTP errors are independent from the successful review outcome.
            notice = send_local_notification(*notifications, result.invoice_id)
            result.notification_status = notice['status']
            result.error_code = notice.get('error_code')
            result.retryable = notice['status'] == 'failed'
            return save(result)

    @app.post('/api/ap/stages/{run_id}/handoff', response_model=StageResult)
    def handoff(run_id: str, request: Request):
        protect_event(request)
        result = load(run_id)
        if not result.event_id or result.outcome != 'decision_ready' or not on_decision:
            raise HTTPException(409, 'A saved review decision is required.')
        delivery = on_decision(result.event_id)
        if delivery:
            result.event_delivery_status = delivery['status']
            result.event_delivery_error = delivery['last_error']
        return save(result)

    @app.post('/api/ap/stages/{run_id}/exception', response_model=StageResult)
    def exception(run_id: str):
        result = load(run_id)
        if result.outcome not in ('failed','skipped'):
            raise HTTPException(409, 'No exception to acknowledge.')
        # The originating stage already saved the failure and source outcome.
        return result

    from backend.native_analysis import register_native
    register_native(app, connect, documents, load, save, failure)
