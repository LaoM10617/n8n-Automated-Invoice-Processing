"""Durable provider start spacing shared by both invoice executors."""
from contextlib import closing
from contextvars import ContextVar
import time
from backend.document_text import ProcessingError

current_gate = ContextVar('invoice_model_gate', default=None)


class ModelGate:
    def __init__(self, connect, clock=time.time, sleep=time.sleep):
        self.connect, self.clock, self.sleep = connect, clock, sleep
        with closing(connect()) as db:
            db.execute('CREATE TABLE IF NOT EXISTS model_request_gate (id INTEGER PRIMARY KEY CHECK(id=1), next_at REAL NOT NULL)')
            db.execute('INSERT OR IGNORE INTO model_request_gate VALUES(1,0)')
            db.commit()

    def remaining(self):
        with closing(self.connect()) as db:
            return max(0, db.execute('SELECT next_at FROM model_request_gate WHERE id=1').fetchone()[0] - self.clock())

    def wait(self):
        remaining = self.remaining()
        if remaining > 65:
            raise ProcessingError('MODEL_LOCAL_RATE_LIMIT', 'Provider cooldown exceeds the synchronous request budget.')
        if remaining:
            self.sleep(remaining)

    def reserve(self, interval):
        with closing(self.connect()) as db:
            db.execute('BEGIN IMMEDIATE')
            now = self.clock()
            if db.execute('SELECT next_at FROM model_request_gate WHERE id=1').fetchone()[0] > now:
                raise ProcessingError('MODEL_LOCAL_RATE_LIMIT', 'Provider cooldown is active; no request was sent.')
            db.execute('UPDATE model_request_gate SET next_at=? WHERE id=1', (now + max(60.1, interval),))
            db.commit()
