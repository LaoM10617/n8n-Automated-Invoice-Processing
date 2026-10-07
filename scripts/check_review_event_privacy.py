"""Check only this receiver's execution payloads; optionally redact its earlier probe token."""
import argparse
import json
from pathlib import Path
import subprocess

parser = argparse.ArgumentParser()
parser.add_argument('--redact-existing-probes', action='store_true')
args = parser.parse_args()
root = Path(__file__).resolve().parents[1]
token = next(line.split('=', 1)[1].strip() for line in (root / '.env').read_text(encoding='utf-8').splitlines() if line.startswith('AP_REVIEW_EVENT_TOKEN='))
code = """
const sqlite3=require('/usr/local/lib/node_modules/n8n/node_modules/.pnpm/sqlite3@5.1.7_bluebird@3.7.2_supports-color@8.1.1/node_modules/sqlite3');
let input=''; process.stdin.on('data',c=>input+=c); process.stdin.on('end',()=>{
 const {token,redact}=JSON.parse(input);
 const db=new sqlite3.Database('/home/node/.n8n/database.sqlite',redact?sqlite3.OPEN_READWRITE:sqlite3.OPEN_READONLY);
 db.serialize(()=>{
  if(redact) {
   db.run('BEGIN IMMEDIATE');
   db.run("UPDATE execution_data SET data=replace(data,?,?) WHERE executionId IN (SELECT id FROM execution_entity WHERE workflowId=?)",[token,'[REDACTED]','APReviewEventsV1']);
   db.run('COMMIT');
  }
  db.all('SELECT d.data FROM execution_data d JOIN execution_entity e ON e.id=d.executionId WHERE e.workflowId=?',['APReviewEventsV1'],(err,rows)=>{
   if(err) throw err;
   console.log(JSON.stringify({payload_rows:rows.length,credential_found:rows.some(r=>r.data.includes(token)),redacted_existing_probes:redact}));
   db.close();
  });
 });
});
"""
result = subprocess.run(['docker', 'compose', 'exec', '-T', 'n8n', 'node', '-e', code],
                        cwd=root, input=json.dumps({'token': token, 'redact': args.redact_existing_probes}),
                        text=True, capture_output=True, check=True)
check = json.loads(result.stdout)
print(json.dumps(check))
assert not check['credential_found'], 'Credential persistence detected; do not deliver further events.'
