"""Offline graph tests use a fake model; they do not claim provider execution."""
import pytest
from pydantic import PrivateAttr
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatResult, ChatGeneration
from backend import invoice_agent as agent
from backend.extraction import RawFields
from backend.document_text import ProcessingError

class ScriptedModel(BaseChatModel):
    loop: bool = False
    _calls: int = PrivateAttr(default=0)
    @property
    def _llm_type(self): return 'offline-test'
    def bind_tools(self, tools, **kwargs): return self
    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        self._calls += 1
        if self._calls == 1 or self.loop:
            name, args = 'read_invoice_page', {'page_numbers':[1]}
        else:
            name, args = 'Extraction', {'fields':{k:None for k in RawFields.model_fields},'evidence':[],'uncertainties':['Test document']}
        message=AIMessage(content='',tool_calls=[{'name':name,'args':args,'id':str(self._calls),'type':'tool_call'}])
        return ChatResult(generations=[ChatGeneration(message=message)])

def run(monkeypatch, loop=False):
    model=ScriptedModel(loop=loop)
    monkeypatch.setattr(agent,'make_model',lambda:model)
    monkeypatch.setattr(agent,'wait_for_model_cooldown',lambda:None)
    monkeypatch.setattr(agent,'reserve_model_request',lambda:None)
    traces=[]
    token=agent.trace_sink.set(traces.append)
    try:
        result=agent.extract_fields([{'page':1,'text':'Test document'}])
        return result,traces
    finally:agent.trace_sink.reset(token)

def test_real_graph_read_then_schema(monkeypatch):
    result,traces=run(monkeypatch)
    assert result['uncertainties']==['Test document']
    trace=traces[-1]
    assert trace['status']=='completed' and len(trace['model_calls'])==2
    assert trace['tools'][0]['tool']=='read_invoice_page' and trace['pages_read']==[1]
    assert 'Test document' not in str(trace)

def test_model_budget_stops_loop(monkeypatch):
    with pytest.raises(ProcessingError,match='budget exhausted'):run(monkeypatch,True)

def test_tools_are_document_scoped():
    trace={'tools':[]}
    tools,read=agent.build_tools([{'page':1,'text':'Invoice A'}],trace,lambda:None)
    with pytest.raises(ValueError):tools[0].invoke({'page_numbers':[2]})
    assert read==set() and not trace['tools']
    assert tools[1].invoke({'query':'Invoice'})['matches'][0]['page']==1

def test_legacy_cache_invalidated_and_failed_trace_persisted(tmp_path,monkeypatch):
    from fastapi.testclient import TestClient
    from backend.app import create_app
    from backend.test_intake_stages import setup,archive,advance
    from backend import app as module
    import sqlite3,json
    setup(monkeypatch)
    with TestClient(create_app(tmp_path)) as c:
        first=advance(c,archive(c))
        with sqlite3.connect(tmp_path/'invoices.sqlite3') as db:
            raw=json.loads(db.execute('SELECT result_json FROM processing_attempts WHERE attempt_id=?',(first['analysis_run_id'],)).fetchone()[0])
            raw.pop('analysis_signature')
            db.execute('UPDATE processing_attempts SET result_json=? WHERE attempt_id=?',(json.dumps(raw),first['analysis_run_id']))
        def fail(pages):
            agent.trace_sink.get()({'status':'failed','model_calls':[{'status':'failed'}]})
            raise ProcessingError('AGENT_FAILED','Test failure')
        monkeypatch.setattr(module,'extract_fields',fail)
        second=advance(c,archive(c))
        assert second['outcome']=='failed' and not second['analysis_cached']
        current=c.get('/api/ap/invoices/'+first['invoice_id']).json()
        assert current['processing_result']['agent_trace']['status']=='failed'
        assert current['processing_attempt_id']!=first['analysis_run_id']

def test_provider_binding_preserves_nullable_schema():
    from backend.extraction import Extraction
    model=agent.InvoiceGemini(model='gemini-3.5-flash-lite',google_api_key='offline-test-key',vertexai=False,max_retries=0)
    bound=model.bind_tools([Extraction],tool_choice='any')
    schema=bound.kwargs['tools'][0].function_declarations[0].parameters_json_schema
    for field in RawFields.model_fields:
        assert {'type':'null'} in schema['properties']['fields']['properties'][field]['anyOf']
    assert schema['properties']['fields']['required']==list(RawFields.model_fields)
