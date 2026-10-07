"""Document stages shared by legacy processing and the compact workflow."""
from contextlib import closing
import json
import os
import threading
from fastapi import HTTPException
from backend.document_text import ProcessingError, QUALITY_VERSION
from backend.extraction import grounded_fields, wait_for_model_cooldown
from backend.validation import validate

from backend.invoice_agent import ANALYSIS_SIGNATURE, trace_sink

PIPELINE = 'langchain-agent-layout-v1'


class DocumentStages:
    def __init__(self, connect, invoice_row, get_invoice, originals, read_pages, extract_fields):
        self.connect, self.invoice_row, self.get_invoice = connect, invoice_row, get_invoice
        self.originals, self.read_pages, self.extract_fields = originals, read_pages, extract_fields
        self.lock = threading.RLock()
        with closing(connect()) as db:
            db.execute('CREATE TABLE IF NOT EXISTS document_reads (invoice_id TEXT PRIMARY KEY REFERENCES invoices, quality_version TEXT NOT NULL, pages_json TEXT NOT NULL)')
            db.commit()

    def latest(self, invoice_id):
        with closing(self.connect()) as db:
            return db.execute('SELECT * FROM processing_attempts WHERE invoice_id=? ORDER BY attempt_id DESC LIMIT 1', (invoice_id,)).fetchone()

    def reusable(self, attempt):
        result = json.loads(attempt['result_json'] or '{}') if attempt else {}
        return bool(attempt and attempt['status'] in ('analyzed', 'processed')
                    and result.get('pipeline_version') == PIPELINE
                    and result.get('analysis_signature') == ANALYSIS_SIGNATURE
                    and result.get('model') == os.environ.get('AP_LLM_MODEL')
                    and result.get('model_base_url') == os.environ.get('AP_LLM_BASE_URL'))

    def read(self, invoice_id):
        row = self.invoice_row(invoice_id)
        previous = self.latest(invoice_id)
        result = json.loads(previous['result_json'] or '{}') if previous else {}
        pages = result.get('pages') or []
        if pages and all(p.get('quality_rule') == QUALITY_VERSION for p in pages):
            return pages
        with closing(self.connect()) as db:
            cached = db.execute('SELECT * FROM document_reads WHERE invoice_id=?', (invoice_id,)).fetchone()
        if cached and cached['quality_version'] == QUALITY_VERSION:
            return json.loads(cached['pages_json'])
        pages = self.read_pages(self.originals / row['stored_name'], row['media_type'])
        with closing(self.connect()) as db:
            db.execute('INSERT OR REPLACE INTO document_reads VALUES(?,?,?)', (invoice_id, QUALITY_VERSION, json.dumps(pages)))
            db.commit()
        return pages

    def fail(self, attempt_id, result, exc):
        error = exc if isinstance(exc, ProcessingError) else ProcessingError('PROCESSING_FAILED', 'Processing failed; inspect backend diagnostics.')
        with closing(self.connect()) as db:
            db.execute("UPDATE processing_attempts SET status='failed',result_json=?,error_code=?,error_message=? WHERE attempt_id=?", (json.dumps(result), error.code, str(error), attempt_id))
            db.commit()
        status = 429 if error.code in ('MODEL_LOCAL_RATE_LIMIT', 'MODEL_RATE_LIMITED') else (503 if error.code in ('MODEL_NOT_CONFIGURED', 'OCR_DEPENDENCY_MISSING', 'ORIGINAL_UNAVAILABLE') else 502)
        raise HTTPException(status, {'code': error.code, 'message': str(error)}) from exc

    def analyze(self, invoice_id, wait_for_slot=False):
        with self.lock:
            self.invoice_row(invoice_id)
            with closing(self.connect()) as db:
                db.execute('BEGIN IMMEDIATE')
                previous = db.execute('SELECT * FROM processing_attempts WHERE invoice_id=? ORDER BY attempt_id DESC LIMIT 1', (invoice_id,)).fetchone()
                if self.reusable(previous):
                    return previous['attempt_id']
                task = db.execute('SELECT status FROM review_tasks WHERE invoice_id=?', (invoice_id,)).fetchone()
                if task and task['status'] != 'pending':
                    raise HTTPException(409, 'Final invoices cannot be reanalyzed. Their approved snapshot is preserved.')
                if previous and previous['status'] == 'processing':
                    raise HTTPException(409, 'Invoice processing is already in progress.')
                attempt_id = db.execute("INSERT INTO processing_attempts(invoice_id,status) VALUES(?,'processing')", (invoice_id,)).lastrowid
                db.commit()
            result = {'analysis_signature': ANALYSIS_SIGNATURE, 'pipeline_version': PIPELINE, 'model': os.environ.get('AP_LLM_MODEL'), 'model_base_url': os.environ.get('AP_LLM_BASE_URL'), 'pages': []}
            try:
                # Read before replacing the previous cached page source.
                old = json.loads(previous['result_json'] or '{}') if previous else {}
                pages = old.get('pages') or []
                result['pages'] = pages if pages and all(p.get('quality_rule') == QUALITY_VERSION for p in pages) else self.read(invoice_id)
                if wait_for_slot:
                    wait_for_model_cooldown()
                def save_trace(trace):
                    result['agent_trace'] = trace
                    with closing(self.connect()) as trace_db:
                        trace_db.execute('UPDATE processing_attempts SET result_json=? WHERE attempt_id=?', (json.dumps(result), attempt_id))
                        trace_db.commit()
                token = trace_sink.set(save_trace)
                try:
                    result['raw_extraction'] = self.extract_fields(result['pages'])
                finally:
                    trace_sink.reset(token)
                with closing(self.connect()) as db:
                    db.execute("UPDATE processing_attempts SET status='analyzed',result_json=? WHERE attempt_id=?", (json.dumps(result), attempt_id))
                    db.commit()
            except Exception as exc:
                self.fail(attempt_id, result, exc)
            return attempt_id

    def finalize(self, invoice_id, attempt_id):
        with self.lock:
            attempt = self.latest(invoice_id)
            if not attempt or attempt['attempt_id'] != attempt_id:
                raise HTTPException(409, 'Analysis attempt is no longer current.')
            if attempt['status'] == 'processed':
                return self.get_invoice(invoice_id)
            if attempt['status'] != 'analyzed':
                raise HTTPException(409, 'Complete analysis before validation.')
            result = json.loads(attempt['result_json'])
            try:
                grounded, evidence_issues = grounded_fields(result['raw_extraction'], result['pages'])
                result['fields'], issues, result['arithmetic_check'] = validate(grounded)
                issues.extend(evidence_issues)
                for uncertainty in result['raw_extraction']['uncertainties']:
                    issues.append({'code': 'EXTRACTION_UNCERTAINTY', 'field': 'document', 'message': uncertainty})
                for page in result['pages']:
                    if page['ocr_confidence'] is not None and page['ocr_confidence'] < 80:
                        issues.append({'code': 'OCR_LOW_CONFIDENCE', 'field': f"page_{page['page']}", 'message': 'OCR word confidence is low; compare with the original.'})
                result['validation_issues'] = issues
                with closing(self.connect()) as db:
                    db.execute("UPDATE processing_attempts SET status='processed',result_json=? WHERE attempt_id=?", (json.dumps(result), attempt_id))
                    db.commit()
            except Exception as exc:
                self.fail(attempt_id, result, exc)
            return self.get_invoice(invoice_id)

    def process(self, invoice_id):
        with self.lock:
            try:
                return self.finalize(invoice_id, self.analyze(invoice_id))
            except HTTPException as exc:
                if isinstance(exc.detail, dict):
                    exc.detail = {**exc.detail, 'invoice_id': invoice_id}
                raise
