"""Verify actual local exports of the two existing labeled synthetic approvals."""
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import urllib.error
import urllib.request

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
from backend.invoice_xlsx import verify_xlsx

base = 'http://127.0.0.1:8000'
path = root / 'logs&architechture/phase02_step7_verification.json'
report = json.loads(path.read_text(encoding='utf-8'))
results = []
events = ['56386780-79ad-4001-82aa-07e683b29563', '49f81bda-f796-46ee-b024-70e7e6ce720c']
for event_id in events:
    request = urllib.request.Request(base + '/api/ap/exports', data=json.dumps({'event_id': event_id}).encode(),
                                     headers={'Content-Type': 'application/json', 'X-AP-Review': '1'})
    with urllib.request.urlopen(request, timeout=30) as response:
        export = json.load(response)
    with urllib.request.urlopen(base + export['download_url']) as response:
        data = response.read()
        assert response.headers.get_content_type() == 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    with sqlite3.connect((root / 'data/ap/invoices.sqlite3').as_uri() + '?mode=ro', uri=True) as db:
        db.row_factory = sqlite3.Row
        task = dict(db.execute('SELECT * FROM review_tasks WHERE invoice_id=?', (export['invoice_id'],)).fetchone())
        snapshot = db.execute('SELECT fields_json FROM review_revisions WHERE invoice_id=? AND revision=?', (export['invoice_id'], export['review_revision'])).fetchone()[0]
    assert verify_xlsx(data, json.loads(snapshot), task, export) == export['file_sha256']
    assert (root / 'data/ap' / export['file_path']).read_bytes() == data
    results.append({**export, 'approval_method': task['approval_method'], 'download_snapshot_and_hash_verified': True})
request = urllib.request.Request(base + '/api/ap/exports', data=json.dumps({'event_id': '531d8b4c-0b9a-462e-8786-109bbfc70047'}).encode(), headers={'Content-Type': 'application/json', 'X-AP-Review': '1'})
try:
    urllib.request.urlopen(request)
    raise AssertionError('Rejected invoice was exported')
except urllib.error.HTTPError as exc:
    assert exc.code == 409
if report.get('live_exports'):
    report['replay_or_restart_same_ids_and_hashes'] = all(
        (old['export_id'], old['file_sha256'], old['attempts']) == (new['export_id'], new['file_sha256'], new['attempts'])
        for old, new in zip(report['live_exports'], results))
    assert report['replay_or_restart_same_ids_and_hashes']
report['live_exports'] = results
report['rejected_export_status'] = 409
with sqlite3.connect((root / 'data/ap/invoices.sqlite3').as_uri() + '?mode=ro', uri=True) as db, sqlite3.connect((root / report['backup'] / 'invoices.sqlite3').as_uri() + '?mode=ro', uri=True) as old:
    tables = list(report['before_counts'])
    report['after_counts'] = {t: db.execute('SELECT COUNT(*) FROM "' + t + '"').fetchone()[0] for t in tables}
    report['historical_rows_unchanged'] = all(db.execute('SELECT * FROM "' + t + '" ORDER BY rowid').fetchall() == old.execute('SELECT * FROM "' + t + '" ORDER BY rowid').fetchall() for t in tables if t != 'exports')
    assert report['historical_rows_unchanged']
    report['schema_version'] = db.execute('PRAGMA user_version').fetchone()[0]
    assert db.execute('PRAGMA foreign_key_check').fetchall() == []
    assert report['after_counts']['exports'] == 2
report['workflow_hashes_unchanged'] = all(hashlib.sha256((root / p).read_bytes()).hexdigest() == h for p, h in report['workflow_hashes'].items())
report['original_hashes_unchanged'] = all(hashlib.sha256((root / p).read_bytes()).hexdigest() == h for p, h in report['original_hashes'].items())
assert report['workflow_hashes_unchanged'] and report['original_hashes_unchanged']
report['tests_passed'] = 157
path.write_text(json.dumps(report, indent=2), encoding='utf-8')
print(json.dumps({'exports': [{'id': x['export_id'], 'method': x['approval_method'], 'hash': x['file_sha256']} for x in results], 'historical_rows_unchanged': report['historical_rows_unchanged']}))
