CREATE TABLE review_requests (
    request_id TEXT PRIMARY KEY,
    invoice_id TEXT NOT NULL REFERENCES invoices,
    request_hash TEXT NOT NULL,
    event_id TEXT NOT NULL REFERENCES review_events(event_id)
);
