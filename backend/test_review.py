"""Persistent review-task behavior; no real model calls."""
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import sqlite3

from fastapi.testclient import TestClient
from backend.app import create_app

FIXTURE = Path(__file__).resolve().parents[1] / 'test_data/first_round/text_pdf/01_invoice_A.pdf'


def intake(client):
    return client.post('/api/ap/intakes', data={'source_type':'upload','source_namespace':'review-test','source_id':'one','attachment_id':'0'}, files={'file':('invoice.pdf',FIXTURE.read_bytes())}).json()['invoice_id']


def seed(root, invoice_id, status='processed'):
    fields={'supplier_name':'<script>alert(1)</script>', 'invoice_number':'TEST-1', 'currency':'EUR','total_amount':'119.00'}
    result={'fields':fields,'validation_issues':[{'code':'MISSING_FIELD','field':'due_date','message':'Date missing <b>check</b>'}], 'raw_extraction':{'evidence':[]},'model':'test-double'}
    with sqlite3.connect(root/'invoices.sqlite3') as db:
        db.execute('INSERT INTO processing_attempts(invoice_id,status,result_json) VALUES(?,?,?)',(invoice_id,status,json.dumps(result) if status=='processed' else '{}'))


def test_review_requires_success_and_get_does_not_create(tmp_path):
    with TestClient(create_app(tmp_path)) as c:
        invoice_id=intake(c); endpoint=f'/api/ap/invoices/{invoice_id}/review-task'
        assert c.get(f'/reviews/{invoice_id}').status_code==404
        assert c.post(endpoint).status_code==409
        seed(tmp_path,invoice_id,'failed')
        assert c.post(endpoint).status_code==409
        assert c.get('/api/ap/invoices/'+invoice_id).json()['review_status']=='not_created'
        assert c.post('/api/ap/invoices/nonexistent/review-task').status_code==404


def test_review_idempotent_concurrent_persistent_and_safe(tmp_path,monkeypatch):
    monkeypatch.setenv('AP_PUBLIC_BASE_URL','http://127.0.0.1:8000')
    with TestClient(create_app(tmp_path)) as c:
        invoice_id=intake(c);seed(tmp_path,invoice_id)
        endpoint=f'/api/ap/invoices/{invoice_id}/review-task'
        with ThreadPoolExecutor(max_workers=4) as pool:
            responses=list(pool.map(lambda _:c.post(endpoint),range(4)))
        assert sorted(r.status_code for r in responses)==[200,200,200,201]
        tasks=[r.json() for r in responses]
        assert len({t['review_id'] for t in tasks})==1
        assert tasks[0]['review_status']=='pending'
        assert tasks[0]['review_url']==f'http://127.0.0.1:8000/reviews/{invoice_id}'
        page=c.get('/reviews/'+invoice_id)
        assert page.status_code==200 and 'Original invoice page 1' in page.text
        assert '<script>alert(1)</script>' not in page.text
        assert '&lt;script&gt;alert(1)&lt;/script&gt;' in page.text
        assert 'Date missing &lt;b&gt;check&lt;/b&gt;' in page.text
        assert 'read-only' in page.text and 'No rule exceptions' not in page.text
        assert page.headers['cache-control']=='no-store'
        assert c.get('/api/ap/invoices/'+invoice_id).json()['review_id']==tasks[0]['review_id']
    with TestClient(create_app(tmp_path)) as c:
        assert c.post(endpoint).json()['review_id']==tasks[0]['review_id']
        assert c.get('/reviews/'+invoice_id).status_code==200
        assert c.get(f'/api/ap/invoices/{invoice_id}/original').content==FIXTURE.read_bytes()
        seed(tmp_path,invoice_id,'failed')
        assert 'Current processing is incomplete' in c.get('/reviews/'+invoice_id).text
        assert c.post(endpoint).status_code==409
