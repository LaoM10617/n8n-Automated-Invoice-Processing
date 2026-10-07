"""Notification state and concurrency tests without SMTP or model calls."""
from concurrent.futures import ThreadPoolExecutor
from fastapi.testclient import TestClient
from backend.app import create_app
from backend.test_review import intake, seed


def test_notification_failure_retry_and_replay(tmp_path):
    with TestClient(create_app(tmp_path)) as c:
        invoice_id = intake(c)
        url = f'/api/ap/invoices/{invoice_id}/notifications'
        assert c.post(url + '/claim').status_code == 409
        seed(tmp_path, invoice_id)
        task = c.post(f'/api/ap/invoices/{invoice_id}/review-task').json()
        claim = c.post(url + '/claim').json()
        assert claim['send_required'] and task['review_url'] in claim['text']
        assert c.post(url + '/claim').json()['send_required'] is False
        result_url = '/api/ap/notifications/' + claim['notification_id'] + '/result'
        assert c.post(result_url, json={'status':'failed','error_code':'ECONNREFUSED'}).status_code == 200
        retry = c.post(url + '/claim').json()
        assert retry['send_required'] and retry['notification_id'] != claim['notification_id']
        result_url = '/api/ap/notifications/' + retry['notification_id'] + '/result'
        assert c.post(result_url, json={'status':'sent'}).status_code == 422
        assert c.post(result_url, json={'status':'sent','message_id':'<local@test.invalid>'}).status_code == 200
        assert c.post(result_url, json={'status':'failed'}).status_code == 409
        assert c.post(url + '/claim').json()['send_required'] is False
        assert c.post(f'/api/ap/invoices/{invoice_id}/review-task').json()['review_id'] == task['review_id']
    with TestClient(create_app(tmp_path)) as c:
        assert [a['status'] for a in c.get(url).json()] == ['failed', 'sent']
        assert not c.post(url + '/claim').json()['send_required']


def test_notification_concurrent_and_uncertain(tmp_path):
    with TestClient(create_app(tmp_path)) as c:
        invoice_id = intake(c)
        seed(tmp_path, invoice_id)
        c.post(f'/api/ap/invoices/{invoice_id}/review-task')
        url = f'/api/ap/invoices/{invoice_id}/notifications'
        with ThreadPoolExecutor(max_workers=4) as pool:
            claims = list(pool.map(lambda _: c.post(url + '/claim').json(), range(4)))
        assert sum(r['send_required'] for r in claims) == 1
        result_url = '/api/ap/notifications/' + claims[0]['notification_id'] + '/result'
        assert c.post(result_url, json={'status':'unknown','error_code':'ETIMEDOUT'}).status_code == 200
        assert not c.post(url + '/claim').json()['send_required']
        assert len(c.get(url).json()) == 1
