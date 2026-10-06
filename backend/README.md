# AP intake backend

Local-only demo service. Implemented: PDF/JPEG/PNG intake, persistent originals,
SQLite receipts, replay protection, content-hash reuse and original retrieval.
OCR, extraction, business validation, review and notifications are not implemented.

From the project root, with Python 3.12:

```powershell
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r backend/requirements-dev.txt
.venv/Scripts/python.exe -m uvicorn backend.app:create_app --factory --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000/docs` for the generated API schema and upload form.
This session already installed the dependencies into `.venv` using the bundled
runtime's pip. If that environment has no pip module, use the bundled pip with
`--python .venv/Scripts/python.exe`; the server command above remains valid.

Default storage: `data/ap/`. Set `AP_DATA_DIR` to change it. Keep both the SQLite
database and `originals/` across restarts. Run one local worker for this demo.
No authentication is implemented; bind to loopback. Container integration is pending.

## Intake

`POST /api/ap/intakes` accepts multipart fields:

- `file`: one PDF, JPEG or PNG, up to 20 MiB; PDFs up to 50 pages, unencrypted.
- `source_type`: `upload` or `email`.
- `source_namespace`: stable upload-client identifier or provider/mailbox identifier.
- `source_id`: stable upload event ID or provider message ID.
- `attachment_id`: stable attachment ID or index within that source.

The four source fields form the idempotency key. Keep them unchanged on retry.
Same key and bytes: HTTP 200, same receipt. Same key with different bytes: HTTP 409.
New key: HTTP 201 and a new receipt. Identical bytes reuse the same invoice record;
this is content deduplication, not supplier/invoice-number business matching.
Different file bytes always create a new invoice candidate at this stage.

File format is inspected from bytes, not the filename or submitted MIME type.
`ocr_required=true` identifies images or PDFs with at least one empty-text page.
False does **not** certify text quality: `text_quality_assessed=false` remains explicit.
No extracted invoice fields or review link are fabricated.

`GET /api/ap/invoices/{invoice_id}` returns stored metadata and receipts.
`GET /api/ap/invoices/{invoice_id}/original` returns original bytes.
`POST /api/ap/invoices/{invoice_id}/process` returns HTTP 501 for an existing invoice.
`GET /health` reports implemented capabilities and database connectivity.

## Verification

```powershell
.venv/Scripts/python.exe -m pytest backend/test_intake.py -q
```

Tests use temporary storage, never the normal database. They exercise all 16 first-round
PDFs, image intake, source conflicts, duplicates, concurrent replay and app recreation.
They do not measure OCR accuracy or prove n8n integration.

File writes are flushed before the database commit; handled failures remove new files.
A process crash between file creation and commit can leave an unreferenced original.
Orphan reconciliation, parser isolation and production upload limits remain future work.
