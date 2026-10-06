"""Render fixed inputs using local synthetic-invoice-gen templates; never call an LLM."""
import json
import shutil
import sys
from pathlib import Path

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[1]
SOURCE = Path('D:/Projects/synthetic-invoice-gen')
sys.path.insert(0, str(ROOT / 'tmp/invoice_gen_deps'))
from jinja2 import Environment

data = json.loads((OUT / 'input.json').read_text(encoding='utf-8'))
env = Environment(autoescape=True)
templates = OUT / 'templates'
templates.mkdir(exist_ok=True)
shutil.copyfile(SOURCE / 'LICENSE', templates / 'LICENSE')
for name in ('formal_corporate', 'modern_minimal'):
    text = (SOURCE / 'templates' / f'{name}.html').read_text(encoding='utf-8')
    text = text.replace('</style>', '''
  .logo-area { max-width: 330px; }
  .logo-text { font-size: 20pt; }
  .brand { max-width: 360px; }
  .brand h1 { font-size: 18pt; letter-spacing: 0; }
  .invoice-badge { padding: 8px 12px; }
  .meta-value.large { font-size: 12pt; }
  .footer-note { color: #555; }
  tr { break-inside: avoid; }
</style>''')
    text = text.replace('Your account will be debited by', 'Invoice amount:').replace(' on {{ due_date_formatted }}', '; due {{ due_date_formatted }}.')
    text = text.replace('Payment Terms: 30 Days From Invoice Date', 'Payment terms: due on {{ due_date_formatted }}')
    (templates / f'{name}.html').write_text(text, encoding='utf-8')

for case in data['cases']:
    if 'copy_from' in case:
        continue
    record = data['records'][case['record_index']]
    ctx = dict(record)
    ctx.update(document_date_formatted=record['document_date'], due_date_formatted=record['due_date'],
               currency_symbol='EUR ', color_primary='#244663', payment_details=None, max=max)
    template = env.from_string((templates / (case['template'] + '.html')).read_text(encoding='utf-8'))
    (OUT / case['file_name'].replace('.pdf', '.html')).write_text(template.render(**ctx), encoding='utf-8')
print('Rendered four HTML files from fixed JSON and adapted upstream templates.')
