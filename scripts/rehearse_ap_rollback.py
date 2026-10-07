"""Rehearse receiver rollback with existing demo IDs and restore the original configuration."""
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import subprocess
import time
import urllib.request
from datetime import datetime, timezone
from scripts import snapshot_unified_canvas

ROOT = Path(__file__).resolve().parents[1]
TARGETS = {
    'stage_a': ('ap-unified-review-a2-v1', 'ap-unified-excel-a2-v1'),
    'original_01_02': ('ap-review-export-v1', 'ap-batch-export-v1'),
    'native': ('ap-native-review-b2-v2', 'ap-native-excel-b2-v2'),
}


def state():
    with sqlite3.connect((ROOT/'data/ap/invoices.sqlite3').as_uri()+'?mode=ro', uri=True) as db:
        assert not db.execute("SELECT 1 FROM processing_attempts WHERE status='processing'").fetchone()
        assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        assert not db.execute('PRAGMA foreign_key_check').fetchall()
        tables={}
        for (name,) in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"):
            rows=sorted(repr(row) for row in db.execute('SELECT * FROM "'+name+'"'))
            tables[name]={'rows':len(rows),'sha256':hashlib.sha256('\n'.join(rows).encode()).hexdigest()}
    files={str(p.relative_to(ROOT/'data/ap')):hashlib.sha256(p.read_bytes()).hexdigest()
           for folder in ('originals','exports') for p in (ROOT/'data/ap'/folder).rglob('*') if p.is_file()}
    return {'tables':tables,'files':files}


def deploy():
    subprocess.run(['docker','compose','up','-d','python-api'],cwd=ROOT,check=True,capture_output=True)
    for _ in range(30):
        try:
            with urllib.request.urlopen('http://127.0.0.1:8000/health',timeout=2) as response:
                if response.status==200:return
        except OSError:time.sleep(1)
    raise RuntimeError('Backend health check failed')


def main():
    compose=ROOT/'compose.yaml';original=compose.read_bytes();before=state()
    stamp=datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%SZ')
    snapshot_unified_canvas.STAMP=stamp
    snapshot_unified_canvas.DEST=ROOT/'data/baselines'/('final-delivery-'+stamp)
    snapshot_unified_canvas.main()
    report={'backup':str(snapshot_unified_canvas.DEST.relative_to(ROOT)),'before':before,'phases':[]}
    b4=json.loads((ROOT/'logs&architechture/AP_native_agent_B4_verification.json').read_text(encoding='utf-8'))
    events=[e['event_id'] for e in b4['snapshot']['events']]
    export_id=b4['batch']['export_id']
    try:
        for phase,(review,batch) in TARGETS.items():
            text=original.decode('utf-8')
            text=re.sub(r'AP_REVIEW_EVENT_URL: .*', 'AP_REVIEW_EVENT_URL: http://n8n:5678/webhook/'+review,text)
            text=re.sub(r'AP_BATCH_EVENT_URL: .*', 'AP_BATCH_EVENT_URL: http://n8n:5678/webhook/'+batch,text)
            compose.write_bytes(text.encode('utf-8'));deploy()
            code='''import os,json,httpx
from backend.review_events import send_event
events,export_id,review,batch=json.loads(INPUT)
assert os.environ['AP_REVIEW_EVENT_URL'].endswith('/'+review)
assert os.environ['AP_BATCH_EVENT_URL'].endswith('/'+batch)
statuses=[send_event(os.environ['AP_REVIEW_EVENT_URL'],os.environ['AP_REVIEW_EVENT_TOKEN'],{'event_id':e}) for e in events]
statuses.append(send_event(os.environ['AP_BATCH_EVENT_URL'],os.environ['AP_REVIEW_EVENT_TOKEN'],{'export_id':export_id}))
assert all(s==202 for s in statuses)
print(json.dumps({'http_statuses':statuses,'review_target':review,'batch_target':batch}))
'''.replace('INPUT',repr(json.dumps([events,export_id,review,batch])))
            result=subprocess.run(['docker','compose','exec','-T','python-api','python','-'],cwd=ROOT,input=code,text=True,capture_output=True,check=True)
            time.sleep(2)
            after=state();assert after==before,'Business data or files changed during '+phase
            report['phases'].append({'phase':phase,**json.loads(result.stdout),'all_business_rows_and_files_unchanged':True})
            print('Rollback phase passed: '+phase,flush=True)
    finally:
        compose.write_bytes(original);deploy()
        report['original_compose_restored']=compose.read_bytes()==original
        report['final_state_unchanged']=state()==before
        (ROOT/'logs&architechture/AP_final_delivery_rollback_verification.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    assert len(report['phases'])==3 and report['final_state_unchanged']


if __name__=='__main__':main()
