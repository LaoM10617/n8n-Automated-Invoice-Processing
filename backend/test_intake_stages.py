"""Stage contract, isolation, deterministic parity and notification recovery tests."""
from concurrent.futures import ThreadPoolExecutor
import json
import sqlite3
import smtplib
import pytest
from fastapi.testclient import TestClient
from backend.app import create_app
from backend.test_review import FIXTURE
from backend.test_processing import fields
from backend.document_text import ProcessingError, QUALITY_VERSION


def setup(monkeypatch):
    import backend.app as app
    import backend.document_stages as stages
    raw = fields(total_amount='129.00')
    pages = [{'page':1,'text':'\n'.join(v for v in raw.values() if isinstance(v,str)), 'ocr_confidence':None, 'quality_rule':QUALITY_VERSION}]
    draft = {'fields':raw,'evidence':[{'field':k,'page':1,'quote':v} for k,v in raw.items() if isinstance(v,str)],'uncertainties':[]}
    calls=[]
    monkeypatch.setattr(app,'read_pages',lambda *_:pages)
    monkeypatch.setattr(app,'extract_fields',lambda _: calls.append(1) or draft)
    monkeypatch.setattr(stages,'wait_for_model_cooldown',lambda:None)
    return calls


def archive(c, sid='m1', attachment='0', data=None, mime='application/pdf'):
    source=dict(source_type='email',source_namespace='stage-test',source_id=sid,attachment_id=attachment,batch_id='stage-batch',case_id='mixed')
    return c.post('/api/ap/stages/archive',data={'metadata':json.dumps(source)},files={'file':('invoice.pdf',FIXTURE.read_bytes() if data is None else data,mime)}).json()


def advance(c,r):
    for stage in ['analyze','validate']:
        response=c.post(f"/api/ap/stages/{r['run_id']}/{stage}");assert response.status_code==200
        r=response.json()
    return r


def test_stage_parity_replay_isolation_and_persistence(tmp_path,monkeypatch):
    calls=setup(monkeypatch)
    with TestClient(create_app(tmp_path)) as c:
        a=archive(c)
        assert c.post(f"/api/ap/stages/{a['run_id']}/validate").status_code==409
        a=advance(c,a)
        assert a['outcome']=='review_ready' and 'TOTAL_MISMATCH' in a['issue_codes']
        before=c.get('/api/ap/invoices/'+a['invoice_id']).json()
        assert c.post('/api/ap/invoices/'+a['invoice_id']+'/process').json()==before
        b=advance(c,archive(c));new=advance(c,archive(c,'m2'))
        assert b['receipt_id']==a['receipt_id'] and new['receipt_id']!=a['receipt_id']
        assert b['review_id']==new['review_id']==a['review_id'] and len(calls)==1
        bad=advance(c,archive(c,attachment='1',data=b'broken'))
        skip=advance(c,archive(c,attachment='2',data=b'notes',mime='text/plain'))
        for r in [bad,skip]:assert r['invoice_id'] is None and r['receipt_id'] is None
        assert bad['error_code']=='HTTP_422' and skip['outcome']=='skipped'
        batch=c.get('/api/ap/email-batches/stage-batch').json()
        assert (batch['messages'],batch['receipts'],batch['failed_items'],batch['skipped_items'])==(2,2,1,1)
        with sqlite3.connect(tmp_path/'invoices.sqlite3') as db:
            assert db.execute('SELECT COUNT(*) FROM intake_stage_events WHERE run_id=?',(bad['run_id'],)).fetchone()[0]>=2
    with TestClient(create_app(tmp_path)) as c:
        assert c.get('/api/ap/stages/'+a['run_id']).json()==a
        assert advance(c,archive(c))['review_id']==a['review_id']


def test_stage_provider_failure_saved_before_exception_node(tmp_path,monkeypatch):
    setup(monkeypatch)
    import backend.app as module
    def fail(_):raise ProcessingError('MODEL_RATE_LIMITED','test-only quota failure')
    monkeypatch.setattr(module,'extract_fields',fail)
    with TestClient(create_app(tmp_path)) as c:
        r=advance(c,archive(c));assert r['outcome']=='failed' and r['retryable']
        assert c.get('/api/ap/email-batches/stage-batch').json()['failed_items']==1
        assert c.get('/api/ap/stages/'+r['run_id']).json()['error_code']=='MODEL_RATE_LIMITED'
        assert c.post('/api/ap/stages/'+r['run_id']+'/notify').status_code==409


def test_stage_notification_failure_retry_concurrency_and_uncertainty(tmp_path,monkeypatch):
    setup(monkeypatch)
    import backend.intake_stages as module
    state={'mode':'connect_fail','sent':0}
    class SMTP:
        def __init__(self,*args,**kwargs):
            if state['mode']=='connect_fail':raise ConnectionRefusedError()
        def send_message(self,message):
            if state['mode']=='uncertain':raise TimeoutError()
            state['sent']+=1
            assert '/reviews/' in message.get_content()
            return {}
        def close(self):pass
    monkeypatch.setattr(module.smtplib,'SMTP',SMTP)
    with TestClient(create_app(tmp_path)) as c:
        r=advance(c,archive(c));url='/api/ap/stages/'+r['run_id']+'/notify'
        failed=c.post(url).json();assert failed['outcome']=='review_ready' and failed['notification_status']=='failed'
        state['mode']='ok'
        with ThreadPoolExecutor(max_workers=3) as pool:results=list(pool.map(lambda _:c.post(url).json(),range(3)))
        assert state['sent']==1 and all(x['review_id']==r['review_id'] for x in results)
        notices=c.get('/api/ap/invoices/'+r['invoice_id']+'/notifications').json();assert [x['status'] for x in notices]==['failed','sent']
    # A second isolated store tests uncertain delivery without resetting prior records.
    with TestClient(create_app(tmp_path/'uncertain')) as c:
        r=advance(c,archive(c));url='/api/ap/stages/'+r['run_id']+'/notify';state['mode']='uncertain'
        assert c.post(url).json()['notification_status']=='unknown'
        state['mode']='ok';assert c.post(url).json()['notification_status']=='unknown';assert state['sent']==1

def test_cooldown_wait_is_bounded_and_does_not_call_provider(monkeypatch):
    import backend.extraction as module
    slept=[]
    monkeypatch.setattr(module.time,'monotonic',lambda:100)
    monkeypatch.setattr(module.time,'sleep',lambda n:slept.append(n))
    monkeypatch.setattr(module,'_next_request_at',160)
    module.wait_for_model_cooldown();assert slept==[60]
    monkeypatch.setattr(module,'_next_request_at',200)
    with pytest.raises(ProcessingError):module.wait_for_model_cooldown()
    assert slept==[60]
