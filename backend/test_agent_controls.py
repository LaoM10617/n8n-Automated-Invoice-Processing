"""Offline acceptance of agent controls, including an abruptly terminated process."""
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import pytest
from fastapi.testclient import TestClient
from backend import invoice_agent as agent
from backend import extraction
from backend.app import create_app
from backend.document_stages import DocumentStages, PIPELINE
from backend.document_text import ProcessingError
from backend.test_invoice_agent import ScriptedModel


def test_every_model_round_and_next_analysis_are_paced(monkeypatch):
    clock=[100.0]
    monkeypatch.setattr(extraction,'_next_request_at',0)
    monkeypatch.setenv('AP_LLM_MIN_INTERVAL_SECONDS','0')
    monkeypatch.setattr(extraction.time,'monotonic',lambda:clock[0])
    monkeypatch.setattr(extraction.time,'sleep',lambda seconds:clock.__setitem__(0,clock[0]+seconds))
    starts=[]
    reserve=extraction.reserve_model_request
    def record_reservation():
        reserve();starts.append(clock[0])
    monkeypatch.setattr(agent,'reserve_model_request',record_reservation)
    monkeypatch.setattr(agent,'make_model',lambda:ScriptedModel())
    for _ in range(2):agent.extract_fields([{'page':1,'text':'Offline invoice'}])
    assert len(starts)==4
    assert all(b-a>=60 for a,b in zip(starts,starts[1:]))
    assert starts==pytest.approx([100,160.1,220.2,280.3])


def test_exact_model_budget_and_final_request_tools(monkeypatch):
    class ObservedModel(ScriptedModel):
        def bind_tools(self, tools, **kwargs):
            bindings.append([getattr(t,'name',None) for t in tools]);return self
    bindings=[]
    model=ObservedModel(loop=True)
    monkeypatch.setattr(agent,'make_model',lambda:model)
    monkeypatch.setattr(agent,'wait_for_model_cooldown',lambda:None)
    monkeypatch.setattr(agent,'reserve_model_request',lambda:None)
    traces=[];token=agent.trace_sink.set(traces.append)
    try:
        with pytest.raises(ProcessingError) as exc:agent.extract_fields([{'page':1,'text':'Test'}])
    finally:agent.trace_sink.reset(token)
    assert exc.value.code=='AGENT_MODEL_LIMIT'
    assert model._calls==3 and len(traces[-1]['model_calls'])==3
    assert bindings[-1]==['Extraction']
    assert traces[-1]['status']=='failed'


def test_tool_budget_has_no_seventh_record():
    trace={'tools':[]}
    tools,_=agent.build_tools([{'page':1,'text':'Test'}],trace,lambda:None)
    for _ in range(6):tools[2].invoke({})
    with pytest.raises(ProcessingError) as exc:tools[2].invoke({})
    assert exc.value.code=='AGENT_TOOL_LIMIT' and len(trace['tools'])==6


@pytest.mark.parametrize('key,value',[
    ('pipeline_version','old-pipeline'),('analysis_signature','old-signature'),
    ('model','other-model'),('model_base_url','https://other.invalid')])
def test_each_cache_identity_change_invalidates(key,value,monkeypatch):
    monkeypatch.setenv('AP_LLM_MODEL','test-model')
    monkeypatch.setenv('AP_LLM_BASE_URL','https://test.invalid')
    result={'pipeline_version':PIPELINE,'analysis_signature':agent.ANALYSIS_SIGNATURE,
            'model':'test-model','model_base_url':'https://test.invalid'}
    attempt={'status':'processed','result_json':json.dumps(result)}
    assert DocumentStages.reusable(None,attempt)
    valid_json=attempt['result_json']
    result[key]=value;attempt['result_json']=json.dumps(result)
    assert not DocumentStages.reusable(None,attempt)
    attempt['result_json']=valid_json
    for state in ['processing','failed']:
        attempt['status']=state
        assert not DocumentStages.reusable(None,attempt)


def test_process_exit_preserves_trace_and_restart_does_not_retry(tmp_path,monkeypatch):
    fixture=Path('test_data/first_round/text_pdf/04_invoice_A_business_duplicate.pdf').resolve()
    script='''
import os,json
from pathlib import Path
from fastapi.testclient import TestClient
import backend.app as module
from backend.invoice_agent import trace_sink
from backend.document_text import QUALITY_VERSION
root=Path(os.environ['AP_DATA_DIR'])
module.read_pages=lambda *_:[{'page':1,'text':'Offline invoice','quality_rule':QUALITY_VERSION,'ocr_confidence':None}]
def interrupted(_):
    trace_sink.get()({'status':'running','model_calls':[{'index':1,'status':'completed'},{'index':2,'status':'running'}],'tools':[{'tool':'read_invoice_page'}]})
    os._exit(73)
module.extract_fields=interrupted
with TestClient(module.create_app(root)) as c:
    source={'source_type':'upload','source_namespace':'interruption-test','source_id':'one','attachment_id':'0'}
    f=Path(os.environ['TEST_INVOICE'])
    r=c.post('/api/ap/stages/archive',data={'metadata':json.dumps(source)},files={'file':(f.name,f.read_bytes(),'application/pdf')}).json()
    (root/'run.json').write_text(json.dumps(r))
    c.post('/api/ap/stages/'+r['run_id']+'/analyze')
'''
    env={k:v for k,v in os.environ.items() if k not in ('AP_LLM_API_KEY','GOOGLE_API_KEY','GEMINI_API_KEY')}
    env.update(AP_DATA_DIR=str(tmp_path),TEST_INVOICE=str(fixture))
    child=subprocess.run([sys.executable,'-c',script],env=env,capture_output=True,timeout=30)
    assert child.returncode==73,child.stderr.decode(errors='replace')
    with sqlite3.connect(tmp_path/'invoices.sqlite3') as db:
        before=db.execute('SELECT status,result_json FROM processing_attempts').fetchone()
    assert before[0]=='processing' and json.loads(before[1])['agent_trace']['status']=='running'
    def unexpected(_):pytest.fail('Restart must not invoke a model')
    monkeypatch.setattr('backend.app.extract_fields',unexpected)
    with TestClient(create_app(tmp_path)) as c:
        run=json.loads((tmp_path/'run.json').read_text())
        current=c.get('/api/ap/invoices/'+run['invoice_id']).json()
        assert current['processing_status']=='failed'
        trace=current['processing_result']['agent_trace']
        assert trace['status']=='interrupted' and trace['error_code']=='PROCESS_INTERRUPTED'
        assert [call['status'] for call in trace['model_calls']]==['completed','unknown']
        assert trace['tools']==[{'tool':'read_invoice_page'}]
        assert c.post('/api/ap/stages/'+run['run_id']+'/validate').status_code==409
        assert c.post('/api/ap/stages/'+run['run_id']+'/notify').status_code==409
    with sqlite3.connect(tmp_path/'invoices.sqlite3') as db:
        assert db.execute('SELECT count(*) FROM processing_attempts').fetchone()[0]==1
        assert db.execute('SELECT count(*) FROM review_tasks').fetchone()[0]==0
        assert db.execute('SELECT count(*) FROM notification_attempts').fetchone()[0]==0
    # Starting again must not overwrite the preserved interruption evidence.
    with TestClient(create_app(tmp_path)) as c:
        assert c.get('/api/ap/invoices/'+run['invoice_id']).json()['processing_result']['agent_trace']==trace
