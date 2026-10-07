"""Email batch counts use stable source identities rather than execution counts."""
from fastapi.testclient import TestClient
from backend.app import create_app
from backend.test_review import FIXTURE, seed


def test_email_batch_replay_new_message_and_invalid_item(tmp_path):
    with TestClient(create_app(tmp_path)) as c:
        source = {'source_type':'email','source_namespace':'test:inbox','source_id':'m1','attachment_id':'attachment_0'}
        saved = c.post('/api/ap/intakes', data=source, files={'file':('invoice.pdf',FIXTURE.read_bytes())}).json()
        seed(tmp_path, saved['invoice_id'])
        c.post('/api/ap/invoices/' + saved['invoice_id'] + '/review-task')
        outcome = {k:source[k] for k in ('source_namespace','source_id','attachment_id')}
        outcome.update(batch_id='batch-1',case_id='single',status='review_ready',reason_code='PENDING_REVIEW',
                       receipt_id=saved['receipt_id'],invoice_id=saved['invoice_id'])
        for _ in range(2):
            assert c.post('/api/ap/email-outcomes', json=outcome).status_code == 200
        wrong = {**outcome,'source_id':'wrong'}
        assert c.post('/api/ap/email-outcomes', json=wrong).status_code == 409
        source['source_id'] = 'm2'
        second = c.post('/api/ap/intakes', data=source, files={'file':('invoice.pdf',FIXTURE.read_bytes())}).json()
        assert second['invoice_id'] == saved['invoice_id'] and second['receipt_id'] != saved['receipt_id']
        c.post('/api/ap/email-outcomes', json={**outcome,'source_id':'m2','receipt_id':second['receipt_id']})
        c.post('/api/ap/email-outcomes', json={**outcome,'source_id':'m3','status':'intake_failed',
                                            'reason_code':'HTTP_422','receipt_id':None,'invoice_id':None})
        batch = c.get('/api/ap/email-batches/batch-1').json()
        assert (batch['messages'],batch['receipts'],batch['unique_invoices'],batch['review_tasks'],batch['failed_items']) == (3,2,1,1,1)
    with TestClient(create_app(tmp_path)) as c:
        assert c.get('/api/ap/email-batches/batch-1').json()['receipts'] == 2
