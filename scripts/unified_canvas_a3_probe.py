"""Explicit local A3 probes using labeled cached analyses, never provider calls."""
import argparse
import hashlib
import json
from pathlib import Path
import sqlite3
import urllib.request
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / 'logs&architechture/AP_unified_canvas_A3_A4_verification.json'
BASE = 'http://127.0.0.1:8000'
FORM = 'http://127.0.0.1:5678/form/ap-unified-intake-a2-v1'


def api(path, body=None, method=None):
    request = urllib.request.Request(BASE + path, data=None if body is None else json.dumps(body).encode(),
        method=method, headers={'Content-Type': 'application/json', 'X-AP-Review': '1'})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def upload(record):
    boundary = 'a3-' + str(uuid4())
    payload = (ROOT / 'data/ap/originals' / record['stored_name']).read_bytes()
    body = (f'--{boundary}\r\nContent-Disposition: form-data; name="field-0"\r\n\r\n{record["source_id"]}\r\n'
            f'--{boundary}\r\nContent-Disposition: form-data; name="field-1"; filename="synthetic-a3.pdf"\r\n'
            'Content-Type: application/pdf\r\n\r\n').encode() + payload + f'\r\n--{boundary}--\r\n'.encode()
    request = urllib.request.Request(FORM, data=body, headers={'Content-Type': f'multipart/form-data; boundary={boundary}'})
    with urllib.request.urlopen(request, timeout=45) as response:
        data = json.load(response)
    assert data['analysis_cached'] and data['analysis_source'] == 'synthetic_saved_analysis_no_model', data
    assert data['invoice_id'] == record['invoice_id']
    return data


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['upload', 'decide', 'batch', 'snapshot', 'verify'])
    parser.add_argument('--case', choices=['auto', 'manual', 'reject'])
    args = parser.parse_args()
    records = json.loads((ROOT / 'data/ap/unified_a3_probes.json').read_text())
    report = json.loads(REPORT.read_text(encoding='utf-8')) if REPORT.exists() else {'fixture_source': 'synthetic_saved_analysis_no_model', 'records': records}
    selected = next((r for r in records if r['case'] == args.case), None)
    if args.action == 'upload':
        assert selected
        data = upload(selected)
        report.setdefault('uploads', {})[args.case] = data
        print(json.dumps({k: data[k] for k in ('invoice_id','outcome','review_status','approval_method','analysis_cached','event_id')}))
    elif args.action == 'decide':
        assert selected and args.case != 'auto'
        path = '/api/ap/invoices/' + selected['invoice_id'] + '/review'
        state = api(path)
        if state['status'] == 'pending':
            body = {'expected_revision': state['current_revision'], 'processing_attempt_id': state['processing_attempt_id'],
                    'changes': {}, 'reason': 'A3 synthetic demo: checked the original on page 1.', 'page': 1}
            if args.case == 'manual':
                body['changes'] = {'supplier_address': 'Example Street 1'}
                body['evidence_resolutions'] = [{'id': issue['id'], 'page': 1, 'reason': 'The synthetic original states Example Street 1.'}
                    for issue in state['validation']['machine_issues'] if issue.get('resolvable')]
            state = api(path, body, 'PATCH')
            state = api(path+'/decision', {'expected_revision': state['current_revision'], 'processing_attempt_id': state['processing_attempt_id'],
                'decision': 'approve' if args.case == 'manual' else 'reject', 'request_id': 'unified-a3-'+args.case,
                'reason': 'Synthetic original reviewed; approve correction.' if args.case == 'manual' else 'Synthetic total does not match net plus tax.'}, 'POST')
        assert state['status'] == ('approved' if args.case == 'manual' else 'rejected')
        report.setdefault('decisions', {})[args.case] = {k: state[k] for k in ('status','current_revision','processing_attempt_id','approval_method','event')}
        print(json.dumps(report['decisions'][args.case]))
    elif args.action == 'batch':
        events = [api('/api/ap/invoices/'+r['invoice_id']+'/review')['event']['event_id'] for r in records if r['case'] != 'reject']
        result = api('/api/ap/export-batches', {'event_ids': events, 'only_unexported': False}, 'POST')
        report['batch'] = result
        print(json.dumps(result))
    else:
        db = sqlite3.connect((ROOT/'data/ap/invoices.sqlite3').as_uri()+'?mode=ro', uri=True)
        db.row_factory = sqlite3.Row
        states = [api('/api/ap/invoices/'+r['invoice_id']+'/review') for r in records]
        events = [s['event']['event_id'] for s in states]
        notices = [api('/api/ap/result-notifications/review/'+e) for e in events]
        batch = api('/api/ap/export-batches/'+report['batch']['export_id'])
        notices.append(api('/api/ap/result-notifications/batch/'+batch['export_id']))
        data = urllib.request.urlopen(BASE+'/api/ap/export-batches/'+batch['export_id']+'/files/xlsx').read()
        assert data[:2] == b'PK' and hashlib.sha256(data).hexdigest() == batch['file_sha256']
        assert all(n['status']=='sent' for n in notices)
        assert all(s['event']['status']=='processed' for s in states)
        assert [s['status'] for s in states]==['approved','approved','rejected']
        assert states[1]['current_fields']['supplier_address']=='Example Street 1'
        assert states[1]['raw_extraction']['fields']['supplier_address']=='Simulated OCR draft error'
        assert db.execute('SELECT COUNT(*) FROM processing_attempts').fetchone()[0] == 98, 'Unexpected analysis attempt'
        assert not db.execute('PRAGMA foreign_key_check').fetchall()
        assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        snap={'events': [s['event'] for s in states], 'notices': notices, 'batch':batch,
              'counts':{t[0]:db.execute('SELECT COUNT(*) FROM "'+t[0]+'"').fetchone()[0] for t in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}}
        if args.action == 'verify':
            assert report['durable_snapshot'] == snap, 'Durable state changed across restart/replay'
            report['restart_replay_unchanged'] = True
        else:
            report['durable_snapshot']=snap
        print(json.dumps({'action':args.action,'statuses':[s['status'] for s in states], 'notices':[n['status'] for n in notices], 'xlsx_sha256':batch['file_sha256']}))
    REPORT.write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')


if __name__ == '__main__':
    main()
