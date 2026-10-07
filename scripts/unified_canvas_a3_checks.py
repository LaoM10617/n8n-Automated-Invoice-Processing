"""Local A3 transport, attachment isolation, preservation and delivery checks."""
import hashlib
import json
from pathlib import Path
import sqlite3
import urllib.error
import urllib.parse
import urllib.request
from uuid import uuid4

from unified_canvas_a3_probe import ROOT, REPORT, BASE, FORM, api


def multipart(url, fields, data, mime, field='file'):
    boundary = 'a3-' + str(uuid4())
    body = b''.join(f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode() for k,v in fields.items())
    body += f'--{boundary}\r\nContent-Disposition: form-data; name="{field}"; filename="synthetic-probe.bin"\r\nContent-Type: {mime}\r\n\r\n'.encode()
    body += data + f'\r\n--{boundary}--\r\n'.encode()
    request = urllib.request.Request(url,data=body,headers={'Content-Type':f'multipart/form-data; boundary={boundary}'})
    with urllib.request.urlopen(request,timeout=45) as response:
        return json.load(response)


def replay(report):
    # Keep the existing credential in memory; never print it or serialize request headers.
    token = next(line.split('=',1)[1].strip() for line in (ROOT/'.env').read_text(encoding='utf-8').splitlines() if line.startswith('AP_REVIEW_EVENT_TOKEN='))
    events = [api('/api/ap/invoices/'+r['invoice_id']+'/review')['event']['event_id'] for r in report['records']]
    results=[]
    for path,payload in [('ap-unified-review-a2-v1',{'event_id':e}) for e in events]+[('ap-unified-excel-a2-v1',{'export_id':report['batch']['export_id']})]:
        url='http://127.0.0.1:5678/webhook/'+path
        try:
            urllib.request.urlopen(urllib.request.Request(url,data=json.dumps(payload).encode(),headers={'Content-Type':'application/json'}))
            raise AssertionError('Unauthenticated event accepted')
        except urllib.error.HTTPError as exc:
            assert exc.code==403
        request=urllib.request.Request(url,data=json.dumps(payload).encode(),headers={'Content-Type':'application/json','X-AP-Event-Token':token})
        with urllib.request.urlopen(request,timeout=15) as response:
            assert response.status==202
            results.append({'path':path,'unauthenticated':403,'authenticated':202})
    return results


def main():
    import sys
    action=sys.argv[1]
    report=json.loads(REPORT.read_text(encoding='utf-8'))
    if action=='mixed':
        results=[]
        original=(ROOT/'data/ap/originals'/report['records'][0]['stored_name']).read_bytes()
        for attachment,data,mime,expected in [('good',original,'application/pdf','decision_ready'),('broken',b'broken','application/pdf','failed'),('unsupported',b'notes','text/plain','skipped'),('after-error',original,'application/pdf','decision_ready')]:
            source={'source_type':'email','source_namespace':'unified-a3-synthetic-email','source_id':'one-message','attachment_id':attachment,'batch_id':'unified-a3-mixed','case_id':'mixed'}
            r=multipart(BASE+'/api/ap/stages/archive',{'metadata':json.dumps(source)},data,mime)
            for stage in ('analyze','validate-policy'):
                r=api('/api/ap/stages/'+r['run_id']+'/'+stage,{},'POST')
            assert r['outcome']==expected and r['source']==source
            if expected=='decision_ready':
                assert r['analysis_cached'] and r['invoice_id']==report['records'][0]['invoice_id']
            results.append({k:r[k] for k in ('run_id','source','outcome','error_code','receipt_id','invoice_id')})
        report['live_backend_mixed_attachments']=results
        report['live_form_invalid_files']=[]
        for label,data,mime,expected in [('broken',b'broken','application/pdf','failed'),('unsupported',b'notes','text/plain','skipped')]:
            r=multipart(FORM,{'field-0':'unified-a3-'+label},data,mime,'field-1')
            assert r['outcome']==expected
            report['live_form_invalid_files'].append({k:r[k] for k in ('run_id','outcome','error_code','formSubmittedText')})
        print('Mixed attachment associations, failures, skips, subsequent valid item and actual form responses passed.')
    elif action=='replay':
        report['event_replay_http']=replay(report)
        print('Authenticated replay accepted with 202; missing credentials rejected with 403.')
    elif action=='preserve':
        baseline=ROOT/'data/baselines/unified-canvas-a3-start-20261007'
        before=sqlite3.connect((baseline/'invoices.sqlite3').as_uri()+'?mode=ro',uri=True)
        now=sqlite3.connect((ROOT/'data/ap/invoices.sqlite3').as_uri()+'?mode=ro',uri=True)
        tables=[t[0] for t in before.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
        for table in tables:
            rows=before.execute('SELECT rowid,* FROM "'+table+'"').fetchall()
            current={r[0]:r for r in now.execute('SELECT rowid,* FROM "'+table+'"')}
            assert all(current[r[0]]==r for r in rows),table
        m=json.loads((baseline/'manifest.json').read_text())
        for group in ('originals','exports'):
            for p,v in m[group].items():
                assert hashlib.sha256((ROOT/'data/ap'/p).read_bytes()).hexdigest()==v['sha256'],p
        for p,h in m['workspace'].items():
            if (p.startswith('backend/') and p != 'backend/README.md') or (p.startswith('n8n_workflows/') and 'AP_unified_canvas_python_agent_v1' not in p):
                assert hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==h,p
        report['baseline_rows_files_backend_and_old_json_preserved']=True
        checks=[]
        for notice in report['durable_snapshot']['notices']:
            query=urllib.parse.urlencode({'query':'message-id:'+notice['message_id'].strip('<>')})
            found=json.load(urllib.request.urlopen('http://127.0.0.1:8025/api/v1/search?'+query))
            assert len([m for m in found['messages'] if m['MessageID'].strip('<>')==notice['message_id'].strip('<>')])==1
            checks.append({'notification_id':notice['notification_id'],'messages':1})
        report['mailpit_delivery_checks']=checks
        print('All pre-existing business rows, originals, exports and backend code preserved; exactly one Mailpit message per result notification.')
    REPORT.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')


if __name__=='__main__':
    main()
