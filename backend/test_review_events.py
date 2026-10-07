"""Transport failures must never undo a decision or mark business work complete."""
from contextlib import closing
from concurrent.futures import ThreadPoolExecutor
import threading

import pytest
from fastapi import HTTPException

from backend.review_events import ReviewEvents, IDENTIFIERS
from backend.test_review_decisions import env, seed, save, decide, state


@pytest.fixture
def event(env, monkeypatch):
    monkeypatch.setenv('AP_REVIEW_EVENT_URL', 'http://n8n:5678/webhook/ap-review-events-v1')
    monkeypatch.setenv('AP_REVIEW_EVENT_TOKEN', 'isolated-test-token')
    invoice_id, _ = seed(env)
    save(env, invoice_id)
    return decide(env, invoice_id).json()['event']['event_id']


def test_transport_recovery_reuses_event_and_preserves_decision(env, event):
    sent = []
    def unavailable(*args):
        raise OSError('Do not persist transport details or secrets')
    service = ReviewEvents(env[1], unavailable)
    assert service.deliver(event)['status'] == 'unknown'
    def accept(url, token, payload):
        # The outbox claim is committed and visible from another connection during I/O.
        with closing(env[1]()) as db:
            assert db.execute('SELECT status FROM review_events').fetchone()[0] == 'delivering'
        assert set(payload) == set(IDENTIFIERS)
        sent.append(payload)
        return 202
    service.sender = accept
    assert service.deliver(event)['status'] == 'accepted'
    assert service.deliver(event)['status'] == 'accepted'
    assert sent[0] == sent[1]
    with closing(env[1]()) as db:
        assert db.execute('SELECT COUNT(*) FROM review_events').fetchone()[0] == 1
        assert db.execute('SELECT status FROM review_tasks').fetchone()[0] == 'approved'
        assert db.execute('SELECT processed_at FROM review_events').fetchone()[0] is None
        assert db.execute('SELECT COUNT(*) FROM exports').fetchone()[0] == 0


def test_timeout_after_receiver_acceptance_and_limit(env, event):
    def lost_response(*args):
        raise TimeoutError()
    service = ReviewEvents(env[1], lost_response)
    for number in range(1, 6):
        result = service.deliver(event)
        assert result['attempts'] == number and result['status'] == 'unknown'
        assert result['last_error'] == 'TRANSPORT_UNCONFIRMED'
    with pytest.raises(HTTPException) as exc:
        service.deliver(event)
    assert exc.value.status_code == 409


def test_accepted_failure_can_be_redriven_and_http_error_visible(env, event):
    service = ReviewEvents(env[1], lambda *args: 202)
    assert not service.deliver(event)['business_processed']
    # Downstream execution can fail after acknowledgement; accepted is still replayable.
    service.sender = lambda *args: 503
    result = service.deliver(event)
    assert result['status'] == 'failed' and result['last_error'] == 'HTTP_503'
    service.sender = lambda *args: 202
    assert service.deliver(event)['status'] == 'accepted'


def test_live_claim_blocks_concurrent_delivery_and_expired_claim_recovers(env, event):
    started, release = threading.Event(), threading.Event()
    def delayed(*args):
        started.set()
        assert release.wait(10)
        return 202
    service = ReviewEvents(env[1], delayed)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(service.deliver, event)
        assert started.wait(10)
        try:
            with pytest.raises(HTTPException) as exc:
                service.deliver(event)
            assert exc.value.status_code == 409
        finally:
            release.set()
        assert future.result()['status'] == 'accepted'
    with closing(env[1]()) as db:
        db.execute("UPDATE review_events SET status='delivering',last_attempt_at='2000-01-01T00:00:00+00:00'")
        db.commit()
    assert ReviewEvents(env[1], lambda *args: 202).deliver(event)['attempts'] == 2


def test_authoritative_event_and_credential_checks(env, event):
    endpoint = '/api/ap/review-events/' + event
    assert env[0].get(endpoint).status_code == 403
    response = env[0].get(endpoint, headers={'X-AP-Event-Token': 'isolated-test-token'})
    assert response.status_code == 200 and response.json()['can_export']
    assert 'fields' not in response.json()
    assert env[0].get('/api/ap/review-events/forged', headers={'X-AP-Event-Token': 'isolated-test-token'}).status_code == 404
    with closing(env[1]()) as db:
        db.execute('UPDATE review_tasks SET current_revision=current_revision-1')
        db.commit()
    assert env[0].get(endpoint, headers={'X-AP-Event-Token': 'isolated-test-token'}).status_code == 409


def test_processed_event_does_not_send_and_missing_config_does_not_consume_attempt(env, event, monkeypatch):
    monkeypatch.delenv('AP_REVIEW_EVENT_TOKEN')
    service = ReviewEvents(env[1], lambda *args: pytest.fail('Unexpected delivery'))
    with pytest.raises(HTTPException) as exc:
        service.deliver(event)
    assert exc.value.status_code == 503
    assert service.read(event)['attempts'] == 0
    monkeypatch.setenv('AP_REVIEW_EVENT_TOKEN', 'test')
    with closing(env[1]()) as db:
        db.execute("UPDATE review_events SET status='processed'")
        db.commit()
    assert service.deliver(event)['status'] == 'processed'


def test_rejected_event_has_no_export_authorization(env, monkeypatch):
    invoice_id, _ = seed(env)
    save(env, invoice_id)
    event_id = decide(env, invoice_id, 'reject').json()['event']['event_id']
    assert not ReviewEvents(env[1]).read(event_id)['can_export']
