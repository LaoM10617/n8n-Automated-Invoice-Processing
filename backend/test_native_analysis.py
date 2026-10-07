"""Native analysis contracts and gateway faults, using an offline provider only."""
import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
import pytest
from fastapi.testclient import TestClient
from backend.app import create_app
from backend.test_intake_stages import setup, archive
from backend.native_analysis import proxy_key, MARKER
from backend.extraction import RawFields
from backend.model_gate import ModelGate
from backend.document_text import ProcessingError


@pytest.fixture
def env(tmp_path, monkeypatch):
    setup(monkeypatch)
    monkeypatch.setenv('AP_REVIEW_EVENT_TOKEN','native-offline-test-only')
    monkeypatch.setenv('AP_LLM_MODEL','gemini-3.5-flash-lite')
    monkeypatch.setenv('AP_LLM_BASE_URL','https://generativelanguage.googleapis.com/v1beta/openai')
    monkeypatch.setenv('AP_LLM_API_KEY','offline-not-a-provider-key')
    app = create_app(tmp_path)
    service = app.state.native_analysis
    now = [1000.0]
    service.clock = lambda:now[0]
    gate = service.documents.model_gate
    gate.clock = lambda:now[0]
    gate.sleep = lambda seconds:now.__setitem__(0,now[0]+seconds)
    with TestClient(app) as client:
        yield client, service, now, tmp_path


def start(c, sid='native'):
    run = archive(c,sid)
    response = c.post('/api/ap/native/'+run['run_id']+'/begin',headers={'X-AP-Event-Token':'native-offline-test-only'})
    assert response.status_code == 200, response.text
    return response.json()


def payload(r, turn=0):
    return {'systemInstruction':{'parts':[{'text':r['system_prompt']}]},
            'contents':[{'role':'user','parts':[{'text':str(turn)}]}],
            'tools':[{'functionDeclarations':[{'name':'Read_Invoice_Page','parameters':{'type':'object','properties':{'page_numbers':{'type':'array','items':{'type':'integer'}}}}}]}]}


def output():
    return {'fields':{key:None for key in RawFields.model_fields},'evidence':[],'uncertainties':['Offline synthetic test; not a quality evaluation.']}


def provider_result(draft):
    return {'candidates':[{'finishReason':'STOP','content':{'role':'model','parts':[{'text':json.dumps(draft)}]}}], 'usageMetadata':{'totalTokenCount':1}}


def test_native_commit_cache_and_deterministic_gate(env):
    c,s,now,root = env
    r = start(c)
    s.tool(r['scope'],'read',{'page_numbers':[1]})
    sent=[]
    def provider(model,body):
        sent.append(body)
        assert MARKER not in body['systemInstruction']['parts'][0]['text']
        return provider_result(output())
    s.provider=provider
    s.generate(r['model'],payload(r))
    done=s.commit(r['scope'],json.dumps(output()))
    assert done['extractor']=='n8n_native_agent' and not done['analysis_cached']
    reviewed=c.post('/api/ap/stages/'+r['run_id']+'/validate').json()
    assert reviewed['outcome']=='review_ready'
    assert s.commit(r['scope'],output())['stage']=='validate'
    cached=start(c,'cache')
    assert cached['native_action']=='cache_hit' and cached['analysis_cached']
    assert len(sent)==1
    with sqlite3.connect(root/'invoices.sqlite3') as db:
        assert db.execute('SELECT COUNT(*) FROM processing_attempts').fetchone()[0]==1
        assert db.execute('SELECT status FROM review_tasks').fetchone()[0]=='pending'


def test_provider_budget_and_durable_spacing(env):
    c,s,now,root=env
    r=start(c)
    starts=[]
    s.provider=lambda *_: starts.append(now[0]) or provider_result(output())
    for i in range(3):s.generate(r['model'],payload(r,i))
    with pytest.raises(Exception):s.generate(r['model'],payload(r,3))
    assert len(starts)==3 and all(b-a>=60 for a,b in zip(starts,starts[1:]))
    gate=ModelGate(s.connect,clock=lambda:now[0],sleep=lambda _:None)
    assert gate.remaining()>60
    with pytest.raises(ProcessingError):gate.reserve(60)
    assert c.post('/api/ap/stages/'+r['run_id']+'/validate').json()['outcome']=='failed'


