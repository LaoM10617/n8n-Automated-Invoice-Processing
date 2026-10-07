"""Outcome notification claims, transport handoff and independent failure recovery."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from io import BytesIO
import json
import sqlite3
from uuid import uuid4

from fastapi import HTTPException
import pytest

from backend.outcomes import Outcomes
from backend.review_events import ReviewEvents
from backend.test_exports import approved
from backend.test_export_register import batch
from backend.test_review_decisions import env, seed, save, decide, HEADERS


@pytest.mark.parametrize('decision', ['approved', 'rejected'])
def test_result_notification_and_processed_are_idempotent(env, decision):
    if decision == 'approved':
        invoice, _, event = approved(env)
    else:
        invoice, _ = seed(env)
        save(env, invoice)
        event = decide(env, invoice, 'reject').json()['event']['event_id']
    messages = []
    def send(message):
        with closing(env[1]()) as db:
            assert db.execute('SELECT status,message_id FROM outcome_notifications').fetchone()[:] == ('sending', message['Message-ID'])
            assert db.execute('SELECT status FROM review_events').fetchone()[0] != 'processed'
        messages.append(message)
        return 'sent', None
    service = Outcomes(env[1], env[2], send)
    first = service.send('review', event)
    assert first['status'] == 'sent' and service.send('review', event) == first
    assert len(messages) == 1 and messages[0]['To'] == 'reviewer@example.invalid'
    assert '/reviews/' + invoice in messages[0].get_content()
    assert ('Export register:' in messages[0].get_content()) == (decision == 'approved')
    with closing(env[1]()) as db:
        assert db.execute('SELECT status FROM review_events').fetchone()[0] == 'processed'
        assert db.execute('SELECT COUNT(*) FROM export_batches').fetchone()[0] == 0


def test_batch_notice_failure_never_rebuilds_excel(env):
    record = batch(env, [approved(env)[2]]).json()
    path = env[2] / record['file_path']
    original = path.read_bytes()
    service = Outcomes(env[1], env[2], lambda _: ('failed', 'SMTP_CONNECTION_FAILED'))
    assert service.send('batch', record['export_id'])['status'] == 'failed'
    seen = []
    service.sender = lambda message: (seen.append(message) or ('sent', None))
    recovered = service.send('batch', record['export_id'])
    assert recovered['attempts'] == 2 and record['download_url'] in seen[0].get_content()
    assert path.read_bytes() == original
    with closing(env[1]()) as db:
        assert db.execute('SELECT attempts FROM export_batches').fetchone()[0] == 1
        assert db.execute('SELECT COUNT(*) FROM outcome_notification_attempts').fetchone()[0] == 2


def test_unknown_or_interrupted_smtp_never_resends_without_reconciliation(env, monkeypatch):
    event = approved(env)[2]
    service = Outcomes(env[1], env[2], lambda _: ('unknown', 'SMTP_DELIVERY_UNCERTAIN'))
    row = service.send('review', event)
    service.sender = lambda _: pytest.fail('Uncertain SMTP must not resend')
    with pytest.raises(HTTPException) as blocked:
        service.send('review', event)
    assert blocked.value.status_code == 409
    with pytest.raises(HTTPException):
        service.reconcile('review', event)
    with closing(env[1]()) as db:
        db.execute("UPDATE outcome_notifications SET updated_at='2000-01-01T00:00:00+00:00'")
        db.commit()
    class Mailpit:
        def open(self, url, timeout):
            assert 'message-id%3A' in url
            return BytesIO(json.dumps({'messages': [{'MessageID': row['message_id'].strip('<>')}]}).encode())
    monkeypatch.setattr('backend.outcomes.urllib.request.build_opener', lambda *args: Mailpit())
    result = service.reconcile('review', event)
    assert result['status'] == 'sent' and result['attempts'] == 1
    assert service.events.read(event)['business_processed']


def test_missing_mailpit_message_remains_unknown(env, monkeypatch):
    event = approved(env)[2]
    service = Outcomes(env[1], env[2], lambda _: ('unknown', 'SMTP_DELIVERY_UNCERTAIN'))
    service.send('review', event)
    with closing(env[1]()) as db:
        db.execute("UPDATE outcome_notifications SET updated_at='2000-01-01T00:00:00+00:00'")
        db.commit()
    class Mailpit:
        def open(self, *args, **kwargs):
            return BytesIO(b'{"messages":[]}')
    monkeypatch.setattr('backend.outcomes.urllib.request.build_opener', lambda *args: Mailpit())
    assert service.reconcile('review', event)['last_error'] == 'MAILPIT_NOT_CONFIRMED'
    assert not service.events.read(event)['business_processed']


def test_delayed_sender_cannot_downgrade_confirmed_delivery(env):
    event = approved(env)[2]
    service = Outcomes(env[1], env[2], lambda _: ('sent', None))
    row = service.send('review', event)
    with closing(env[1]()) as db:
        service.finish(db, row, 'unknown', 'LATE_RESPONSE')
        db.commit()
    assert service.read('review', event)['status'] == 'sent'
    with closing(env[1]()) as db:
        assert db.execute('SELECT status FROM outcome_notification_attempts').fetchone()[0] == 'sent'


def test_process_interruption_leaves_durable_message_identity(env):
    event = approved(env)[2]
    def crash(message):
        raise SystemExit()
    service = Outcomes(env[1], env[2], crash)
    with pytest.raises(SystemExit):
        service.send('review', event)
    saved = service.read('review', event)
    assert saved['status'] == 'sending' and saved['message_id'] and saved['attempts'] == 1
    with pytest.raises(HTTPException):
        service.send('review', event)


def test_notification_parallel_claim_and_bounded_failures(env):
    event = approved(env)[2]
    service = Outcomes(env[1], env[2], lambda _: ('sent', None))
    def send(_):
        try:
            return service.send('review', event)['status']
        except HTTPException as exc:
            return exc.status_code
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(send, range(4)))
    assert all(r in ('sent', 409) for r in results)
    assert service.read('review', event)['attempts'] == 1
    second = approved(env)[2]
    service.sender = lambda _: ('failed', 'SMTP_CONNECTION_FAILED')
    for _ in range(5):
        assert service.send('review', second)['status'] == 'failed'
    with pytest.raises(HTTPException):
        service.send('review', second)


def test_forged_stale_and_missing_batch_cannot_notify(env):
    event = approved(env)[2]
    service = Outcomes(env[1], env[2], lambda _: pytest.fail('No mail for invalid state'))
    with pytest.raises(HTTPException):
        service.send('review', str(uuid4()))
    record = batch(env, [event]).json()
    (env[2] / record['file_path']).unlink()
    with pytest.raises(HTTPException):
        service.send('batch', record['export_id'])
    with closing(env[1]()) as db:
        db.execute('UPDATE review_tasks SET current_revision=current_revision+1')
        db.commit()
    with pytest.raises(HTTPException):
        service.send('review', event)


def test_outcome_api_auth_and_read_only_resolution(env, monkeypatch):
    event = approved(env)[2]
    monkeypatch.setenv('AP_REVIEW_EVENT_TOKEN', 'test-token')
    url = '/api/ap/outcomes/review/' + event
    assert env[0].get(url).status_code == 403
    result = env[0].get(url, headers={'X-AP-Event-Token': 'test-token'})
    assert result.json() == {'kind': 'review', 'id': event, 'category': 'review_approved'}
    assert env[0].post(url + '/notify').status_code == 403
    assert env[0].post('/api/ap/result-notifications/review/' + event + '/retry').status_code == 403
    assert env[0].post('/api/ap/result-notifications/review/' + event + '/retry', headers={**HEADERS, 'Origin': 'http://evil.invalid'}).status_code == 403
    with closing(env[1]()) as db:
        assert db.execute('SELECT COUNT(*) FROM outcome_notifications').fetchone()[0] == 0


def test_background_manual_decision_handoff_occurs_after_commit(env, monkeypatch):
    invoice, _ = seed(env)
    save(env, invoice)
    calls = []
    def delivered(service, event_id):
        calls.append(event_id)
        assert service.read(event_id)['review_status'] == 'approved'
        return service.read(event_id)
    monkeypatch.setenv('AP_OUTCOME_AUTODISPATCH', '1')
    monkeypatch.setenv('AP_REVIEW_EVENT_URL', 'http://n8n:5678/webhook/ap-review-export-v1')
    monkeypatch.setattr(ReviewEvents, 'deliver', delivered)
    result = decide(env, invoice)
    assert result.status_code == 200 and calls == [result.json()['event']['event_id']]


def test_batch_transport_acceptance_is_not_notification_completion(env, monkeypatch):
    record = batch(env, [approved(env)[2]]).json()
    monkeypatch.setenv('AP_BATCH_EVENT_URL', 'http://n8n:5678/webhook/ap-batch-export-v1')
    monkeypatch.setenv('AP_REVIEW_EVENT_TOKEN', 'test-token')
    def accepted(url, token, payload):
        assert payload == {'export_id': record['export_id']}
        return 202
    monkeypatch.setattr('backend.outcomes.send_event', accepted)
    service = Outcomes(env[1], env[2])
    result = service.dispatch_batch(record['export_id'])
    assert result['delivery_status'] == 'accepted' and result['status'] == 'pending'
    for _ in range(4):
        service.dispatch_batch(record['export_id'])
    with pytest.raises(HTTPException):
        service.dispatch_batch(record['export_id'])


def test_schema_five_preserves_batch_membership_and_repeats(env):
    from backend.migrations import migrate
    record = batch(env, [approved(env)[2]]).json()
    with closing(env[1]()) as db:
        before = list(db.execute('SELECT * FROM export_batch_items'))
        db.execute('DROP TABLE outcome_notification_attempts')
        db.execute('DROP TABLE outcome_notifications')
        db.execute('PRAGMA user_version=4')
        db.commit()
        assert migrate(db) == 5 and migrate(db) == 5
        assert list(db.execute('SELECT * FROM export_batch_items')) == before
        assert not db.execute('PRAGMA foreign_key_check').fetchall()
    assert env[0].get(record['download_url']).status_code == 200
