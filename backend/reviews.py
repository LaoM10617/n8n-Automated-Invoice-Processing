"""Versioned review and deterministic approval. No model or network calls."""
from contextlib import closing
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
from typing import Literal
from uuid import uuid4

from fastapi import HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from backend.extraction import RawFields
from backend.validation import validate, duplicate_candidates

POLICY_VERSION = 'eur-gross-under-10000-v1'
THRESHOLD = Decimal('10000.00')
REVIEWER = 'demo reviewer (local, unauthenticated)'
RESOLVABLE = {'UNSUPPORTED_EXTRACTION', 'EXTRACTION_UNCERTAINTY', 'OCR_LOW_CONFIDENCE', 'DOCUMENT_QUALITY_WARNING'}
DETERMINISTIC = {'MISSING_FIELD', 'DATE_AMBIGUOUS_OR_INVALID', 'DUE_BEFORE_INVOICE',
                 'CURRENCY_UNRESOLVED', 'NEGATIVE_AMOUNT_REVIEW', 'AMOUNT_AMBIGUOUS_OR_INVALID',
                 'TOTAL_CHECK_INCOMPLETE', 'TOTAL_EQUATION_REVIEW', 'TOTAL_MISMATCH'}


def encoded(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False)


def digest(value):
    return hashlib.sha256(encoded(value).encode()).hexdigest()


class Version(BaseModel):
    model_config = ConfigDict(extra='forbid')
    expected_revision: int = Field(ge=0)
    processing_attempt_id: int = Field(gt=0)


class Resolution(BaseModel):
    model_config = ConfigDict(extra='forbid')
    id: str = Field(min_length=1, max_length=200)
    reason: str = Field(min_length=1, max_length=2000)
    page: int = Field(ge=1)

    @field_validator('reason')
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError('A reason is required')
        return value.strip()


class DuplicateResolution(Resolution):
    disposition: Literal['not_duplicate', 'justified_continue', 'confirmed_duplicate']


class SaveReview(Version):
    changes: dict[str, str | bool | None] = Field(default_factory=dict)
    reason: str = Field(min_length=1, max_length=2000)
    page: int = Field(ge=1)
    evidence_resolutions: list[Resolution] = Field(default_factory=list, max_length=100)
    duplicate_resolutions: list[DuplicateResolution] = Field(default_factory=list, max_length=100)
    adopt_attempt_id: int | None = Field(default=None, gt=0)


class Decision(Version):
    decision: Literal['approve', 'reject']
    request_id: str = Field(min_length=1, max_length=100)
    reason: str = Field(default='', max_length=2000)

    @model_validator(mode='before')
    @classmethod
    def saved_decision_only(cls, value):
        if isinstance(value, dict):
            if any(key in value for key in ('changes', 'evidence_resolutions', 'duplicate_resolutions', 'has_unsaved_changes')):
                raise ValueError('Save changes and exception resolutions before deciding.')
            if value.get('decision') == 'reject' and not str(value.get('reason') or '').strip():
                raise ValueError('Reject requires a reason.')
            if not str(value.get('request_id') or '').strip():
                raise ValueError('A nonblank request ID is required.')
        return value


def protect_write(request: Request):
    # The host ports are loopback-only. Reject cross-origin browser writes and simple forms.
    if request.url.hostname not in ('localhost', '127.0.0.1', 'python-api', '[::1]', '::1'):
        raise HTTPException(403, 'Local review host required.')
    origin = request.headers.get('origin')
    if origin and origin != str(request.base_url).rstrip('/'):
        raise HTTPException(403, 'Same-origin review request required.')
    if request.headers.get('x-ap-review') != '1':
        raise HTTPException(403, 'Review request header required.')
    if request.headers.get('sec-fetch-site') == 'cross-site':
        raise HTTPException(403, 'Cross-site review request denied.')


