"""Rehearse against a frozen database, then optionally migrate the local database."""
import argparse
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3

from backend.migrations import migrate, SCHEMA_VERSION

ROOT = Path(__file__).resolve().parents[1]
NEW_TABLES = ('review_revisions', 'review_events', 'exports', 'result_notifications', 'result_notification_attempts', 'review_requests')


def connect(path):
    db = sqlite3.connect(path.resolve().as_uri() + '?mode=rw', uri=True)
    db.execute('PRAGMA foreign_keys=ON')
    return db


def compare(old, new):
    counts = {}
    for (table,) in old.execute("SELECT name FROM sqlite_master WHERE type='table'"):
        columns = ','.join('"' + row[1] + '"' for row in old.execute(f'PRAGMA table_info("{table}")'))
        query = f'SELECT {columns} FROM "{table}" ORDER BY rowid'
        before = old.execute(query).fetchall()
        assert before == new.execute(query).fetchall(), f'Historical data changed: {table}'
        counts[table] = len(before)
    assert new.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
    assert not new.execute('PRAGMA foreign_key_check').fetchall()
    assert new.execute('PRAGMA user_version').fetchone()[0] == SCHEMA_VERSION
    for table in NEW_TABLES:
        assert new.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0] == 0
    assert new.execute('SELECT COUNT(*) FROM review_tasks WHERE current_revision<>0 OR extraction_attempt_id<>created_attempt_id OR status<>\'pending\'').fetchone()[0] == 0
    return counts


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('baseline', type=Path)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    baseline = args.baseline.resolve()
    manifest = json.loads((baseline / 'manifest.json').read_text(encoding='utf-8'))
    for name, digest in manifest['sha256'].items():
        assert hashlib.sha256((baseline / name).read_bytes()).hexdigest() == digest, name
        if name.startswith(('data/ap/originals/', 'n8n_workflows/')):
            assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest, name
    rehearsal = ROOT / 'tmp/phase02-rehearsal.sqlite3'
    if rehearsal.exists():
        raise RuntimeError('Rehearsal database already exists; retain evidence and choose a new path')
    rehearsal.parent.mkdir(exist_ok=True)
    with closing(sqlite3.connect((baseline / 'invoices.sqlite3').as_uri() + '?mode=ro', uri=True)) as old:
        with closing(sqlite3.connect(rehearsal)) as isolated:
            old.backup(isolated)
            isolated.execute('PRAGMA foreign_keys=ON')
            migrate(isolated)
            counts = compare(old, isolated)
            migrate(isolated)
            assert counts == compare(old, isolated)
        report = {'baseline': manifest['baseline'], 'schema_version': SCHEMA_VERSION,
                  'isolated_migration': 'passed', 'isolated_repeat': 'passed',
                  'historical_rows_equal': True, 'legacy_table_counts': counts,
                  'originals_and_workflows_sha256_unchanged': True,
                  'new_tables_empty': list(NEW_TABLES), 'live_database_migrated': False}
        if args.apply:
            with closing(connect(ROOT / 'data/ap/invoices.sqlite3')) as live:
                # Refuse application if new writes occurred after the frozen baseline.
                for (table,) in old.execute("SELECT name FROM sqlite_master WHERE type='table'"):
                    query = f'SELECT * FROM "{table}" ORDER BY rowid'
                    assert old.execute(query).fetchall() == live.execute(query).fetchall(), table
                migrate(live)
                assert counts == compare(old, live)
                migrate(live)
                compare(old, live)
            report.update(live_database_migrated=True, live_repeat='passed', integrity_check='ok', foreign_key_check=[])
    output = ROOT / 'logs&architechture/phase02_migration_verification.json'
    output.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
