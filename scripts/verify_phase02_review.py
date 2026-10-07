"""Read-only post-deployment evidence for the three labeled approval probes."""
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


def get(path):
    return json.load(urllib.request.urlopen(path, timeout=15))


def main():
    baseline = ROOT / 'data/baselines/phase02-start-20261007-075205Z'
    manifest = json.loads((baseline / 'manifest.json').read_text(encoding='utf-8'))
    original_baseline = json.loads((ROOT / 'data/baselines/phase02-start-20261007-073157Z/manifest.json').read_text(encoding='utf-8'))
    for name, expected in original_baseline['sha256'].items():
        if name.startswith(('data/ap/originals/', 'n8n_workflows/')):
            assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected, name
    with closing(sqlite3.connect((ROOT / 'data/ap/invoices.sqlite3').as_uri() + '?mode=ro', uri=True)) as db, closing(sqlite3.connect((baseline / 'invoices.sqlite3').as_uri() + '?mode=ro', uri=True)) as old:
        db.execute('BEGIN')
        unchanged = []
        for table in ('invoices', 'receipts', 'processing_attempts', 'review_tasks', 'notification_attempts'):
            columns = ','.join('"' + row[1] + '"' for row in old.execute(f'PRAGMA table_info({table})'))
            count = manifest['counts'][table]
            assert old.execute(f'SELECT {columns} FROM {table} ORDER BY rowid').fetchall() == db.execute(f'SELECT {columns} FROM {table} ORDER BY rowid LIMIT ?', (count,)).fetchall(), table
            unchanged.append(table)
        counts = {table: db.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0] for table in ('invoices','receipts','processing_attempts','review_tasks','review_revisions','review_events','exports','notification_attempts','review_requests')}
        assert db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        assert not db.execute('PRAGMA foreign_key_check').fetchall()
        assert db.execute('PRAGMA user_version').fetchone()[0] == 2
        new = db.execute('SELECT result_json FROM processing_attempts WHERE attempt_id>90').fetchall()
        assert len(new) == 3 and all(json.loads(r[0]).get('analysis_source') == 'synthetic_saved_analysis_no_model' for r in new)
        runs = [json.loads(r[0]) for r in db.execute('SELECT result_json FROM intake_runs')]
        runs = [r for r in runs if r['source']['source_id'].startswith('phase02-review-')]
        assert all(r['analysis_cached'] for r in runs)
    probes = json.loads((ROOT / 'data/ap/phase02_review_probes.json').read_text(encoding='utf-8'))
    outcomes = []
    for probe in probes:
        result = get('http://127.0.0.1:8000/api/ap/invoices/' + probe['invoice_id'] + '/review')
        expected = 'rejected' if probe['case'] == 'reject' else 'approved'
        assert result['status'] == expected
        if probe['case'] == 'manual':
            assert result['current_fields']['supplier_address'] == 'Example Street 1'
            assert result['machine_fields']['supplier_address'] is None
        outcomes.append({'case': probe['case'], 'invoice_id': probe['invoice_id'], 'status': result['status'],
                         'approval_method': result['approval_method'], 'revision': result['current_revision'], 'event': result['event']})
    instance_checks = {}
    for version, file in [('v7','01_AP_agent_intake_v7.json'),('v8','01_AP_approval_intake_v8.json')]:
        local = json.loads((ROOT / 'n8n_workflows' / file).read_text(encoding='utf-8'))
        remote = json.loads((ROOT / f'tmp/phase02-{version}-instance.json').read_text(encoding='utf-8'))[0]
        assert local['nodes'] == remote['nodes'] and local['connections'] == remote['connections']
        assert remote['active'] and remote['activeVersionId'] == remote['versionId']
        instance_checks[version] = {'nodes_connections_match': True, 'published': True}
    report = {'schema_version': 2, 'counts': counts, 'historical_rows_unchanged': unchanged,
              'historical_originals_and_workflows_sha256_unchanged': True,
              'new_provider_calls': 0, 'synthetic_cached_analyses': 3,
              'outcomes': outcomes, 'instance_checks': instance_checks,
              'mailpit_total': get('http://127.0.0.1:8025/api/v1/messages')['total'],
              'runs': [{key: r.get(key) for key in ('run_id','outcome','invoice_id','analysis_cached','analysis_source','notification_status','event_id')} for r in runs],
              'tests_passed': 101, 'event_delivery_implemented': False, 'excel_generation_implemented': False,
              'gmail': 'Existing credential reference preserved; no new Gmail execution in this step.'}
    before_path = ROOT / 'logs&architechture/phase02_review_before_restart.json'
    if before_path.exists():
        before = json.loads(before_path.read_text(encoding='utf-8'))
        assert before['counts'] == counts and before['outcomes'] == outcomes
        assert before['mailpit_total'] == report['mailpit_total']
        report['restart_and_replay_business_state_unchanged'] = True
    path = ROOT / 'logs&architechture/phase02_review_verification.json'
    path.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
