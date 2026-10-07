"""Transactional SQLite schema migration, independent of application startup."""
import argparse
from contextlib import closing
from pathlib import Path
import sqlite3

SCHEMA_VERSION = 5  # Version zero is the unversioned Phase01 schema.


def migrate(db):
    if db.in_transaction:
        raise RuntimeError('Migration requires a connection without an active transaction')
    foreign_keys = db.execute('PRAGMA foreign_keys').fetchone()[0]
    # SQLite table replacement requires disabling FK enforcement outside the transaction.
    # Validate every FK before commit; never rename the old parent table.
    db.execute('PRAGMA foreign_keys=OFF')
    try:
        db.execute('BEGIN IMMEDIATE')
        version = db.execute('PRAGMA user_version').fetchone()[0]
        if version > SCHEMA_VERSION:
            raise RuntimeError(f'Unsupported schema version: {version}')
        for target, filename in ((1, 'phase02_schema.sql'), (2, 'phase02_review_schema.sql'), (3, 'phase02_export_schema.sql'), (4, 'phase02_export_register_schema.sql'), (5, 'phase02_outcome_schema.sql')):
            if version >= target:
                continue
            statement = ''
            for line in Path(__file__).with_name(filename).read_text(encoding='utf-8').splitlines(True):
                statement += line
                if sqlite3.complete_statement(statement):
                    db.execute(statement)
                    statement = ''
            if statement.strip():
                raise RuntimeError('Incomplete migration SQL')
            db.execute(f'PRAGMA user_version={target}')
        if db.execute('PRAGMA foreign_key_check').fetchall():
            raise RuntimeError('Migration foreign-key validation failed')
        if db.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise RuntimeError('Migration integrity validation failed')
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.execute(f'PRAGMA foreign_keys={foreign_keys}')
    return SCHEMA_VERSION


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Migrate an existing AP database after taking a baseline backup.')
    parser.add_argument('database', type=Path)
    args = parser.parse_args()
    with closing(sqlite3.connect(args.database.resolve().as_uri() + '?mode=rw', uri=True, timeout=30)) as connection:
        connection.execute('PRAGMA foreign_keys=ON')
        print(f'Schema version: {migrate(connection)}')
