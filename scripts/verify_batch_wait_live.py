"""Replay a saved native analysis through the published form; never request fresh inference."""
import json
from pathlib import Path
import sqlite3
import urllib.request
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
db = sqlite3.connect((ROOT / 'data/ap/invoices.sqlite3').as_uri() + '?mode=ro', uri=True)
before = {t: db.execute('SELECT COUNT(*) FROM ' + t).fetchone()[0]
          for t in ('processing_attempts', 'native_analysis', 'review_events', 'export_batches')}
payload = (ROOT / 'data/native-b3-samples/text.pdf').read_bytes()
boundary = 'batch-wait-' + str(uuid4())
source = 'native-batch-wait-cached-20261007'
body = (f'--{boundary}\r\nContent-Disposition: form-data; name="field-0"\r\n\r\n{source}\r\n'
        f'--{boundary}\r\nContent-Disposition: form-data; name="field-1"; filename="cached-native-demo.pdf"\r\n'
        'Content-Type: application/pdf\r\n\r\n').encode() + payload + f'\r\n--{boundary}--\r\n'.encode()
request = urllib.request.Request('http://127.0.0.1:5678/form/ap-native-intake-b2-v2', data=body,
                                 headers={'Content-Type': f'multipart/form-data; boundary={boundary}'})
with urllib.request.urlopen(request, timeout=45) as response:
    result = json.load(response)
assert result['analysis_cached'] and result['analysis_source'] == 'native_provider_analysis', result
assert result['review_status'] == 'approved' and not result['new_invoice']
assert result['source']['notification_mode'] == 'batch'
after = {t: db.execute('SELECT COUNT(*) FROM ' + t).fetchone()[0] for t in before}
assert before == after
report = {'cached_upload': result, 'before': before, 'after': after, 'new_model_calls': 0,
          'scope': 'Real published form, existing approved native analysis; not fresh inference or new approval.'}
(ROOT / 'logs&architechture/AP_batch_wait_live_verification.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
print(json.dumps({'run_id': result['run_id'], 'approved': True, 'cached': True, 'new_model_calls': 0}))
