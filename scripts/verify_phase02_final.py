"""Read-only final acceptance; run again after restart to compare durable identities."""
import hashlib
import json
import re
from pathlib import Path
import sqlite3
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / 'logs&architechture/phase02_final_verification.json'


def get(url):
    with urllib.request.urlopen(url, timeout=20) as response:
        return response.read()


def main():
    report = json.loads(REPORT.read_text(encoding='utf-8'))
    db = sqlite3.connect((ROOT / 'data/ap/invoices.sqlite3').as_uri() + '?mode=ro', uri=True)
    db.row_factory = sqlite3.Row
    assert db.execute('PRAGMA user_version').fetchone()[0] == 5
    assert not db.execute('PRAGMA foreign_key_check').fetchall()
    assert db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
    for filename, digest in report['baseline_files'].items():
        assert hashlib.sha256((ROOT / filename).read_bytes()).hexdigest() == digest, filename
    previous = sqlite3.connect((ROOT / report['backup'] / 'invoices.sqlite3').as_uri() + '?mode=ro', uri=True)
    # Existing business rows stay unchanged; only outbox transport advances.
    for table in report['baseline_counts']:
        if table == 'review_events':
            continue
        old = previous.execute(f'SELECT rowid,* FROM "{table}"').fetchall()
        current = {r[0]: tuple(r) for r in db.execute(f'SELECT rowid,* FROM "{table}"')}
        assert all(current[r[0]] == r for r in old), table
    events = [dict(r) for r in db.execute('SELECT event_id,event_type,status,attempts FROM review_events ORDER BY event_id')]
    assert all(r['status'] == 'processed' for r in events)
    identity = 'event_id,review_id,invoice_id,review_revision,event_type,request_id,request_hash,created_at'
    existing = {tuple(r) for r in db.execute(f'SELECT {identity} FROM review_events')}
    assert all(tuple(r) in existing for r in previous.execute(f'SELECT {identity} FROM review_events'))
    batches = []
    for row in db.execute('SELECT export_id,file_sha256,attempts FROM export_batches ORDER BY export_id'):
        data = get(f'http://127.0.0.1:8000/api/ap/export-batches/{row[0]}/files/xlsx')
        assert data[:2] == b'PK' and hashlib.sha256(data).hexdigest() == row[1]
        batches.append(dict(row))
    notifications = []
    for row in db.execute('SELECT notification_id,category,status,attempts,message_id FROM outcome_notifications ORDER BY notification_id'):
        assert row['status'] == 'sent'
        query = urllib.parse.urlencode({'query': 'message-id:' + row['message_id'].strip('<>')})
        found = json.loads(get('http://127.0.0.1:8025/api/v1/search?' + query))
        matches = [m for m in found['messages'] if m['MessageID'].strip('<>') == row['message_id'].strip('<>')]
        assert len(matches) == 1
        message = json.loads(get('http://127.0.0.1:8025/api/v1/message/' + matches[0]['ID']))
        links = re.findall(r'http://127\.0\.0\.1:8000/[^\s<>]+', message['Text'])
        assert links
        for link in links:
            assert get(link)
        notifications.append(dict(row))
    snapshot = {'events': events, 'batches': batches, 'notifications': notifications,
                'counts': {t[0]: db.execute(f'SELECT COUNT(*) FROM "{t[0]}"').fetchone()[0]
                           for t in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}}
    if 'durable_snapshot' in report:
        assert snapshot == report['durable_snapshot'], 'State changed across restart/replay.'
        report['restart_and_replay_unchanged'] = True
    report['durable_snapshot'] = snapshot
    report['baseline_business_rows_and_files_preserved'] = True
    report['mailpit_exactly_one_message_per_notification'] = True
    report['notification_links_verified'] = True
    REPORT.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps({'counts': snapshot['counts'], 'restart_verified': report.get('restart_and_replay_unchanged', False)}))


if __name__ == '__main__':
    main()