class Reviews:
    def __init__(self, connect):
        self.connect = connect

    def load(self, db, invoice_id):
        task = db.execute('SELECT * FROM review_tasks WHERE invoice_id=?', (invoice_id,)).fetchone()
        if not task:
            raise HTTPException(404, 'Review task not found.')
        task = dict(task)
        bound = task['extraction_attempt_id'] or task['created_attempt_id']
        revision = db.execute('SELECT * FROM review_revisions WHERE review_id=? AND revision=?',
                              (task['review_id'], task['current_revision'])).fetchone()
        attempt = db.execute('SELECT * FROM processing_attempts WHERE attempt_id=? AND invoice_id=?', (bound, invoice_id)).fetchone()
        latest = db.execute('SELECT attempt_id,status FROM processing_attempts WHERE invoice_id=? ORDER BY attempt_id DESC LIMIT 1', (invoice_id,)).fetchone()
        result = json.loads(attempt['result_json'] or '{}')
        fields = json.loads(revision['fields_json']) if revision else result.get('fields', {})
        return task, bound, revision, result, fields, dict(latest)

    def evaluate(self, db, invoice_id, bound, result, fields, evidence, duplicates):
        clean = {key: (value.strip() or None) if isinstance(value, str) else value for key, value in fields.items()}
        normalized, issues, arithmetic = validate(clean)
        machine_issues = []
        source_issues = list(result.get('validation_issues', []))
        for page in result.get('pages', []):
            for warning in page.get('warnings', []):
                source_issues.append({'code': 'DOCUMENT_QUALITY_WARNING', 'field': f"page_{page['page']}", 'message': warning})
        for index, item in enumerate(source_issues):
            item = {**item, 'id': digest([bound, index, item]), 'resolvable': item['code'] in RESOLVABLE}
            machine_issues.append(item)
            if item['code'] in {'AMOUNT_AMBIGUOUS_OR_INVALID', 'DATE_AMBIGUOUS_OR_INVALID'} and fields.get(item['field']) == result.get('fields', {}).get(item['field']):
                issues.append(item)
            if item['code'] not in DETERMINISTIC:
                if not (item['resolvable'] and any(r['id'] == item['id'] for r in evidence)):
                    issues.append(item)
        # Compare with saved human/approved values where available, otherwise latest extraction.
        others = []
        for row in db.execute('''SELECT p.invoice_id,p.result_json,r.fields_json FROM processing_attempts p
                LEFT JOIN review_tasks t ON t.invoice_id=p.invoice_id
                LEFT JOIN review_revisions r ON r.review_id=t.review_id AND r.revision=t.current_revision
                WHERE p.invoice_id<>? AND p.attempt_id=(SELECT MAX(attempt_id) FROM processing_attempts WHERE invoice_id=p.invoice_id)''', (invoice_id,)):
            other = json.loads(row['fields_json']) if row['fields_json'] else json.loads(row['result_json'] or '{}').get('fields')
            if other:
                others.append((row['invoice_id'], other))
        status, candidates = duplicate_candidates(normalized, others)
        for candidate in candidates:
            # A changed candidate invalidates an earlier manual resolution.
            other = next(value for key, value in others if key == candidate['invoice_id'])
            candidate['id'] = digest([candidate['invoice_id'], other])
            resolution = next((r for r in duplicates if r['id'] == candidate['id']), None)
            if not resolution:
                issues.append({'code': 'BUSINESS_DUPLICATE_CANDIDATE', 'field': 'invoice_number',
                               'message': 'Record a disposition and reason for this duplicate candidate before deciding.', 'id': candidate['id']})
            elif resolution.get('disposition') == 'confirmed_duplicate':
                issues.append({'code': 'CONFIRMED_DUPLICATE', 'field': 'invoice_number',
                               'message': 'Confirmed duplicate: reject this invoice; approval is blocked.', 'id': candidate['id']})
        if status == 'not_evaluable':
            issues.append({'code': 'DUPLICATE_CHECK_INCOMPLETE', 'field': 'supplier', 'message': 'Supplier identity and invoice number are required for duplicate checking.'})
        if normalized.get('total_amount') is not None and Decimal(normalized['total_amount']) <= 0:
            issues.append({'code': 'NON_POSITIVE_TOTAL', 'field': 'total_amount', 'message': 'A positive invoice total is required.'})
        return {'fields': normalized, 'issues': issues, 'arithmetic': arithmetic, 'machine_issues': machine_issues,
                'duplicate_status': status, 'duplicate_candidates': candidates, 'can_approve': not issues}

    def state(self, db, invoice_id):
        task, bound, revision, result, fields, latest = self.load(db, invoice_id)
        evidence = json.loads(revision['evidence_resolution_json']) if revision else []
        duplicates = json.loads(revision['duplicate_resolution_json']) if revision else []
        # Final decisions retain their original validation explanation, even if other invoices change.
        checked = json.loads(revision['validation_json']) if task['status'] != 'pending' and revision else self.evaluate(db, invoice_id, bound, result, fields, evidence, duplicates)
        blockers = []
        if task['status'] != 'pending':
            blockers.append({'code': 'REVIEW_FINAL', 'message': 'This decision is final. Its saved validation is shown.'})
        if latest['status'] != 'processed':
            blockers.append({'code': 'PROCESSING_INCOMPLETE', 'message': 'Complete processing before saving or deciding.'})
        if latest['attempt_id'] != bound:
            blockers.append({'code': 'ANALYSIS_VERSION_CONFLICT', 'message': 'Compare and explicitly accept the latest analysis first.'})
        if not revision:
            blockers.append({'code': 'REVIEW_NOT_SAVED', 'message': 'Save a review version before deciding.'})
        unresolved_duplicates = any(i['code'] == 'BUSINESS_DUPLICATE_CANDIDATE' for i in checked['issues'])
        gate = {'can_approve': not blockers and checked['can_approve'],
                'can_reject': not blockers and not unresolved_duplicates, 'blockers': blockers}
        history = [dict(r) for r in db.execute('SELECT revision,processing_attempt_id,changes_json,actor,notes,created_at FROM review_revisions WHERE review_id=? ORDER BY revision', (task['review_id'],))]
        event = db.execute('SELECT event_id,event_type,status,attempts,last_error,last_attempt_at,accepted_at,processed_at FROM review_events WHERE review_id=?', (task['review_id'],)).fetchone()
        return {**task, 'processing_attempt_id': bound, 'latest_attempt_id': latest['attempt_id'],
                'latest_fields': json.loads(db.execute('SELECT result_json FROM processing_attempts WHERE attempt_id=?', (latest['attempt_id'],)).fetchone()[0] or '{}').get('fields'),
                'version_conflict': latest['attempt_id'] != bound, 'processing_status': latest['status'],
                'machine_fields': result.get('fields', {}), 'raw_extraction': result.get('raw_extraction', {}),
                'analysis_source': result.get('analysis_source', 'provider_analysis'),
                'current_fields': fields, 'validation': checked, 'decision_gate': gate, 'history': history,
                'evidence_resolutions': evidence, 'duplicate_resolutions': duplicates,
                'event': dict(event) if event else None, 'reviewer': REVIEWER}

    def read(self, invoice_id):
        with closing(self.connect()) as db:
            db.execute('BEGIN')
            return self.state(db, invoice_id)

    def check_version(self, task, bound, latest, request, allow_adopt=False):
        if task['status'] != 'pending':
            raise HTTPException(409, 'This review is final. Refresh to see the decision.')
        if request.expected_revision != task['current_revision'] or request.processing_attempt_id != bound:
            raise HTTPException(409, 'Review version changed. Refresh and compare before saving.')
        if latest['status'] != 'processed':
            raise HTTPException(409, 'Current processing must be complete.')
        if latest['attempt_id'] != bound and not allow_adopt:
            raise HTTPException(409, 'Analysis changed. Explicitly accept the new attempt after comparing it.')

    def snapshot(self, db, task, bound, checked, changes, evidence, duplicates, actor, notes):
        revision = task['current_revision'] + 1
        db.execute('''INSERT INTO review_revisions(review_id,invoice_id,revision,processing_attempt_id,
            fields_json,changes_json,validation_json,duplicate_resolution_json,evidence_resolution_json,actor,notes)
            VALUES(?,?,?,?,?,?,?,?,?,?,?)''', (task['review_id'], task['invoice_id'], revision, bound,
            encoded(checked['fields']), encoded(changes), encoded(checked), encoded(duplicates), encoded(evidence), actor, notes))
        db.execute('UPDATE review_tasks SET current_revision=?,extraction_attempt_id=? WHERE review_id=?', (revision, bound, task['review_id']))
        return revision

    def save(self, invoice_id, request):
        with closing(self.connect()) as db:
            db.execute('BEGIN IMMEDIATE')
            task, bound, revision, result, fields, latest = self.load(db, invoice_id)
            adopting = request.adopt_attempt_id is not None
            self.check_version(task, bound, latest, request, allow_adopt=adopting)
            if adopting:
                if request.adopt_attempt_id != latest['attempt_id']:
                    raise HTTPException(409, 'The selected analysis is no longer current.')
                bound = request.adopt_attempt_id
                result = json.loads(db.execute('SELECT result_json FROM processing_attempts WHERE attempt_id=?', (bound,)).fetchone()[0])
                if not revision:
                    fields = result['fields']
            pages = json.loads(db.execute('SELECT inspection FROM invoices WHERE invoice_id=?', (invoice_id,)).fetchone()[0])['page_count']
            resolutions = request.evidence_resolutions + request.duplicate_resolutions
            if not request.reason.strip() or request.page > pages or any(r.page > pages for r in resolutions):
                raise HTTPException(422, 'A reason and valid original-document page are required.')
            for key, value in request.changes.items():
                if key not in RawFields.model_fields or (key == 'has_adjustments' and value is not None and type(value) is not bool) or (key != 'has_adjustments' and value is not None and not isinstance(value, str)):
                    raise HTTPException(422, 'Unsupported field or field type.')
                if isinstance(value, str) and len(value) > 4000:
                    raise HTTPException(422, 'Field is too long.')
            incoming = {k: (v.strip() or None) if isinstance(v, str) else v for k, v in request.changes.items()}
            changed = {k: {'before': fields.get(k), 'after': v, 'source': 'manual', 'page': request.page, 'reason': request.reason.strip()} for k, v in incoming.items() if fields.get(k) != v}
            evidence = [r.model_dump() for r in request.evidence_resolutions]
            duplicates = [r.model_dump() for r in request.duplicate_resolutions]
            checked = self.evaluate(db, invoice_id, bound, result, {**fields, **incoming}, evidence, duplicates)
            if any(i['code'] in {'AMOUNT_AMBIGUOUS_OR_INVALID', 'DATE_AMBIGUOUS_OR_INVALID'} and i['field'] in incoming for i in checked['issues']):
                raise HTTPException(422, 'Enter unambiguous dates and amounts before saving.')
            valid_evidence = {i['id'] for i in checked['machine_issues'] if i['resolvable']}
            valid_duplicates = {c['id'] for c in checked['duplicate_candidates']}
            if any(r['id'] not in valid_evidence for r in evidence) or any(r['id'] not in valid_duplicates for r in duplicates):
                raise HTTPException(409, 'Exception or duplicate candidate changed. Refresh and compare.')
            if len({r['id'] for r in evidence}) != len(evidence) or len({r['id'] for r in duplicates}) != len(duplicates):
                raise HTTPException(422, 'Record only one resolution per issue or candidate.')
            candidate_ids = {c['id']: c['invoice_id'] for c in checked['duplicate_candidates']}
            duplicates = [{**r, 'invoice_id': candidate_ids[r['id']]} for r in duplicates]
            self.snapshot(db, task, bound, checked, changed, evidence, duplicates, REVIEWER, request.reason.strip())
            state = self.state(db, invoice_id)
            db.commit()
            return state

    def commit_decision(self, db, task, bound, checked, evidence, duplicates, method, decision, reason, request_id=None, request_hash=None, policy=None):
        actor = 'system' if method == 'automatic' else REVIEWER
        revision = self.snapshot(db, task, bound, checked, {}, evidence, duplicates, actor, reason)
        event_id = str(uuid4())
        db.execute('''UPDATE review_tasks SET status=?,decided_by=?,decided_at=?,approval_method=?,
            policy_version=?,policy_inputs_json=?,routing_reason=? WHERE review_id=?''',
            (decision, actor, datetime.now(timezone.utc).isoformat(), method,
             POLICY_VERSION if method == 'automatic' else task['policy_version'],
             encoded(policy) if policy else task['policy_inputs_json'], reason, task['review_id']))
        db.execute('''INSERT INTO review_events(event_id,review_id,invoice_id,review_revision,event_type,request_id,request_hash)
                      VALUES(?,?,?,?,?,?,?)''', (event_id, task['review_id'], task['invoice_id'], revision, decision, request_id, request_hash))
        return event_id

    def decide(self, invoice_id, request):
        request_hash = digest([invoice_id, request.model_dump()])
        with closing(self.connect()) as db:
            db.execute('BEGIN IMMEDIATE')
            prior = db.execute('SELECT * FROM review_requests WHERE request_id=?', (request.request_id,)).fetchone()
            if prior and prior['request_hash'] != request_hash:
                raise HTTPException(409, 'Request ID was already used for different content.')
            task, bound, revision, result, fields, latest = self.load(db, invoice_id)
            final = 'approved' if request.decision == 'approve' else 'rejected'
            if task['status'] != 'pending':
                if task['status'] != final:
                    raise HTTPException(409, 'A different final decision already exists.')
                event_id = db.execute('SELECT event_id FROM review_events WHERE review_id=?', (task['review_id'],)).fetchone()[0]
            else:
                self.check_version(task, bound, latest, request)
                if not revision:
                    raise HTTPException(409, 'Save a review version before deciding.')
                if final == 'rejected' and not request.reason.strip():
                    raise HTTPException(422, 'Reject requires a reason.')
                evidence = json.loads(revision['evidence_resolution_json'])
                duplicates = json.loads(revision['duplicate_resolution_json'])
                checked = self.evaluate(db, invoice_id, bound, result, fields, evidence, duplicates)
                if any(i['code'] == 'BUSINESS_DUPLICATE_CANDIDATE' for i in checked['issues']):
                    raise HTTPException(422, {'message': 'Save a disposition and reason for each duplicate candidate before deciding.', 'issues': checked['issues']})
                if final == 'approved' and not checked['can_approve']:
                    raise HTTPException(422, {'message': 'Resolve approval blockers first.', 'issues': checked['issues']})
                event_id = self.commit_decision(db, task, bound, checked, evidence, duplicates, 'manual', final, request.reason.strip(), request.request_id, request_hash)
            if not prior:
                db.execute('INSERT INTO review_requests VALUES(?,?,?,?)', (request.request_id, invoice_id, request_hash, event_id))
            state = self.state(db, invoice_id)
            db.commit()
            return state

    def automatic(self, invoice_id, request=None, new_only=False):
        with closing(self.connect()) as db:
            db.execute('BEGIN IMMEDIATE')
            task = db.execute('SELECT * FROM review_tasks WHERE invoice_id=?', (invoice_id,)).fetchone()
            if new_only and task:
                return self.state(db, invoice_id)
            if not task:
                attempt = db.execute('SELECT * FROM processing_attempts WHERE invoice_id=? ORDER BY attempt_id DESC LIMIT 1', (invoice_id,)).fetchone()
                if not attempt or attempt['status'] != 'processed':
                    raise HTTPException(409, 'Complete processing first.')
                db.execute('INSERT INTO review_tasks(review_id,invoice_id,created_attempt_id,extraction_attempt_id) VALUES(?,?,?,?)', (str(uuid4()), invoice_id, attempt['attempt_id'], attempt['attempt_id']))
            task, bound, revision, result, fields, latest = self.load(db, invoice_id)
            if task['status'] != 'pending':
                return self.state(db, invoice_id)
            request = request or Version(expected_revision=task['current_revision'], processing_attempt_id=bound)
            self.check_version(task, bound, latest, request)
            checked = self.evaluate(db, invoice_id, bound, result, fields, [], [])
            total = checked['fields'].get('total_amount')
            reasons = sorted({i['code'] for i in checked['issues']})
            if revision:
                reasons.append('HUMAN_REVIEW_EXISTS')
            if checked['fields'].get('currency') != 'EUR':
                reasons.append('NON_EUR')
            if total is None or not Decimal('0') < Decimal(total) < THRESHOLD:
                reasons.append('OUTSIDE_AMOUNT_POLICY')
            policy = {'version': POLICY_VERSION, 'threshold': str(THRESHOLD), 'currency': 'EUR',
                      'amount_basis': 'gross total_amount', 'fields': checked['fields'],
                      'checks': checked, 'reasons': reasons}
            if not reasons:
                self.commit_decision(db, task, bound, checked, [], [], 'automatic', 'approved', 'All automatic approval gates passed.', policy=policy)
            else:
                db.execute('UPDATE review_tasks SET policy_version=?,policy_inputs_json=?,routing_reason=? WHERE review_id=?', (POLICY_VERSION, encoded(policy), ', '.join(reasons), task['review_id']))
            state = self.state(db, invoice_id)
            db.commit()
            return state


def register_reviews(app, connect):
    reviews = Reviews(connect)

    @app.get('/api/ap/invoices/{invoice_id}/review')
    def read(invoice_id: str):
        return reviews.read(invoice_id)

    @app.patch('/api/ap/invoices/{invoice_id}/review')
    def save(invoice_id: str, body: SaveReview, request: Request):
        protect_write(request)
        return reviews.save(invoice_id, body)

    @app.post('/api/ap/invoices/{invoice_id}/review/decision')
    def decide(invoice_id: str, body: Decision, request: Request):
        protect_write(request)
        return reviews.decide(invoice_id, body)

    @app.post('/api/ap/invoices/{invoice_id}/review/evaluate-policy')
    def policy(invoice_id: str, body: Version, request: Request):
        protect_write(request)
        return reviews.automatic(invoice_id, body)

    return reviews
