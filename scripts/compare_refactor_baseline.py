"""Compare preserved baseline semantics and bytes, ignoring only execution timestamps."""
import hashlib,json,sqlite3
from pathlib import Path
import httpx
ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'data/baselines/phase01-pre-refactor-20261006'
baseline=json.loads((BASE/'manifest.json').read_text(encoding='utf-8'))
baseline['files']={k.replace(chr(92),'/'):v for k,v in baseline['files'].items()}
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
report={'originals_unchanged':True,'v5_unchanged':True,'invoice_differences':[],'batch_differences':[],'baseline_files_unchanged':True}
for path,sha in baseline['files'].items():
 assert digest(BASE/path)==sha,path
 if path.startswith('originals/'):
  assert digest(ROOT/'data/ap'/path)==sha,path
report['originals_checked']=sum(k.startswith('originals/') for k in baseline['files'])
assert report['originals_checked']==baseline['counts']['invoices']
v5='n8n_workflows/01_AP_unified_intake_v5.json'
assert digest(ROOT/v5)==baseline['files'][v5]
with httpx.Client(base_url='http://127.0.0.1:8000',timeout=30) as c:
 for before in baseline['invoices']:
  after=c.get('/api/ap/invoices/'+before['invoice_id']).json()
  if before!=after:report['invoice_differences'].append(before['invoice_id'])
 for batch,before in baseline['batches'].items():
  after=c.get('/api/ap/email-batches/'+batch).json()
  def normalized(x):
   value=json.loads(json.dumps(x))
   for row in value['outcomes']:row.pop('updated_at',None)
   return value
  if normalized(before)!=normalized(after):report['batch_differences'].append(batch)
with sqlite3.connect(ROOT/'data/ap/invoices.sqlite3') as db:
 report['before_counts']=baseline['counts']
 report['after_counts']={t:db.execute('SELECT COUNT(*) FROM '+t).fetchone()[0] for t in baseline['counts']}
 report['stage_runs']=db.execute('SELECT COUNT(*) FROM intake_runs').fetchone()[0]
 report['stage_events']=db.execute('SELECT COUNT(*) FROM intake_stage_events').fetchone()[0]
report['passed']=not report['invoice_differences'] and not report['batch_differences'] and report['before_counts']==report['after_counts']
(ROOT/'logs&architechture/phase01_refactor_comparison.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report,indent=2));assert report['passed']
