"""Offline migration safety and database constraints; no provider or SMTP calls."""
import sqlite3

import pytest

from backend.migrations import migrate


@pytest.fixture
def legacy(tmp_path):
    db = sqlite3.connect(tmp_path / 'legacy.sqlite3')
    db.execute('PRAGMA foreign_keys=ON')
    db.executescript('''
        CREATE TABLE invoices(invoice_id TEXT PRIMARY KEY);
        CREATE TABLE processing_attempts(attempt_id INTEGER PRIMARY KEY, invoice_id TEXT REFERENCES invoices);
        CREATE TABLE review_tasks(
            review_id TEXT PRIMARY KEY, invoice_id TEXT UNIQUE NOT NULL REFERENCES invoices,
            status TEXT NOT NULL DEFAULT 'pending' CHECK(status='pending'),
            created_attempt_id INTEGER NOT NULL REFERENCES processing_attempts(attempt_id),
            created_at TEXT NOT NULL DEFAULT 'original-time');
        CREATE TABLE notification_attempts(notification_id TEXT PRIMARY KEY,
            review_id TEXT NOT NULL REFERENCES review_tasks(review_id));
        INSERT INTO invoices VALUES('invoice');
        INSERT INTO processing_attempts VALUES(1,'invoice');
        INSERT INTO review_tasks(review_id,invoice_id,created_attempt_id) VALUES('review','invoice',1);
        INSERT INTO notification_attempts VALUES('notification','review');
    ''')
    yield db
    db.close()


def snapshot(db):
    schema = db.execute('SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name').fetchall()
    tables = [r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")]
    return schema, {t: db.execute(f'SELECT * FROM "{t}" ORDER BY rowid').fetchall() for t in tables}


def test_preserves_legacy_rows_foreign_keys_and_repeat(legacy):
    before = legacy.execute('SELECT * FROM review_tasks').fetchall()
    assert migrate(legacy) == 5
    assert legacy.execute('SELECT review_id,invoice_id,status,created_attempt_id,created_at FROM review_tasks').fetchall() == before
    assert legacy.execute('SELECT current_revision,extraction_attempt_id FROM review_tasks').fetchone() == (0, 1)
    assert legacy.execute('SELECT * FROM notification_attempts').fetchall() == [('notification', 'review')]
    assert legacy.execute('PRAGMA foreign_keys').fetchone()[0] == 1
    assert legacy.execute('PRAGMA foreign_key_check').fetchall() == []
    after = snapshot(legacy)
    migrate(legacy)
    assert snapshot(legacy) == after
    with pytest.raises(sqlite3.IntegrityError):
        legacy.execute("DELETE FROM review_tasks WHERE review_id='review'")
    legacy.rollback()
    with pytest.raises(sqlite3.IntegrityError):
        legacy.execute("INSERT INTO notification_attempts VALUES('bad','missing')")


def test_late_failure_rolls_back_table_replacement_and_version(legacy):
    legacy.execute('CREATE TABLE exports(existing TEXT)')
    before = snapshot(legacy)
    with pytest.raises(sqlite3.OperationalError):
        migrate(legacy)
    assert snapshot(legacy) == before
    assert legacy.execute('PRAGMA user_version').fetchone()[0] == 0
    assert legacy.execute('PRAGMA foreign_keys').fetchone()[0] == 1


def test_future_version_is_rejected_without_changes(legacy):
    legacy.execute('PRAGMA user_version=99')
    before = snapshot(legacy)
    with pytest.raises(RuntimeError, match='Unsupported schema'):
        migrate(legacy)
    assert snapshot(legacy) == before
    assert legacy.execute('PRAGMA user_version').fetchone()[0] == 99


def test_status_revision_event_and_export_constraints(legacy):
    migrate(legacy)
    for status in ('approved', 'rejected', 'pending'):
        legacy.execute('UPDATE review_tasks SET status=?', (status,))
    legacy.commit()
    with pytest.raises(sqlite3.IntegrityError):
        legacy.execute("UPDATE review_tasks SET status='paid'")
    legacy.rollback()
    legacy.execute('''INSERT INTO review_revisions VALUES
        ('review','invoice',1,1,'{}','{}','[]','[]','[]','demo reviewer',NULL,'now')''')
    legacy.execute("INSERT INTO review_events(event_id,review_id,invoice_id,review_revision,event_type) VALUES('event','review','invoice',1,'approved')")
    legacy.execute("INSERT INTO exports(export_id,event_id,invoice_id,review_revision,mapping_version) VALUES('export','event','invoice',1,'v1')")
    legacy.commit()
    invalid = [
        "UPDATE review_revisions SET fields_json='changed'",
        'DELETE FROM review_revisions',
        "INSERT INTO review_events(event_id,review_id,invoice_id,review_revision,event_type) VALUES('event2','review','invoice',1,'approved')",
        "INSERT INTO exports(export_id,event_id,invoice_id,review_revision,mapping_version) VALUES('export2','event','invoice',1,'v2')",
        "INSERT INTO review_tasks(review_id,invoice_id,created_attempt_id) VALUES('other','invoice',1)",
        "INSERT INTO result_notifications(notification_id,event_id,category) VALUES('notification','event','export_completed')",
    ]
    for sql in invalid:
        with pytest.raises(sqlite3.IntegrityError):
            legacy.execute(sql)
        legacy.rollback()
    assert legacy.execute('PRAGMA foreign_key_check').fetchall() == []


def test_active_transaction_is_not_committed_by_migration(legacy):
    legacy.execute("INSERT INTO invoices VALUES('uncommitted')")
    with pytest.raises(RuntimeError, match='active transaction'):
        migrate(legacy)
    assert legacy.in_transaction
    legacy.rollback()
    assert legacy.execute("SELECT 1 FROM invoices WHERE invoice_id='uncommitted'").fetchone() is None
