"""Bounded, explicit outbox delivery. HTTP acceptance is never business completion."""
import argparse
from contextlib import closing
from datetime import datetime, timezone, timedelta
import hmac
import json
import os
from pathlib import Path
import sqlite3
import urllib.error
import urllib.request
from urllib.parse import urlparse

from fastapi import HTTPException, Request

MAX_ATTEMPTS = 5
LEASE_SECONDS = 60
IDENTIFIERS = ('event_id', 'invoice_id', 'review_id', 'review_revision', 'event_type')


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def send_event(url, token, payload):
    request = urllib.request.Request(url, data=json.dumps(payload).encode(), method='POST',
                                     headers={'Content-Type': 'application/json', 'X-AP-Event-Token': token})
    # Never forward the credential to a redirect target or environment proxy.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    with opener.open(request, timeout=10) as response:
        return response.status


class ReviewEvents:
    def __init__(self, connect, sender=send_event):
        self.connect, self.sender = connect, sender

    def load(self, db, event_id):
        event = db.execute('SELECT * FROM review_events WHERE event_id=?', (event_id,)).fetchone()
        if not event:
            raise HTTPException(404, 'Review event not found.')
        event = dict(event)
        task = db.execute('SELECT * FROM review_tasks WHERE review_id=? AND invoice_id=?',
                          (event['review_id'], event['invoice_id'])).fetchone()
        snapshot = db.execute('SELECT * FROM review_revisions WHERE review_id=? AND invoice_id=? AND revision=?',
                              (event['review_id'], event['invoice_id'], event['review_revision'])).fetchone()
        if not task or not snapshot or task['status'] != event['event_type'] or task['current_revision'] != event['review_revision']:
            raise HTTPException(409, 'Event does not match the current final decision and snapshot.')
        if event['event_type'] == 'approved' and not json.loads(snapshot['validation_json'])['can_approve']:
            raise HTTPException(409, 'The approval snapshot is not eligible.')
        return event, task, snapshot

    def read(self, event_id):
        with closing(self.connect()) as db:
            db.execute('BEGIN')
            event, task, snapshot = self.load(db, event_id)
            return {**{key: event[key] for key in IDENTIFIERS},
                    'status': event['status'], 'attempts': event['attempts'], 'max_attempts': MAX_ATTEMPTS,
                    'last_error': event['last_error'], 'accepted_at': event['accepted_at'],
                    'processed_at': event['processed_at'], 'review_status': task['status'],
                    'snapshot_revision': snapshot['revision'], 'can_export': task['status'] == 'approved',
                    'business_processed': event['status'] == 'processed'}

    def deliver(self, event_id):
        url = os.environ.get('AP_REVIEW_EVENT_URL', '')
        token = os.environ.get('AP_REVIEW_EVENT_TOKEN', '')
        parsed = urlparse(url)
        if not token or parsed.scheme != 'http' or parsed.hostname not in ('n8n', 'localhost', '127.0.0.1') or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise HTTPException(503, 'Configure the local review webhook and credential before delivery.')
        now = datetime.now(timezone.utc)
        with closing(self.connect()) as db:
            db.execute('BEGIN IMMEDIATE')
            event, _, _ = self.load(db, event_id)
            if event['status'] == 'processed':
                return self.read(event_id)
            if event['status'] == 'delivering' and datetime.fromisoformat(event['last_attempt_at']) > now - timedelta(seconds=LEASE_SECONDS):
                raise HTTPException(409, 'Delivery is in progress. Retry after the 60-second lease expires.')
            if event['attempts'] >= MAX_ATTEMPTS:
                raise HTTPException(409, 'Delivery attempt limit reached. Inspect the receiver before operator recovery.')
            attempt = event['attempts'] + 1
            db.execute("UPDATE review_events SET status='delivering',attempts=?,last_attempt_at=?,last_error=NULL WHERE event_id=?",
                       (attempt, now.isoformat(), event_id))
            db.commit()
        # Claim is committed before any network I/O; decisions cannot be rolled back by transport errors.
        try:
            status = self.sender(url, token, {key: event[key] for key in IDENTIFIERS})
            outcome, error = ('accepted', None) if 200 <= status < 300 else ('failed', f'HTTP_{status}')
        except urllib.error.HTTPError as exc:
            outcome, error = 'failed', f'HTTP_{exc.code}'
        except (OSError, urllib.error.URLError, TimeoutError):
            # A timeout can occur after receiver execution; the same event remains replayable.
            outcome, error = 'unknown', 'TRANSPORT_UNCONFIRMED'
        with closing(self.connect()) as db:
            db.execute('''UPDATE review_events SET status=?,last_error=?,
                       accepted_at=CASE WHEN ?='accepted' THEN ? ELSE accepted_at END
                       WHERE event_id=? AND status='delivering' AND attempts=?''',
                       (outcome, error, outcome, now.isoformat(), event_id, attempt))
            db.commit()
        return self.read(event_id)


def protect_event(request):
    expected = os.environ.get('AP_REVIEW_EVENT_TOKEN', '')
    supplied = request.headers.get('x-ap-event-token', '')
    if not expected or not hmac.compare_digest(expected.encode(), supplied.encode()):
        raise HTTPException(403, 'Event credential required.')


def register_review_events(app, connect):
    service = ReviewEvents(connect)

    @app.get('/api/ap/review-events/{event_id}')
    def read(event_id: str, request: Request):
        protect_event(request)
        return service.read(event_id)

    return service


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Deliver one saved review event once; at most five attempts per event.')
    parser.add_argument('event_id')
    args = parser.parse_args()
    database = Path(os.environ.get('AP_DATA_DIR', 'data/ap')) / 'invoices.sqlite3'
    def connect():
        db = sqlite3.connect(database.resolve().as_uri() + '?mode=rw', uri=True, timeout=30)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        return db
    try:
        print(json.dumps(ReviewEvents(connect).deliver(args.event_id)))
    except HTTPException as exc:
        parser.exit(1, f'{exc.status_code}: {exc.detail}\n')