def test_timeout_and_implicit_retry_never_forward_again(env):
    c,s,now,root=env
    r=start(c); sent=[]
    def timeout(*_):sent.append(1);raise TimeoutError()
    s.provider=timeout
    for _ in range(7):
        with pytest.raises(Exception):s.generate(r['model'],payload(r))
    assert sent==[1]
    row,result=s._row(r['scope'])
    assert row['status']=='failed' and result['agent_trace']['model_calls'][0]['status']=='unknown'
    with pytest.raises(Exception):s.commit(r['scope'],output())


@pytest.mark.parametrize('case',['bad_schema','missing_pages','tampered_output','wrong_model','external_tool','duplicate_request'])
def test_invalid_analysis_fails_closed(env,case):
    c,s,now,root=env;r=start(c)
    s.provider=lambda *_:provider_result(output())
    if case!='missing_pages':s.tool(r['scope'],'read',{'page_numbers':[1]})
    body=payload(r)
    if case=='external_tool':body['tools']=[{'googleSearch':{}}]
    if case in ('wrong_model','external_tool'):
        with pytest.raises(Exception):s.generate('wrong' if case=='wrong_model' else r['model'],body)
    else:
        s.generate(r['model'],body)
        with pytest.raises(Exception):
            if case=='duplicate_request':s.generate(r['model'],body)
            else:
                draft=output()
                if case=='bad_schema':draft['fields']['total_amount']=123
                if case=='tampered_output':draft['fields']['total_amount']='123'
                s.commit(r['scope'],draft)
    assert s._row(r['scope'])[0]['status']=='failed'
    with sqlite3.connect(root/'invoices.sqlite3') as db:
        assert db.execute('SELECT COUNT(*) FROM review_tasks').fetchone()[0]==0


def test_tool_scope_budget_and_auth(env):
    c,s,now,root=env;r=start(c)
    assert c.post('/api/ap/native/tools/read',json={'scope':r['scope'],'arguments':{'page_numbers':[1]}}).status_code==401
    headers={'X-AP-Native':proxy_key()}
    assert c.post('/api/ap/native/tools/read',headers=headers,json={'scope':'another','arguments':{'page_numbers':[1]}}).status_code==404
    for _ in range(6):s.tool(r['scope'],'quality',{'include_quality':True})
    with pytest.raises(Exception):s.tool(r['scope'],'quality',{'include_quality':True})
    assert len(s._row(r['scope'])[1]['agent_trace']['tools'])==6


def test_restart_preserves_unknown_and_old_attempts(env):
    c,s,now,root=env;r=start(c)
    row,result=s._row(r['scope'])
    result['agent_trace']['model_calls']=[{'status':'running','request_sha256':'offline'}]
    s._persist(row,result)
    app=create_app(root)
    other=app.state.native_analysis
    row,result=other._row(r['scope'])
    assert row['status']=='failed'
    assert result['agent_trace']['status']=='interrupted'
    assert result['agent_trace']['model_calls'][0]['status']=='unknown'
    with pytest.raises(Exception):other.generate(r['model'],payload(r))
    assert other.abort(r['run_id']).outcome=='failed'


def test_expiry_and_in_progress_are_not_restarted(env):
    c,s,now,root=env;r=start(c)
    with pytest.raises(Exception):s.begin(r['run_id'])
    now[0]+=1201
    with pytest.raises(Exception):s.tool(r['scope'],'read',{'page_numbers':[1]})
    assert s._row(r['scope'])[0]['status']=='failed'


def test_sqlite_gate_serializes_competing_executors(env):
    c,s,now,root=env
    a=ModelGate(s.connect,clock=lambda:now[0]);b=ModelGate(s.connect,clock=lambda:now[0])
    def reserve(gate):
        try:gate.reserve(60);return True
        except ProcessingError:return False
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(reserve,[a,b]))==[False,True]


def test_http_gateway_and_write_permission_separation(env):
    c,s,now,root=env;r=start(c)
    headers={'x-goog-api-key':proxy_key()}
    s.provider=lambda *_:provider_result(output())
    assert c.get('/api/ap/native/gemini/v1beta/models',headers=headers).status_code==200
    assert c.post('/api/ap/native/commit',headers=headers,json={'scope':r['scope'],'output':output()}).status_code==403
    response=c.post('/api/ap/native/gemini/v1beta/models/'+r['model']+':generateContent',headers=headers,json=payload(r))
    assert response.status_code==200 and response.json()['candidates'][0]['finishReason']=='STOP'
    assert c.post('/api/ap/native/gemini/v1beta/models/'+r['model']+':streamGenerateContent',headers=headers,json=payload(r)).status_code==400


