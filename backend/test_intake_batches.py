"""Batch waiting, live decisions and local-notice idempotency without model calls."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import json
from uuid import uuid4

import pytest
from fastapi import HTTPException

from backend.intake_batches import BatchMembers, IntakeBatches
from backend.outcomes import Outcomes
from backend.reviews import Reviews
from backend.test_review_decisions import env, seed, save, decide


def run(env, invoice=None, outcome='review_ready', new=True, mode='batch'):
    run_id = str(uuid4())
    result = {'run_id': run_id, 'source': {'source_type': 'upload', 'notification_mode': mode},
              'invoice_id': invoice, 'outcome': outcome, 'new_invoice': new}
    with closing(env[1]()) as db:
        db.execute('INSERT INTO intake_runs(run_id,result_json) VALUES(?,?)', (run_id, json.dumps(result)))
        db.commit()
    return run_id


def test_mixed_batch_waits_then_summarizes_current_decisions_once(env):
    low, _ = seed(env, task=False)
    Reviews(env[1]).automatic(low, new_only=True)
    high, _ = seed(env, total='11900.00')
    rejected, _ = seed(env, total='15000.00')
    messages = []
    service = IntakeBatches(env[1], lambda m: (messages.append(m) or ('sent', None)))
    members = BatchMembers(run_ids=[run(env, low, 'decision_ready'), run(env, high), run(env, rejected),
                                   run(env, outcome='failed'), run(env, outcome='skipped')])
    state = service.create(members)
    batch_id = state['batch_id']
    assert service.create(members)['batch_id'] == batch_id
    assert (state['approved'], state['pending'], state['failed_items'], state['skipped_items']) == (1, 2, 1, 1)
    assert not state['complete']
    with pytest.raises(HTTPException):
        service.notify(batch_id, 'summary')
    service.notify(batch_id, 'pending')
    service.notify(batch_id, 'pending')
    assert len(messages) == 1 and '/reviews/' + high in messages[0].get_content()
    assert save(env, high).status_code == 200
    assert decide(env, high).status_code == 200
    assert save(env, rejected).status_code == 200
    assert decide(env, rejected, 'reject').status_code == 200
    final = service.read(batch_id)
    assert final['complete'] and (final['approved'], final['rejected'], final['pending']) == (2, 1, 0)
    service.notify(batch_id, 'summary')
    service.notify(batch_id, 'summary')
    assert len(messages) == 2
    with closing(env[1]()) as db:
        assert db.execute('SELECT COUNT(*) FROM export_batches').fetchone()[0] == 0
        assert db.execute("SELECT COUNT(*) FROM review_events WHERE status='processed'").fetchone()[0] == 3
    exported = env[0].get('/api/ap/export-register').json()
    assert {r['invoice_id'] for r in exported['rows']} == {low, high}


def test_cached_batch_is_not_new_and_does_not_wait(env):
    invoice, _ = seed(env, task=False)
    Reviews(env[1]).automatic(invoice, new_only=True)
    service = IntakeBatches(env[1], lambda _: ('sent', None))
    state = service.create(BatchMembers(run_ids=[run(env, invoice, 'decision_ready', False),
                                               run(env, invoice, 'decision_ready', False)]))
    assert state['attachments'] == 2 and state['unique_invoices'] == 1
    assert state['new_invoices'] == 0 and state['reused_invoices'] == 1
    assert state['complete'] and state['approved'] == 1
    assert service.notify(state['batch_id'], 'pending')['notices'] == {}
    assert service.notify(state['batch_id'], 'summary')['notices']['summary']['status'] == 'sent'


def test_pending_membership_is_fixed_and_unfinished_processing_is_blocked(env):
    invoice, _ = seed(env)
    service = IntakeBatches(env[1])
    with pytest.raises(HTTPException):
        service.create(BatchMembers(run_ids=[run(env, invoice, 'continue')]))
    first = service.create(BatchMembers(run_ids=[run(env, invoice)]))
    other, _ = seed(env)
    service.create(BatchMembers(run_ids=[run(env, other)]))
    assert service.read(first['batch_id'])['pending'] == 1


def test_notice_parallel_claim_and_uncertain_send_never_repeat(env):
    invoice, _ = seed(env)
    messages = []
    service = IntakeBatches(env[1], lambda m: (messages.append(m) or ('unknown', 'SMTP_DELIVERY_UNCERTAIN')))
    batch_id = service.create(BatchMembers(run_ids=[run(env, invoice)]))['batch_id']
    def attempt(_):
        try:
            return service.notify(batch_id, 'pending')
        except HTTPException as exc:
            return exc.status_code
    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(attempt, range(3)))
    assert len(messages) == 1 and all(r in (409, 503) for r in results)
    restarted = IntakeBatches(env[1], lambda _: pytest.fail('Unknown notice must not resend'))
    assert restarted.read(batch_id)['notices']['pending']['status'] == 'unknown'
    with pytest.raises(HTTPException):
        restarted.notify(batch_id, 'pending')


def test_batch_review_uses_summary_and_legacy_dispatch_still_works(env, monkeypatch):
    invoice, _ = seed(env, task=False)
    task = Reviews(env[1]).automatic(invoice, new_only=True)
    run(env, invoice, 'decision_ready')
    monkeypatch.setenv('AP_REVIEW_EVENT_URL', 'http://n8n:5678/webhook/test')
    outcomes = Outcomes(env[1], env[2])
    calls = []
    outcomes.events.deliver = lambda event: calls.append(event) or {'status': 'accepted'}
    assert outcomes.dispatch_review(task['event']['event_id'])['notification_mode'] == 'batch'
    assert calls == []
    run(env, invoice, 'decision_ready', mode='invoice')
    assert outcomes.dispatch_review(task['event']['event_id'])['status'] == 'accepted'
    assert len(calls) == 1
