CREATE TABLE export_batches (
    export_id TEXT PRIMARY KEY,
    selection_hash TEXT NOT NULL UNIQUE,
    mapping_version TEXT NOT NULL,
    only_unexported INTEGER NOT NULL CHECK(only_unexported IN (0,1)),
    status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','writing','completed','failed')),
    attempts INTEGER NOT NULL DEFAULT 0 CHECK(attempts >= 0),
    file_path TEXT,
    file_sha256 TEXT,
    last_error TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
CREATE TABLE export_batch_items (
    export_id TEXT NOT NULL REFERENCES export_batches(export_id),
    ordinal INTEGER NOT NULL CHECK(ordinal >= 0),
    event_id TEXT NOT NULL REFERENCES review_events(event_id),
    invoice_id TEXT NOT NULL,
    review_revision INTEGER NOT NULL,
    PRIMARY KEY(export_id, invoice_id, review_revision),
    UNIQUE(export_id, ordinal),
    UNIQUE(export_id, event_id),
    FOREIGN KEY(invoice_id,review_revision) REFERENCES review_revisions(invoice_id,revision)
);
CREATE INDEX export_batch_items_invoice ON export_batch_items(invoice_id, review_revision);
CREATE TRIGGER export_batch_items_no_update BEFORE UPDATE ON export_batch_items
BEGIN SELECT RAISE(ABORT, 'Export membership is immutable'); END;
CREATE TRIGGER export_batch_items_no_delete BEFORE DELETE ON export_batch_items
BEGIN SELECT RAISE(ABORT, 'Export membership is immutable'); END;
CREATE TRIGGER export_batches_identity_no_update
BEFORE UPDATE OF export_id, selection_hash, mapping_version, only_unexported ON export_batches
BEGIN SELECT RAISE(ABORT, 'Export identity is immutable'); END;
