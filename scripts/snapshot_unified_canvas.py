"""Capture the A0 baseline without changing application state or reading secrets."""
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import subprocess

ROOT = Path(__file__).resolve().parents[1]
STAMP = '20261007-120021Z'
DEST = ROOT / 'data' / 'baselines' / ('unified-canvas-a0-' + STAMP)

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    subprocess.run(['git', 'check-ignore', str(DEST)], cwd=ROOT, check=True, capture_output=True)
    DEST.mkdir(parents=True, exist_ok=False)
    status = subprocess.check_output(['git', 'status', '--porcelain=v1', '-uall'], cwd=ROOT).decode('utf-8')
    (DEST / 'git-status.txt').write_text(status, encoding='utf-8')
    manifest = {'stamp_utc': STAMP, 'head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT).decode().strip(), 'workspace': {}, 'originals': {}, 'exports': {}, 'tables': {}}
    for folder in ('backend', 'scripts', 'n8n_workflows', 'logs&architechture'):
        for path in sorted((ROOT / folder).rglob('*')):
            if not path.is_file() or '__pycache__' in path.parts or path.suffix not in ('.py', '.js', '.cjs', '.json', '.md', '.txt', '.sql'):
                continue
            rel = path.relative_to(ROOT)
            target = DEST / 'workspace' / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
            manifest['workspace'][rel.as_posix()] = digest(path)
    for name in ('compose.yaml', 'AGENTS.md', '.gitignore'):
        shutil.copy2(ROOT / name, DEST / name)
        manifest['workspace'][name] = digest(ROOT / name)
    src = sqlite3.connect((ROOT / 'data/ap/invoices.sqlite3').as_uri() + '?mode=ro', uri=True)
    with sqlite3.connect(DEST / 'invoices.sqlite3') as backup:
        src.backup(backup)
        assert backup.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        assert not backup.execute('PRAGMA foreign_key_check').fetchall()
        for (name,) in backup.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"):
            quoted = '"' + name.replace('"', '""') + '"'
            manifest['tables'][name] = backup.execute('SELECT count(*) FROM ' + quoted).fetchone()[0]
    src.close()
    for folder in ('originals', 'exports'):
        for path in sorted((ROOT / 'data/ap' / folder).rglob('*')):
            if path.is_file():
                rel = path.relative_to(ROOT / 'data/ap')
                target = DEST / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, target)
                assert digest(target) == digest(path)
                manifest[folder][rel.as_posix()] = {'sha256': digest(path), 'bytes': path.stat().st_size}
    manifest['database_sha256'] = digest(DEST / 'invoices.sqlite3')
    (DEST / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    print(json.dumps({'backup': str(DEST), 'integrity': 'ok', 'foreign_keys': 'ok', 'workspace_files': len(manifest['workspace']), 'originals': len(manifest['originals']), 'exports': len(manifest['exports']), 'tables': manifest['tables']}))

if __name__ == '__main__':
    main()
