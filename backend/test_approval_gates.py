"""Shared approval gates, explicit duplicate dispositions, and final audit snapshots."""
from contextlib import closing

import pytest

from backend.test_review_decisions import env, seed, save, decide, state, HEADERS


@pytest.mark.parametrize('disposition', ['not_duplicate', 'justified_continue', 'confirmed_duplicate'])
def test_duplicate_dispositions_are_saved_and_enforced(env, disposition):
    invoice_id, _ = seed(env, number='DUPLICATE')
    other, _ = seed(env, number='DUPLICATE')
    assert save(env, invoice_id).status_code == 200
    assert decide(env, invoice_id, 'reject').status_code == 422
    candidate = state(env, invoice_id)['validation']['duplicate_candidates'][0]
    resolution = {'id': candidate['id'], 'reason': 'Compared both original documents', 'page': 1}
    assert save(env, invoice_id, duplicate_resolutions=[resolution]).status_code == 422
    resolution['disposition'] = disposition
    assert save(env, invoice_id, duplicate_resolutions=[resolution, resolution]).status_code == 422
    saved = save(env, invoice_id, duplicate_resolutions=[resolution]).json()
    assert saved['duplicate_resolutions'] == [{**resolution, 'invoice_id': other}]
    assert saved['decision_gate']['can_reject']
    if disposition == 'confirmed_duplicate':
        assert not saved['decision_gate']['can_approve']
        assert decide(env, invoice_id).status_code == 422
        final = decide(env, invoice_id, 'reject')
    else:
        assert saved['decision_gate']['can_approve']
        final = decide(env, invoice_id)
    assert final.status_code == 200
    assert final.json()['duplicate_resolutions'] == saved['duplicate_resolutions']
    with closing(env[1]()) as db:
        assert db.execute('SELECT COUNT(*) FROM review_events').fetchone()[0] == 1
        assert db.execute('SELECT COUNT(*) FROM exports').fetchone()[0] == 0


@pytest.mark.parametrize('changes', [
    {'supplier_name': None}, {'invoice_number': None}, {'invoice_date': None},
    {'due_date': None}, {'currency': None}, {'currency': 'unknown'},
    {'invoice_date': 'not a date'}, {'due_date': '2026-09-01'},
    {'net_amount': None}, {'tax_amount': None}, {'total_amount': None},
    {'total_amount': 'unclear'}, {'total_amount': '-119.00'},
    {'tax_amount': '3.00'}, {'has_adjustments': True}, {'shipping_amount': '3.00'},
])
def test_manual_approval_cannot_bypass_deterministic_checks(env, changes):
    invoice_id, _ = seed(env, changes=changes)
    assert save(env, invoice_id).status_code == 200
    assert not state(env, invoice_id)['decision_gate']['can_approve']
    assert decide(env, invoice_id).status_code == 422
    with closing(env[1]()) as db:
        assert db.execute('SELECT COUNT(*) FROM review_events').fetchone()[0] == 0


def test_issue_code_controls_resolution_not_message(env):
    invoice_id, _ = seed(env, issues=[
        {'code': 'UNKNOWN_BLOCKER', 'field': 'document', 'message': 'OCR_LOW_CONFIDENCE'},
        {'code': 'OCR_LOW_CONFIDENCE', 'field': 'document', 'message': 'Check the original'},
    ])
    issues = state(env, invoice_id)['validation']['machine_issues']
    unknown = next(i for i in issues if i['code'] == 'UNKNOWN_BLOCKER')
    ocr = next(i for i in issues if i['code'] == 'OCR_LOW_CONFIDENCE')
    assert save(env, invoice_id, evidence_resolutions=[{'id': unknown['id'], 'reason': 'Checked', 'page': 1}]).status_code == 409
    assert save(env, invoice_id, evidence_resolutions=[{'id': ocr['id'], 'reason': 'Checked', 'page': 1}]).status_code == 200
    assert decide(env, invoice_id).status_code == 422


def test_final_snapshot_and_exact_request_replay_are_stable(env):
    invoice_id, attempt = seed(env, number='LATER-DUPLICATE')
    save(env, invoice_id)
    body = {'expected_revision': 1, 'processing_attempt_id': attempt, 'decision': 'approve', 'request_id': 'stable', 'reason': 'Checked'}
    endpoint = f'/api/ap/invoices/{invoice_id}/review/decision'
    original = env[0].post(endpoint, headers=HEADERS, json=body).json()
    seed(env, number='LATER-DUPLICATE')
    replay = env[0].post(endpoint, headers=HEADERS, json=body).json()
    assert replay['validation'] == original['validation']
    assert replay['event'] == original['event']
    assert replay['current_revision'] == original['current_revision']
    assert not replay['decision_gate']['can_approve']
    assert decide(env, invoice_id, 'reject').status_code == 409


def test_decision_prerequisites_are_visible_and_enforced(env):
    invoice_id, _ = seed(env)
    assert state(env, invoice_id)['decision_gate']['blockers'][0]['code'] == 'REVIEW_NOT_SAVED'
    save(env, invoice_id)
    with closing(env[1]()) as db:
        db.execute("INSERT INTO processing_attempts(invoice_id,status) VALUES(?,'failed')", (invoice_id,))
        db.commit()
    gate = state(env, invoice_id)['decision_gate']
    assert {i['code'] for i in gate['blockers']} == {'PROCESSING_INCOMPLETE', 'ANALYSIS_VERSION_CONFLICT'}
    assert not gate['can_approve'] and not gate['can_reject']
    assert decide(env, invoice_id, 'reject').status_code == 409


@pytest.mark.parametrize('headers', [{}, {**HEADERS, 'Origin': 'null'}, {**HEADERS, 'Host': 'evil.invalid'}, {**HEADERS, 'Sec-Fetch-Site': 'cross-site'}])
def test_decision_write_protection(env, headers):
    invoice_id, attempt = seed(env)
    save(env, invoice_id)
    endpoint = f'/api/ap/invoices/{invoice_id}/review/decision'
    body = {'expected_revision': 1, 'processing_attempt_id': attempt, 'decision': 'approve', 'request_id': 'protected'}
    assert env[0].get(endpoint).status_code == 405
    assert env[0].post(endpoint, headers=headers, json=body).status_code == 403
    assert state(env, invoice_id)['status'] == 'pending'


def test_unsaved_resolutions_and_blank_replay_reason_are_rejected(env):
    invoice_id, _ = seed(env)
    save(env, invoice_id)
    response = decide(env, invoice_id, evidence_resolutions=[])
    assert response.status_code == 422 and 'Save changes' in response.text
    assert decide(env, invoice_id, 'reject').status_code == 200
    assert decide(env, invoice_id, 'reject', reason=' ').status_code == 422
