"""Review/approval integration using isolated SQLite and synthetic saved analyses."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import json
import sqlite3
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.reviews import Reviews, Version
from backend.test_review import FIXTURE
from backend.validation import validate

HEADERS = {'X-AP-Review': '1'}


@pytest.fixture
def env(tmp_path, monkeypatch):
    import backend.app as module
    monkeypatch.setattr(module, 'extract_fields', lambda _: pytest.fail('Review must never call a model'))
    client = TestClient(create_app(tmp_path), base_url='http://localhost')
    def connect():
        db = sqlite3.connect(tmp_path / 'invoices.sqlite3', timeout=30)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        return db
    yield client, connect, tmp_path
    client.close()


def seed(env, total='119.00', changes=None, issues=None, task=True, number=None):
    client, connect, _ = env
    # Distinct bytes preserve independent invoices even with shared synthetic business fields.
    payload = FIXTURE.read_bytes() + ('\n% ' + str(uuid4())).encode()
    response = client.post('/api/ap/intakes', data={'source_type': 'upload', 'source_namespace': 'review-acceptance', 'source_id': str(uuid4()), 'attachment_id': '0'}, files={'file': ('invoice.pdf', payload)})
    invoice_id = response.json()['invoice_id']
    raw = {'supplier_name': 'Synthetic supplier', 'supplier_address': 'Example Street 1', 'supplier_tax_id': 'TEST01',
           'invoice_number': number or str(uuid4()), 'invoice_date': '2026-10-01', 'due_date': '2026-10-31', 'currency': 'EUR',
           'net_amount': total, 'tax_amount': '0.00', 'total_amount': total, 'discount_amount': None, 'shipping_amount': None, 'has_adjustments': False, **(changes or {})}
    fields, checked, arithmetic = validate(raw)
    result = {'fields': fields, 'raw_extraction': {'fields': raw, 'evidence': [], 'uncertainties': []}, 'validation_issues': checked + (issues or []), 'arithmetic_check': arithmetic, 'pages': []}
    with closing(connect()) as db:
        attempt = db.execute("INSERT INTO processing_attempts(invoice_id,status,result_json) VALUES(?,'processed',?)", (invoice_id, json.dumps(result))).lastrowid
        db.commit()
    if task:
        assert client.post(f'/api/ap/invoices/{invoice_id}/review-task').status_code == 201
    return invoice_id, attempt


def state(env, invoice_id):
    return env[0].get(f'/api/ap/invoices/{invoice_id}/review').json()


def save(env, invoice_id, **overrides):
    current = state(env, invoice_id)
    return env[0].patch(f'/api/ap/invoices/{invoice_id}/review', headers=HEADERS, json={
        'expected_revision': current['current_revision'], 'processing_attempt_id': current['processing_attempt_id'],
        'changes': {}, 'reason': 'Checked the original document', 'page': 1, **overrides})


def decide(env, invoice_id, decision='approve', **overrides):
    current = state(env, invoice_id)
    return env[0].post(f'/api/ap/invoices/{invoice_id}/review/decision', headers=HEADERS, json={
        'expected_revision': current['current_revision'], 'processing_attempt_id': current['processing_attempt_id'],
        'decision': decision, 'request_id': str(uuid4()), 'reason': 'Reviewed original', **overrides})


@pytest.mark.parametrize('total,approved', [('9999.99', True), ('10000.00', False), ('10000.01', False), ('0.00', False), ('-1.00', False)])
def test_amount_boundaries(env, total, approved):
    invoice_id, _ = seed(env, total, task=False)
    result = Reviews(env[1]).automatic(invoice_id, new_only=True)
    assert result['status'] == ('approved' if approved else 'pending')
    assert json.loads(result['policy_inputs_json'])['threshold'] == '10000.00'
    if approved:
        assert result['decided_by'] == 'system' and result['approval_method'] == 'automatic'
        assert result['event']['status'] == 'pending'
    with closing(env[1]()) as db:
        assert db.execute('SELECT COUNT(*) FROM notification_attempts').fetchone()[0] == 0


@pytest.mark.parametrize('changes,issues', [
    ({'currency': 'USD'}, []), ({'supplier_name': None}, []), ({'supplier_name': '   '}, []),
    ({'tax_amount': '10.00'}, []), ({'supplier_tax_id': None, 'supplier_address': None}, []),
    ({'has_adjustments': None}, []), ({'shipping_amount': '5.00'}, []),
    ({}, [{'code': 'UNSUPPORTED_EXTRACTION', 'field': 'supplier_address', 'message': 'No evidence'}]),
    ({}, [{'code': 'OCR_LOW_CONFIDENCE', 'field': 'page_1', 'message': 'Check page'}]),
    ({}, [{'code': 'EXTRACTION_UNCERTAINTY', 'field': 'document', 'message': 'Check totals'}]),
    ({'discount_amount': '1.234'}, []),
])
def test_policy_blocks_exceptions(env, changes, issues):
    invoice_id, _ = seed(env, changes=changes, issues=issues, task=False)
    result = Reviews(env[1]).automatic(invoice_id, new_only=True)
    assert result['status'] == 'pending' and result['event'] is None


def test_historical_pending_and_human_revision_never_auto_approved(env):
    invoice_id, attempt = seed(env)
    service = Reviews(env[1])
    assert service.automatic(invoice_id, new_only=True)['policy_version'] is None
    assert save(env, invoice_id, changes={'supplier_address': 'Manually checked address'}).status_code == 200
    result = service.automatic(invoice_id, Version(expected_revision=1, processing_attempt_id=attempt))
    assert result['status'] == 'pending' and 'HUMAN_REVIEW_EXISTS' in result['routing_reason']


def test_manual_correction_preserves_draft_and_final_snapshot(env):
    invoice_id, attempt = seed(env, issues=[{'code': 'UNSUPPORTED_EXTRACTION', 'field': 'supplier_address', 'message': 'Address not grounded'}])
    with closing(env[1]()) as db:
        original = db.execute('SELECT result_json FROM processing_attempts WHERE attempt_id=?', (attempt,)).fetchone()[0]
    issue = state(env, invoice_id)['validation']['machine_issues'][0]
    assert save(env, invoice_id, changes={'supplier_address': 'Corrected address'}, evidence_resolutions=[{'id': issue['id'], 'page': 1, 'reason': 'Read the original address block'}]).status_code == 200
    approved = decide(env, invoice_id).json()
    assert approved['status'] == 'approved' and approved['approval_method'] == 'manual'
    assert approved['current_fields']['supplier_address'] == 'Corrected address'
    assert approved['machine_fields']['supplier_address'] == 'Example Street 1'
    assert env[0].post(f'/api/ap/invoices/{invoice_id}/process').status_code == 409
    assert env[0].post(f'/api/ap/invoices/{invoice_id}/review-task').json()['review_status'] == 'approved'
    assert save(env, invoice_id).status_code == 409
    with closing(env[1]()) as db:
        assert db.execute('SELECT result_json FROM processing_attempts WHERE attempt_id=?', (attempt,)).fetchone()[0] == original
        assert db.execute('SELECT COUNT(*) FROM review_events').fetchone()[0] == 1
    with TestClient(create_app(env[2]), base_url='http://localhost') as restarted:
        assert restarted.get(f'/api/ap/invoices/{invoice_id}/review').json()['current_fields'] == approved['current_fields']


def test_stale_pages_and_new_analysis_require_explicit_adoption(env):
    invoice_id, attempt = seed(env)
    assert save(env, invoice_id, changes={'supplier_address': 'Human address'}).status_code == 200
    assert save(env, invoice_id, expected_revision=0).status_code == 409
    with closing(env[1]()) as db:
        result = db.execute('SELECT result_json FROM processing_attempts WHERE attempt_id=?', (attempt,)).fetchone()[0]
        new = db.execute("INSERT INTO processing_attempts(invoice_id,status,result_json) VALUES(?,'processed',?)", (invoice_id, result)).lastrowid
        db.commit()
    current = state(env, invoice_id)
    assert current['version_conflict'] and current['current_fields']['supplier_address'] == 'Human address'
    assert save(env, invoice_id).status_code == 409
    assert decide(env, invoice_id).status_code == 409
    assert save(env, invoice_id, adopt_attempt_id=new).status_code == 200
    assert state(env, invoice_id)['current_fields']['supplier_address'] == 'Human address'


def test_reject_reason_and_request_replay_conflicts(env):
    invoice_id, _ = seed(env)
    assert decide(env, invoice_id).status_code == 409
    save(env, invoice_id)
    assert decide(env, invoice_id, 'reject', reason=' ').status_code == 422
    assert decide(env, invoice_id, 'reject', request_id='one').status_code == 200
    assert decide(env, invoice_id, 'reject', request_id='one', reason='Different').status_code == 409
    assert decide(env, invoice_id, 'reject', request_id='two').status_code == 200
    assert decide(env, invoice_id, 'reject', request_id='two', reason='Different').status_code == 409
    assert decide(env, invoice_id, 'approve').status_code == 409


def test_duplicates_rechecked_at_approval(env):
    invoice_id, _ = seed(env, number='SAME')
    save(env, invoice_id)
    other_id, _ = seed(env, number='SAME')
    assert decide(env, invoice_id).status_code == 422
    current = state(env, invoice_id)
    candidate = current['validation']['duplicate_candidates'][0]
    assert candidate['invoice_id'] == other_id
    assert save(env, invoice_id, duplicate_resolutions=[{'id': candidate['id'], 'disposition': 'justified_continue', 'reason': 'Independent synthetic scenario, justified continuation', 'page': 1}]).status_code == 200
    assert decide(env, invoice_id).status_code == 200


def test_amount_mismatch_and_adjustments_cannot_be_acknowledged_away(env):
    invoice_id, _ = seed(env, changes={'tax_amount': '3.00'})
    save(env, invoice_id)
    assert decide(env, invoice_id).status_code == 422
    assert save(env, invoice_id, changes={'tax_amount': '0.00'}).status_code == 200
    assert decide(env, invoice_id).status_code == 200
    other, _ = seed(env, changes={'has_adjustments': True})
    save(env, other)
    assert decide(env, other).status_code == 422


def test_csrf_and_unsaved_payload(env):
    invoice_id, _ = seed(env)
    endpoint = f'/api/ap/invoices/{invoice_id}/review'
    body = {'expected_revision': 0, 'processing_attempt_id': 1, 'reason': 'Checked', 'page': 1}
    assert env[0].patch(endpoint, json=body).status_code == 403
    assert env[0].patch(endpoint, json=body, headers={**HEADERS, 'Origin': 'http://evil.invalid'}).status_code == 403
    assert save(env, invoice_id, changes={'discount_amount': 'ambiguous'}).status_code == 422
    assert decide(env, invoice_id, changes={'total_amount': '1'}).status_code == 422


def test_concurrent_decisions_and_atomic_event_failure(env):
    invoice_id, _ = seed(env)
    save(env, invoice_id)
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: decide(env, invoice_id).status_code, range(4)))
    assert results == [200] * 4
    with closing(env[1]()) as db:
        assert db.execute('SELECT COUNT(*) FROM review_events').fetchone()[0] == 1
    other, _ = seed(env)
    save(env, other)
    with closing(env[1]()) as db:
        db.execute("CREATE TRIGGER fail_event BEFORE INSERT ON review_events BEGIN SELECT RAISE(ABORT, 'injected'); END")
        db.commit()
    with pytest.raises(sqlite3.IntegrityError):
        decide(env, other)
    assert state(env, other)['status'] == 'pending' and state(env, other)['current_revision'] == 1


def test_auto_and_manual_race_has_one_terminal_event(env):
    invoice_id, attempt = seed(env)
    service = Reviews(env[1])
    with ThreadPoolExecutor(max_workers=2) as pool:
        auto = pool.submit(service.automatic, invoice_id, Version(expected_revision=0, processing_attempt_id=attempt))
        manual = pool.submit(save, env, invoice_id)
        try:
            auto.result()
        except Exception as exc:
            assert getattr(exc, 'status_code', None) == 409
        response = manual.result()
    if response.status_code == 200:
        assert decide(env, invoice_id).status_code == 200
    with closing(env[1]()) as db:
        assert db.execute('SELECT COUNT(*) FROM review_events').fetchone()[0] == 1


def test_new_workflow_policy_stage_and_legacy_replay(env):
    client, connect, _ = env
    invoice_id, attempt = seed(env, task=False)
    from backend.intake_stages import StageResult, Source
    run_id = str(uuid4())
    result = StageResult(run_id=run_id, invoice_id=invoice_id, analysis_run_id=attempt, stage='analyze',
                         source=Source(source_type='upload',source_namespace='test',source_id='one',attachment_id='0'))
    with closing(connect()) as db:
        db.execute('INSERT INTO intake_runs(run_id,result_json) VALUES(?,?)', (run_id, result.model_dump_json()))
        db.commit()
    response = client.post(f'/api/ap/stages/{run_id}/validate-policy', headers=HEADERS)
    assert response.status_code == 200
    assert response.json()['outcome'] == 'decision_ready' and response.json()['approval_method'] == 'automatic'
    assert client.post(f'/api/ap/stages/{run_id}/notify').status_code == 409
    assert client.post(f'/api/ap/stages/{run_id}/validate-policy', headers=HEADERS).json()['event_id'] == response.json()['event_id']


def test_document_quality_warning_blocks_policy_and_is_reviewable(env):
    invoice_id, attempt = seed(env)
    with closing(env[1]()) as db:
        data = json.loads(db.execute('SELECT result_json FROM processing_attempts WHERE attempt_id=?', (attempt,)).fetchone()[0])
        data['pages'] = [{'page': 1, 'warnings': ['SMALL_IMAGES_NOT_OCR']}]
        db.execute('UPDATE processing_attempts SET result_json=? WHERE attempt_id=?', (json.dumps(data), attempt))
        db.commit()
    result = Reviews(env[1]).automatic(invoice_id, Version(expected_revision=0, processing_attempt_id=attempt))
    assert result['status'] == 'pending' and 'DOCUMENT_QUALITY_WARNING' in result['routing_reason']
