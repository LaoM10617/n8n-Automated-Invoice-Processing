CREATE TABLE review_tasks_new (
    review_id TEXT PRIMARY KEY,
    invoice_id TEXT UNIQUE NOT NULL REFERENCES invoices,
    status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','approved','rejected')),
    created_attempt_id INTEGER NOT NULL REFERENCES processing_attempts(attempt_id),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    current_revision INTEGER NOT NULL DEFAULT 0 CHECK(current_revision >= 0),
    extraction_attempt_id INTEGER REFERENCES processing_attempts(attempt_id),
    decided_by TEXT,
    decided_at TEXT,
    approval_method TEXT CHECK(approval_method IN ('automatic','manual')),
    policy_version TEXT,
    policy_inputs_json TEXT,
    routing_reason TEXT,
    UNIQUE(review_id, invoice_id)
);
INSERT INTO review_tasks_new(review_id,invoice_id,status,created_attempt_id,created_at,extraction_attempt_id)
SELECT review_id,invoice_id,status,created_attempt_id,created_at,created_attempt_id FROM review_tasks;
DROP TABLE review_tasks;
ALTER TABLE review_tasks_new RENAME TO review_tasks;

CREATE TABLE review_revisions (
    review_id TEXT NOT NULL,
    invoice_id TEXT NOT NULL,
    revision INTEGER NOT NULL CHECK(revision > 0),
    processing_attempt_id INTEGER NOT NULL REFERENCES processing_attempts(attempt_id),
    fields_json TEXT NOT NULL,
    changes_json TEXT NOT NULL,
    validation_json TEXT NOT NULL,
    duplicate_resolution_json TEXT NOT NULL,
    evidence_resolution_json TEXT NOT NULL,
    actor TEXT NOT NULL,
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    PRIMARY KEY(review_id, revision),
    UNIQUE(invoice_id, revision),
    FOREIGN KEY(review_id,invoice_id) REFERENCES review_tasks(review_id,invoice_id)
);
CREATE TRIGGER review_revisions_no_update BEFORE UPDATE ON review_revisions
BEGIN SELECT RAISE(ABORT, 'Review revisions are immutable'); END;
CREATE TRIGGER review_revisions_no_delete BEFORE DELETE ON review_revisions
BEGIN SELECT RAISE(ABORT, 'Review revisions are immutable'); END;

CREATE TABLE review_events (
    event_id TEXT PRIMARY KEY,
    review_id TEXT NOT NULL UNIQUE,
    invoice_id TEXT NOT NULL,
    review_revision INTEGER NOT NULL,
    event_type TEXT NOT NULL CHECK(event_type IN ('approved','rejected')),
    request_id TEXT UNIQUE,
    request_hash TEXT,
    status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','delivering','accepted','processed','failed','unknown')),
    attempts INTEGER NOT NULL DEFAULT 0 CHECK(attempts >= 0),
    last_error TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    last_attempt_at TEXT,
    accepted_at TEXT,
    processed_at TEXT,
    FOREIGN KEY(review_id,invoice_id) REFERENCES review_tasks(review_id,invoice_id),
    FOREIGN KEY(review_id,review_revision) REFERENCES review_revisions(review_id,revision)
);
CREATE TABLE exports (
    export_id TEXT PRIMARY KEY,
    event_id TEXT NOT NULL REFERENCES review_events(event_id),
    invoice_id TEXT NOT NULL,
    review_revision INTEGER NOT NULL,
    target TEXT NOT NULL DEFAULT 'excel' CHECK(target='excel'),
    mapping_version TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','writing','completed','failed')),
    file_path TEXT,
    file_sha256 TEXT,
    last_error TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    UNIQUE(invoice_id,review_revision,target),
    FOREIGN KEY(invoice_id,review_revision) REFERENCES review_revisions(invoice_id,revision)
);
CREATE TABLE result_notifications (
    notification_id TEXT PRIMARY KEY,
    event_id TEXT NOT NULL REFERENCES review_events(event_id),
    export_id TEXT REFERENCES exports(export_id),
    category TEXT NOT NULL CHECK(category IN ('export_completed','review_rejected')),
    status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','sending','sent','failed','unknown')),
    attempts INTEGER NOT NULL DEFAULT 0 CHECK(attempts >= 0),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    UNIQUE(event_id,category),
    CHECK((category='export_completed' AND export_id IS NOT NULL) OR
          (category='review_rejected' AND export_id IS NULL))
);
CREATE TABLE result_notification_attempts (
    attempt_id INTEGER PRIMARY KEY AUTOINCREMENT,
    notification_id TEXT NOT NULL REFERENCES result_notifications(notification_id),
    status TEXT NOT NULL CHECK(status IN ('sending','sent','failed','unknown')),
    message_id TEXT,
    error_code TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
