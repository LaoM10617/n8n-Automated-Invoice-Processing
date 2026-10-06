# AP intake backend

Local-only demo service. Implemented: PDF/JPEG/PNG intake, persistent originals,
SQLite receipts, replay protection, content-hash reuse and original retrieval.
Step 4 adds per-page text/OCR routing, configurable structured extraction, evidence checks,
deterministic validation and business-duplicate candidates. Step 5 adds persistent pending review tasks and a read-only page. Notifications and review decisions remain unimplemented.

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
No authentication is implemented; bind to loopback. Compose runs n8n and this API.
The image includes Poppler and Tesseract (English/German). Keep one Uvicorn worker: startup
marks interrupted processing attempts as failed so they can be retried.

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
`POST /api/ap/invoices/{invoice_id}/process` reads the saved original and persists extraction.
HTTP 200 means processing completed, not validation passed or approval granted.
Business issues are returned in `validation_issues`; technical failures return 502/503
and persist a failed attempt. Concurrent processing returns 409. Repeating a completed
pipeline version reuses its result. A new pipeline version creates a new attempt on the
next POST, preserving previous drafts. Failed retries reuse saved page text.
GET returns the latest attempt, original reference, raw extraction, evidence, normalized
fields, arithmetic result and current duplicate candidates. Missing identity means
`not_evaluable`, never a passed duplicate check. Before task creation, `review_status=not_created` and `review_url=null`; afterward GET returns the pending task and real URL.
`GET /health` reports implemented capabilities and database connectivity.

## Verification

```powershell
.venv/Scripts/python.exe -m pytest backend -q
```

Tests use temporary storage, never the normal database. They exercise all 16 first-round
PDFs, image intake, source conflicts, duplicates, concurrent replay and app recreation.
They do not measure OCR accuracy or prove n8n integration.

File writes are flushed before the database commit; handled failures remove new files.
A process crash between file creation and commit can leave an unreferenced original.
Orphan reconciliation, parser isolation and production upload limits remain future work.

## Model configuration and running Step 4

Set `AP_LLM_BASE_URL`, `AP_LLM_MODEL` and `AP_LLM_API_KEY` in the ignored project `.env`
(see `.env.example`), then run `docker compose up -d --build python-api`.
Current primary provider/model: Gemini / gemini-3.5-flash-lite, verified on one real invoice.
Historical full-set evaluation used OpenAI / gpt-4.1-mini. Keys are backend-only; do not
put them in workflow JSON, documentation or image build context. Health capability
`extraction` checks configuration presence only, not live provider availability.

Use http://127.0.0.1:5678/form/ap-intake-process-v2 for the locally published Step 4 form.
The exported workflow is inactive until imported and published in another instance.
The original template and Step 3 workflow are preserved; use v3 below to continue through review-task creation.

To repeat the paid-model development-fixture evaluation explicitly:

```powershell
.venv/Scripts/python.exe test_data/first_round/evaluate.py --process
```

Reference fields are used only by this evaluator, never by application extraction.
See `logs&architechture/step_04_field_evaluation.json` for measured differences.

## Processing limits

- Small-image pages with usable native text can stay native (SMALL_IMAGES_NOT_OCR warning).
  Safe single-image scans preserve original pixels/placement; composite pages render.
  Low-resolution images use a separate 2x OCR working copy. Heuristics and confidence
  do not certify recognition accuracy.
- Evidence validates literal source presence, not semantic field assignment.
- Header/totals extraction only; line items and multi-tax/discount/freight equations
  are not implemented. Adjustments or incomplete totals require manual review.
- Bare dollar signs and ambiguous numeric dates are not guessed. Supported currency
  precision is explicit in `validation.py`; other currencies require review.
- Supplier tax ID or exact normalized supplier name plus address, together with
  invoice number, identifies candidates. No fuzzy identity resolution or automatic merge.
- Processing is synchronous, with a 90-second model timeout and 100,000-character
  document-context limit. Large PDFs may exceed n8n's request timeout. This is a small
  local demo, not a production queue or public service.

## Switching models and protecting the free-tier quota

Change `AP_LLM_BASE_URL`, `AP_LLM_MODEL` and `AP_LLM_API_KEY` together in `.env`, then
run `docker compose up -d python-api`. `.env.example` shows the Gemini defaults.
No n8n changes are needed. No automatic provider fallback is enabled.
A process POST after a model/endpoint change creates a new attempt; changing settings
alone does not trigger bulk reprocessing. Historical model results remain in storage.

`AP_LLM_MIN_INTERVAL_SECONDS=60` enforces a minimum start interval within the single
worker. Requests during cooldown return 429 without reaching the provider. Provider
429 responses also stop immediately, with no retry. The gate resets on process restart;
it is not a shared quota manager or a guarantee against token/day limits.

The evaluator now defaults to `--limit 1 --interval 65`; larger runs must explicitly
set `--limit`. It stops on 429 and writes `step_04_field_evaluation_latest.json`, leaving
the historical full-set report intact. Do not repeatedly run the full set while tuning.

## Layout output

`processing_result.pages` retains `raw_text`, readable block text, `tokens`, `lines`,
`blocks`, `width`, `height` and `coordinate_unit` (pt or px). All boxes use top-left
x/y/width/height. Physical `row_id` preserves table-row relationships independently
of column-ordered readable text; `layout_uncertain` flags multi-fragment rows.
These are geometric regions, not semantic table cells. Embedded scans also record
`image_pdf_bbox`, `pdf_page_size`, `source_image_size` and `ocr_scale` for overlay mapping.
See `test_data/ocr_benchmark/README.md` for isolated PaddleOCR comparison reproduction.

## Step 5: read-only review

POST `/api/ap/invoices/{invoice_id}/review-task` after processing: 201 on creation,
200 on replay, 409 if the latest processing is incomplete. One task per invoice.
GET `/reviews/{invoice_id}` displays persisted fields, original pages, exceptions,
duplicate candidates and evidence. No editing, approval or rejection is available.
The page shows the latest attempt and warns if it differs from the task creation attempt.

Set `AP_PUBLIC_BASE_URL` to the URL a reviewer can open (default http://127.0.0.1:8000).
Keep the current unauthenticated demo loopback-only. PDF previews use Poppler at
`/api/ap/invoices/{invoice_id}/preview/{page}`; original bytes remain downloadable.
Rebuild with `docker compose up -d --build python-api`.

Current local workflow: http://127.0.0.1:5678/form/ap-intake-review-v3
Export: `n8n_workflows/01_AP_intake_review_v3.json` (import and publish on another instance).
The original template and earlier workflows are retained. Notification delivery is Step 6.