def test_two_documents_have_distinct_scopes_and_read_results(env):
    c,s,now,root=env
    from backend.test_review import FIXTURE
    a=start(c)
    other=archive(c,'second',data=FIXTURE.read_bytes()+b'\n% isolated second document\n')
    b=s.begin(other['run_id'])
    assert a['invoice_id']!=b['invoice_id'] and a['scope']!=b['scope']
    row,result=s._row(b['scope'])
    result['pages'][0]['text']='Only second document evidence'
    s._persist(row,result)
    first=s.tool(a['scope'],'read',{'page_numbers':[1]})
    second=s.tool(b['scope'],'read',{'page_numbers':[1]})
    assert first['pages'][0]['text']!=second['pages'][0]['text']
    with pytest.raises(Exception):s.tool(a['scope'],'read',{'page_numbers':[1],'invoice_id':b['invoice_id']})
    assert s._row(b['scope'])[0]['status']=='processing'


def test_native_credential_test_query_is_not_logged():
    import logging
    from backend.native_analysis import NativeAccessFilter
    record=logging.LogRecord('uvicorn.access',20,'',0,'%s %s %s %s %s',
                             ('local','GET','/api/ap/native/gemini/v1beta/models?key=offline-secret','1.1',200),None)
    assert NativeAccessFilter().filter(record)
    assert 'offline-secret' not in record.getMessage() and '?key=' not in record.getMessage()


@pytest.mark.parametrize('status',[429,500])
def test_provider_http_error_has_one_intent_and_no_business_side_effect(env,status):
    from urllib.error import HTTPError
    c,s,now,root=env
    r=start(c); sent=[]
    def fail(*_):
        sent.append(1)
        raise HTTPError('https://provider.invalid',status,'offline fault',{},None)
    s.provider=fail
    for _ in range(3):
        with pytest.raises(Exception): s.generate(r['model'],payload(r))
    assert sent==[1]
    row,result=s._row(r['scope'])
    assert row['status']=='failed'
    assert result['agent_trace']['model_calls'][0]['status']=='unknown'
    assert s.abort(r['run_id']).outcome=='failed'
    with sqlite3.connect(root/'invoices.sqlite3') as db:
        for table in ('review_tasks','review_events','export_batches','outcome_notifications'):
            assert db.execute('SELECT count(*) FROM '+table).fetchone()[0]==0


def test_abrupt_process_exit_preserves_native_uncertain_request(env):
    import subprocess
    import sys
    c,s,now,root=env
    isolated=root/'abrupt-native'
    script=r'''
import sys,time
from pathlib import Path
from fastapi.testclient import TestClient
import backend.app as module
from backend.document_text import QUALITY_VERSION
from backend.test_intake_stages import archive
from backend.test_native_analysis import payload
module.read_pages=lambda *_:[{'page':1,'text':'Isolated native interruption sample','ocr_confidence':None,'quality_rule':QUALITY_VERSION}]
app=module.create_app(Path(sys.argv[1])); service=app.state.native_analysis
with TestClient(app) as client:
    run=archive(client,'native-abrupt')
    context=service.begin(run['run_id'])
    service.tool(context['scope'],'read',{'page_numbers':[1]})
    def blocked(*_):
        print('PROVIDER_IN_FLIGHT',flush=True)
        time.sleep(120)
    service.provider=blocked
    service.generate(context['model'],payload(context))
'''
    process=subprocess.Popen([sys.executable,'-c',script,str(isolated)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    from concurrent.futures import ThreadPoolExecutor
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            ready=pool.submit(process.stdout.readline).result(timeout=20)
        assert ready.strip()=='PROVIDER_IN_FLIGHT'
    finally:
        process.kill(); process.communicate(timeout=10)
    restarted=create_app(isolated)
    with sqlite3.connect(isolated/'invoices.sqlite3') as db:
        status,result=db.execute('SELECT status,result_json FROM processing_attempts').fetchone()
        result=json.loads(result)
        assert status=='failed' and result['agent_trace']['status']=='interrupted'
        assert result['agent_trace']['model_calls'][0]['status']=='unknown'
        scope,run_id=db.execute('SELECT scope,run_id FROM native_analysis').fetchone()
        assert db.execute('SELECT count(*) FROM review_events').fetchone()[0]==0
    assert restarted.state.native_analysis.abort(run_id).outcome=='failed'
    with pytest.raises(Exception): restarted.state.native_analysis.tool(scope,'read',{'page_numbers':[1]})
