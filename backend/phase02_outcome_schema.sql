CREATE TABLE outcome_notifications (
    notification_id TEXT PRIMARY KEY,
    event_id TEXT UNIQUE REFERENCES review_events(event_id),
    export_id TEXT UNIQUE REFERENCES export_batches(export_id),
    category TEXT NOT NULL CHECK(category IN ('review_approved','review_rejected','batch_completed')),
    status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','sending','sent','failed','unknown')),
    attempts INTEGER NOT NULL DEFAULT 0,
    message_id TEXT,
    last_error TEXT,
    delivery_status TEXT NOT NULL DEFAULT 'pending' CHECK(delivery_status IN ('pending','delivering','accepted','failed','unknown','processed')),
    delivery_attempts INTEGER NOT NULL DEFAULT 0,
    delivery_at TEXT,
    delivery_error TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    CHECK((event_id IS NOT NULL AND export_id IS NULL AND category IN ('review_approved','review_rejected')) OR
          (event_id IS NULL AND export_id IS NOT NULL AND category='batch_completed'))
);
CREATE TABLE outcome_notification_attempts (
    notification_id TEXT NOT NULL REFERENCES outcome_notifications(notification_id),
    attempt INTEGER NOT NULL,
    message_id TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL CHECK(status IN ('sending','sent','failed','unknown')),
    error_code TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    PRIMARY KEY(notification_id,attempt)
);
