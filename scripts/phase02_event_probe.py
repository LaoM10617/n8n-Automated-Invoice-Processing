"""Local transport probes over existing synthetic decision events; no models or new decisions."""
import argparse
from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
import sys
import urllib.error
import urllib.request

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
from backend.review_events import ReviewEvents, send_event

parser = argparse.ArgumentParser()
parser.add_argument('mode', choices=['deliver', 'lost-response', 'unauthenticated'])
parser.add_argument('event_id', nargs='?')
parser.add_argument('--label', default='probe')
args = parser.parse_args()
url = 'http://127.0.0.1:5678/webhook/ap-review-events-v1'
token = next(line.split('=', 1)[1].strip() for line in (root / '.env').read_text(encoding='utf-8').splitlines() if line.startswith('AP_REVIEW_EVENT_TOKEN='))
os.environ['AP_REVIEW_EVENT_URL'] = url
os.environ['AP_REVIEW_EVENT_TOKEN'] = token
def connect():
    db = sqlite3.connect((root / 'data/ap/invoices.sqlite3').as_uri() + '?mode=rw', uri=True, timeout=30)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA foreign_keys=ON')
    return db

if args.mode == 'unauthenticated':
    try:
        with urllib.request.urlopen(urllib.request.Request(url, data=b'{}', headers={'Content-Type': 'application/json'}), timeout=10) as response:
            status = response.status
    except urllib.error.HTTPError as exc:
        status = exc.code
    assert status in (401, 403), status
    result = {'unauthenticated_status': status}
else:
    def response_lost(url, token, payload):
        assert send_event(url, token, payload) == 202
        # Real receiver call, then a client-side lost-response fault. Not a physical network outage.
        raise TimeoutError()
    result = ReviewEvents(connect, response_lost if args.mode == 'lost-response' else send_event).deliver(args.event_id)
path = root / 'logs&architechture/phase02_step6_verification.json'
report = json.loads(path.read_text(encoding='utf-8'))
report.setdefault('probes', []).append({'label': args.label, 'mode': args.mode, 'result': result})
path.write_text(json.dumps(report, indent=2), encoding='utf-8')
print(json.dumps(result))
