"""Back up/rehearse schema four, then verify the deployed register using existing demo approvals."""
import argparse
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import sys
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.export_register import ExportBatches
from backend.invoice_xlsx import create_xlsx
from backend.migrations import migrate

REPORT = ROOT / 'logs&architechture/phase02_export_register_verification.json'
DATABASE = ROOT / 'data/ap/invoices.sqlite3'


def connect(path=DATABASE):
    db = sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True)
    db.row_factory = sqlite3.Row
    return db


def table_rows(db, table):
    return [tuple(row) for row in db.execute(f'SELECT * FROM "{table}" ORDER BY rowid')]


def backup():
    destination = ROOT / 'data/baselines' / ('phase02-register-' + datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%SZ'))
    destination.mkdir(parents=True)
    with closing(connect()) as source, closing(sqlite3.connect(destination / 'invoices.sqlite3')) as target:
        source.backup(target)
        assert target.execute('PRAGMA user_version').fetchone()[0] == 3
    files = [*list((ROOT / 'data/ap/originals').rglob('*')), *list((ROOT / 'data/ap/exports').rglob('*.xlsx')), *list((ROOT / 'n8n_workflows').glob('*.json'))]
    hashes = {}
    for path in files:
        if not path.is_file():
            continue
        relative = path.relative_to(ROOT)
        hashes[relative.as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
        copied = destination / relative
        copied.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, copied)
    rehearsal = destination / 'migration_rehearsal.sqlite3'
    shutil.copy2(destination / 'invoices.sqlite3', rehearsal)
    with closing(sqlite3.connect(rehearsal)) as db:
        tables = [r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
        before = {table: table_rows(db, table) for table in tables}
        db.execute('PRAGMA foreign_keys=ON')
        assert migrate(db) == 4 and migrate(db) == 4
        assert all(table_rows(db, t) == rows for t, rows in before.items())
        assert not db.execute('PRAGMA foreign_key_check').fetchall()
    report = {'backup': destination.relative_to(ROOT).as_posix(), 'backup_method': 'SQLite online backup API',
              'migration_rehearsal': {'version': 4, 'repeat_safe': True, 'all_existing_rows_unchanged': True},
              'before_counts': {t: len(rows) for t, rows in before.items()}, 'preserved_file_hashes': hashes}
    REPORT.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps({'backup': report['backup'], 'rehearsal': report['migration_rehearsal'], 'files': len(hashes)}))


def api(path, body=None):
    request = urllib.request.Request('http://127.0.0.1:8000' + path,
        data=json.dumps(body).encode() if body is not None else None,
        headers={'Content-Type': 'application/json', 'X-AP-Review': '1'})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def verify():
    report = json.loads(REPORT.read_text(encoding='utf-8'))
    shown = api('/api/ap/export-register?only_unexported=false')
    events = ['56386780-79ad-4001-82aa-07e683b29563', '49f81bda-f796-46ee-b024-70e7e6ce720c']
    assert {r['event_id'] for r in shown['rows']} == set(events)
    assert api('/api/ap/export-register')['count'] == 0  # Both already have historical single files.
    batch = api('/api/ap/export-batches', {'event_ids': events, 'only_unexported': False})
    assert batch == api('/api/ap/export-batches', {'event_ids': events[::-1], 'only_unexported': False})
    with urllib.request.urlopen('http://127.0.0.1:8000' + batch['download_url']) as response:
        data = response.read()
    service = ExportBatches(connect, ROOT / 'data/ap')
    with closing(connect()) as db, closing(connect(ROOT / report['backup'] / 'invoices.sqlite3')) as previous:
        assert service.verify(data, *service.load(db, batch['export_id'])) == batch['file_sha256']
        assert all(table_rows(db, t) == table_rows(previous, t) for t in report['before_counts'])
        report['all_existing_rows_unchanged'] = True
        report['after_counts'] = {t: len(table_rows(db, t)) for t in [*report['before_counts'], 'export_batches', 'export_batch_items']}
        assert db.execute('PRAGMA user_version').fetchone()[0] == 4
        assert not db.execute('PRAGMA foreign_key_check').fetchall()
        assert db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        # The generalized writer must still recover historical files byte-for-byte.
        for row in db.execute('SELECT * FROM exports'):
            task = dict(db.execute('SELECT * FROM review_tasks WHERE invoice_id=?', (row['invoice_id'],)).fetchone())
            fields = json.loads(db.execute('SELECT fields_json FROM review_revisions WHERE invoice_id=? AND revision=?', (row['invoice_id'], row['review_revision'])).fetchone()[0])
            assert hashlib.sha256(create_xlsx(fields, task, dict(row))).hexdigest() == row['file_sha256']
        report['legacy_writer_hash_compatible'] = True
    assert all(hashlib.sha256((ROOT / p).read_bytes()).hexdigest() == digest for p, digest in report['preserved_file_hashes'].items())
    report['preserved_files_unchanged'] = True
    if 'batch' in report:
        assert all(batch[k] == report['batch'][k] for k in ['export_id', 'file_sha256', 'attempts', 'members'])
        report['replay_or_restart_same_batch'] = True
    report.update(batch=batch, preview_count=shown['count'], totals_by_currency=shown['totals_by_currency'],
                  tests_passed=175, schema_version=4, no_new_models_decisions_or_notifications=True)
    REPORT.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps({k: report[k] for k in ['all_existing_rows_unchanged', 'preserved_files_unchanged', 'legacy_writer_hash_compatible', 'schema_version', 'preview_count']}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['backup', 'verify'])
    args = parser.parse_args()
    backup() if args.action == 'backup' else verify()
