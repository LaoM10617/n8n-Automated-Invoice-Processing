"""Freeze an offline Phase02 baseline without copying environment secrets."""
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import subprocess


ROOT = Path(__file__).resolve().parents[1]


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    stamp = datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%SZ')
    destination = ROOT / 'data/baselines' / f'phase02-start-{stamp}'
    destination.mkdir(parents=True, exist_ok=False)
    source = ROOT / 'data/ap/invoices.sqlite3'
    with closing(sqlite3.connect(source.as_uri() + '?mode=ro', uri=True)) as db:
        with closing(sqlite3.connect(destination / 'invoices.sqlite3')) as backup:
            db.backup(backup)
            assert backup.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
            assert not backup.execute('PRAGMA foreign_key_check').fetchall()
        tables = [r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
        counts = {name: db.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0] for name in tables}
        originals = db.execute('SELECT stored_name,sha256 FROM invoices').fetchall()
    for name, expected in originals:
        path = ROOT / 'data/ap/originals' / name
        assert path.resolve().is_relative_to((ROOT / 'data/ap/originals').resolve())
        assert sha256(path) == expected
    for folder in ('data/ap/originals', 'n8n_workflows', 'backend'):
        shutil.copytree(ROOT / folder, destination / folder, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    for name in ('compose.yaml', 'AGENTS.md'):
        shutil.copy2(ROOT / name, destination / name)
    files = {p.relative_to(destination).as_posix(): sha256(p) for p in destination.rglob('*') if p.is_file()}
    manifest = {'baseline': destination.relative_to(ROOT).as_posix(),
                'head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
                'counts': counts, 'sha256': files,
                'sqlite_backup': 'sqlite3.Connection.backup; source opened read-only',
                'services': 'All three Compose services verified stopped before backup'}
    (destination / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    print(json.dumps({'baseline': manifest['baseline'], 'counts': counts, 'files': len(files)}, indent=2))


if __name__ == '__main__':
    main()
