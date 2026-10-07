"""Compare agent attempts with the preserved local baseline. Run from the repository root."""
import json,sqlite3,hashlib
from pathlib import Path
p=Path('logs&architechture/phase01_agent_verification.json')
with sqlite3.connect('data/ap/invoices.sqlite3') as db, sqlite3.connect('data/baselines/phase01-pre-agent-20261006/invoices.sqlite3') as old:
 report={'tests':61,'offline_agent_tests':5,'attempts':[],'counts':{}}
 for name in ['invoices','receipts','processing_attempts','review_tasks','notification_attempts']:
  try:report['counts'][name]={'before':old.execute('select count(*) from '+name).fetchone()[0],'after':db.execute('select count(*) from '+name).fetchone()[0]}
  except sqlite3.OperationalError:pass
 for aid,iid,status,raw in db.execute('select attempt_id,invoice_id,status,result_json from processing_attempts where attempt_id>=85'):
  r=json.loads(raw or '{}');before=old.execute("select result_json from processing_attempts where invoice_id=? and status='processed' order by attempt_id desc limit 1",(iid,)).fetchone();b=json.loads(before[0]) if before else {}
  report['attempts'].append({'attempt_id':aid,'invoice_id':iid,'status':status,'trace':r.get('agent_trace'),'field_changes':{k:{'before':b.get('fields',{}).get(k),'after':v} for k,v in r.get('fields',{}).items() if b.get('fields',{}).get(k)!=v},'issue_codes':[x['code'] for x in r.get('validation_issues',[])]})
 for name in ['01_AP_unified_intake_v5.json','01_AP_compact_intake_v6.json']:
  assert (Path('n8n_workflows')/name).read_bytes()==(Path('data/baselines/phase01-pre-agent-20261006/n8n_workflows')/name).read_bytes()
 for original in Path('data/baselines/phase01-pre-refactor-20261006/originals').iterdir():
  assert original.read_bytes()==(Path('data/ap/originals')/original.name).read_bytes()
 report['historical_workflows_and_originals_unchanged']=True
 from datetime import datetime
 latest=[a for a in report['attempts'] if a['attempt_id'] in (89,90)]
 stamps=sorted(datetime.fromisoformat(c['started_at']) for a in latest for c in (a['trace'] or {}).get('model_calls',[]))
 report['final_agent_version']='langchain-invoice-v3'
 report['final_model_calls']=len(stamps)
 report['all_diagnostic_model_calls']=sum(len((a['trace'] or {}).get('model_calls',[])) for a in report['attempts'])
 report['final_min_request_gap_seconds']=min((b-a).total_seconds() for a,b in zip(stamps,stamps[1:])) if len(stamps)>1 else None
 report['final_quality_limit']='OCR11 full address is present in the raw draft but rejected by unchanged contiguous-text grounding; validated address is null. This is not full field parity.'
 report['unchanged_components']={name:Path('backend',name).read_bytes()==Path('data/baselines/phase01-pre-agent-20261006/backend',name).read_bytes() for name in ['document_text.py','validation.py']}
 import httpx
 report['mailpit_messages']=httpx.get('http://127.0.0.1:8025/api/v1/messages').json()['total']
 p.write_text(json.dumps(report,indent=2),encoding='utf-8')
 print([(a['attempt_id'],a['status'],a['field_changes']) for a in report['attempts']]);print(report['counts'])
