## Unified AP runtime (2026-10-07)

Use the [unified canvas](http://127.0.0.1:5678/workflow/7xXB2pjXOE1EQ2bY) and [upload form](http://127.0.0.1:5678/form/ap-unified-intake-a2-v1). The export register and Mailpit URLs below are unchanged. Compose now targets `ap-unified-review-a2-v1` and `ap-unified-excel-a2-v1`; the privacy hook protects both production and test paths.

For a new instance, import `n8n_workflows/AP_unified_canvas_python_agent_v1_A4.json`, bind the existing Gmail and Header Auth credentials, load the privacy hook, publish, and verify the two single event targets. Importing JSON alone does not activate a workflow. Original 01/02 remain published for rollback. Use only one canvas per email batch. See `logs&architechture/AP_unified_canvas_A3_A4_log.md` for evidence, demo instructions and rollback. Native Agent migration is pending. The sections below describe the prior runtime.

## Final Phase02 runtime (2026-10-07)

Recommended [upload](http://127.0.0.1:5678/form/ap-approval-intake-v9),
[01 canvas](http://127.0.0.1:5678/workflow/APApprovalIntakeV9),
[02 canvas](http://127.0.0.1:5678/workflow/APReviewExportV1),
[export register](http://127.0.0.1:8000/exports), and
[local Mailpit](http://127.0.0.1:8025).
Both canvases are imported and published. Keep v7/v8 and historical workflows.
The recommended entry changed only after final acceptance; no old workflow was overwritten or disabled.

`docker compose up -d --build python-api` applies schema 5 idempotently.
Compose sets `AP_OUTCOME_AUTODISPATCH=1`, review webhook `ap-review-export-v1`
and batch webhook `ap-batch-export-v1`. The existing `APReviewEventLocalV1`
Header Auth credential must match the ignored `.env` token; never paste tokens in JSON.
For a new instance, import `01_AP_approval_intake_v9.json` and
`02_AP_review_export_v1.json` from `n8n_workflows/`, bind the existing Gmail and
Header Auth credentials, publish both, then restart n8n. Import alone is not activation.
The current instance has completed those steps; Gmail credential references are preserved,
but final acceptance uses cached synthetic uploads and does not re-run external Gmail/model calls.

Automatic intake dispatches the saved event through its handoff stage. Manual review
and batch creation dispatch after the database transaction through background tasks.
A restart may interrupt delivery, but cannot remove the saved decision or batch.
To retry one saved event through 02:
`docker compose exec -T python-api python -m backend.review_events EVENT_ID`.
Transport and SMTP attempts are bounded at five; HTTP 202 is only acceptance.
A review event becomes processed after its result notification is confirmed.
This does not mean Excel has been generated, downloaded or posted to accounting.

The review and batch panels expose **Refresh notification**, **Retry notification**
and **Check Mailpit**. Local API equivalents are GET
`/api/ap/result-notifications/{review|batch}/{id}` and POST its `/retry` or `/check`
with `X-AP-Review: 1` and a valid local Origin. Retry only sends the existing notification;
it never changes a decision or regenerates Excel. For `unknown` or interrupted `sending`,
wait at least 60 seconds and check Mailpit by the persisted Message-ID. If absent,
leave it unknown for investigation; do not blindly resend. SMTP is limited to local Mailpit.
Batch file recovery remains the separate `/api/ap/export-batches/{id}/retry` operation.

See `logs&architechture/phase02_final_log.md` for acceptance and retained evidence.
Earlier v8/receiver notes below describe historical stages.

## Phase02 review and approval (2026-10-07)

### Section 7: export register and combined Excel (current)

Open `/exports`, or **Open export register** from a review page. Approved immutable
snapshots appear immediately without n8n delivery or physical workbook updates.
Filter by inclusive invoice dates, literal supplier substring, currency and
**Not yet exported / All approved**. Preview totals are separate per currency.
Select records, then **Download Excel** to save one combined workbook (up to 500 rows).
New approvals appear on the next refresh and cannot change an earlier selection.
The database is authoritative; no `latest.xlsx`, local path setup or Excel synchronization.

- GET `/api/ap/export-register`: `date_from`, `date_to`, `supplier`, `currency`,
  `only_unexported` (default true). Approved snapshots only; Decimal totals as strings.
- POST `/api/ap/export-batches`: `{"event_ids":["..."],"only_unexported":true}`.
  Uses the same local `X-AP-Review: 1` and Origin protection as review writes.
  The server rechecks every event/current decision/snapshot, then freezes membership.
- GET `/api/ap/export-batches`: latest 30 batch records; GET `/{export_id}` adds
  verified file health, download URL and member invoice IDs/revisions.
- GET `/api/ap/export-batches/{export_id}/files/xlsx`: verified existing bytes only.
- POST `/api/ap/export-batches/{export_id}/retry`: explicit recovery of that exact batch.

Schema 4 adds `export_batches` and immutable `export_batch_items`. The register is a
query of existing approval records, so no copied fields or approval backfill is needed.
A unique hash of sorted event IDs reuses the same batch across reversed selections,
retries, mode changes and mapping deployments. Different selected sets intentionally
produce different combined files, even if some invoices also appear in earlier files.
The not-yet-exported mode checks completion and active reservations transactionally;
a stale/overlapping selection returns 409. It includes historical single exports when
determining completion. Exported means file generation succeeded, not download receipt,
accounting submission or payment. A damaged completed file remains historical exported
and must be recovered under its existing ID, not silently put into a new batch.

`invoice-excel-v1` columns are unchanged. Each combined row contains its invoice ID,
approved revision and the batch ID in Export ID. Amounts are numeric and round-trip
checked with Decimal and currency precision; dates use `yyyy-mm-dd`; optional values
remain blank. Text is literal, including formula-like prefixes and leading zeros.
The file has English headers, freeze/filter, and the notice
`Invoice export — not submitted to an accounting system`. No formulas/macros/external links.
Amounts exceeding Excel's reliable precision fail rather than silently rounding.

Files live in `data/ap/exports/batches/<export_id>.xlsx`. The shared export service
commits an attempt before writing, uses a 60-second claim lease and a write transaction
to fence stale writers, then fsync/atomic replace and read-back snapshot/hash checks.
Explicit attempts are limited to five. A saved file without completion is verified
and reused; missing/corrupt completed files recover with the original ID, members and
SHA256. GET never regenerates. Downloading an intact file consumes no attempts.

Historical single files and `/api/ap/exports` remain compatible, including original
hashes and recovery. The review page retains existing single-file download links but
uses the register as its primary export action. `scripts/verify_phase02_exports.py`
records the earlier single-file acceptance; use `scripts/verify_phase02_export_register.py
verify` for this version. The backup action is a one-time pre-schema-4 rehearsal.

The section-6 n8n receiver remains unchanged: it receives and reloads review events;
it does not automatically generate files. Subsequent 02 integration should notify
approval/register availability, and distinguish that from batch-file completion.
Result notifications remain unimplemented; batch notification storage will need its
own batch association instead of the existing single-export foreign key. No model,
mail or external-accounting call occurs during register preview or Excel creation.

### Section 6: durable event delivery

Decisions commit before network delivery. Delivery is explicit in this version:
`docker compose exec -T python-api python -m backend.review_events EVENT_ID`.
Find the event ID and visible delivery status/attempts/error in the review API/page.
Each command attempts one delivery; the cumulative limit is five per event. Pending,
failed, unknown and accepted events can be retried with the same ID. A live delivery
holds a 60-second lease; after a process interruption, wait for that lease before retrying.
No automatic loop, startup sweep, or background queue is enabled. At the limit, stop
and reconcile the receiver before operator recovery; do not create a new decision/event.

The independent `02_AP_review_events_v1.json` (`APReviewEventsV1`) receives at
`/webhook/ap-review-events-v1`, acknowledges HTTP 202, then reloads the authoritative
decision through authenticated GET `/api/ap/review-events/{event_id}`. It carries only
IDs, revision and event type, and checks the saved event against the current final
task and immutable snapshot. Rejected events return `can_export: false`.
The future export endpoint must independently reuse this check and read the snapshot.

`accepted` means HTTP receipt only. Downstream failures and lost responses remain
replayable. No endpoint in section 6 marks an event `processed`. Excel is now available
through the separate section-7 service; result notifications and receiver-to-export
wiring remain pending. Approval pages show the actual saved export/file state.

For another local instance: run `scripts/configure_review_event_local.py`, import
the workflow, bind `AP review event local header`, publish and restart n8n. Recreate
python-api after adding the ignored `.env` token. Compose mounts the required
`scripts/n8n_review_header_privacy.cjs` external hook; it retains Header Auth access
while excluding the secret from serialized request headers, only for this receiver.
n8n 2.42.3 saves initial execution payloads even when execution saving is disabled;
those settings alone are insufficient. Do not activate this receiver without the hook.
Verify a new authenticated request with `scripts/check_review_event_privacy.py` after
n8n upgrades. Credentials belong only in `.env` and encrypted n8n credential storage.

Verification: `scripts/phase02_event_probe.py` is a local fault-injection tool, not
an automatic retry worker. `lost-response` makes a real request and then injects a
client-side timeout; it does not simulate a physical network outage.

The local review page now supports **Save changes**, **Approve** and **Reject**.
Machine drafts/evidence remain unchanged. Saved revisions are immutable, stale
revision/analysis submissions return 409, and approvals rerun deterministic checks.
Enter a reason and original page for corrections. Resolve each evidence issue or
duplicate candidate explicitly; arithmetic errors cannot be acknowledged away.
For each duplicate, select **Not a duplicate**, **Justified continuation**, or
**Confirmed duplicate — reject**, with a reason and original page. Unresolved
candidates block either decision; confirmed duplicates block approval. Saving
records both the candidate fingerprint and its invoice ID. Field edits clear
the page's selected resolutions so they must be checked again before saving.
If analysis changed, compare it and explicitly accept the new attempt. Existing
manual values are retained. Final invoices cannot be reanalyzed; cached replay is allowed.

The opt-in [v8 editor](http://localhost:5678/workflow/APApprovalIntakeV8) and
[v8 upload](http://127.0.0.1:5678/form/ap-approval-intake-v8) add deterministic
approval for newly created tasks. EUR gross total must satisfy `0 < total < 10000.00`
and every validation/evidence/quality/duplicate gate must pass. Other cases remain
pending and notify the local Mailpit reviewer. Historical pending tasks are not
automatically reevaluated. Human revisions always require manual approval.
v7 and historical JSON are preserved; v7 remains the Phase01 demonstration entry.

Review API: GET/PATCH `/api/ap/invoices/{invoice_id}/review`, POST
`/api/ap/invoices/{invoice_id}/review/decision`. Writes require `X-AP-Review: 1`
and same-origin browser requests on the local host. Send `expected_revision` and
`processing_attempt_id`; decisions also require a unique `request_id`. This is a
local demo reviewer, not authenticated multi-user access. The explicit local
POST `/api/ap/invoices/{invoice_id}/review/evaluate-policy` applies the policy to
a selected pending record; it is never invoked on startup or in a batch.

PATCH `duplicate_resolutions` items require `id`, `disposition` (`not_duplicate`,
`justified_continue`, or `confirmed_duplicate`), `reason`, and `page`. Existing
saved resolutions without a disposition retain their earlier justified-continuation
meaning. GET includes `decision_gate` with `can_approve`, `can_reject`, and prerequisite
`blockers`. Decision payloads cannot include unsaved field or resolution changes.
Reject always requires a reason, including replays. Final reads and replays return
the saved decision validation snapshot rather than recomputing historical results.

Automatic/manual decisions share a snapshot and transactional outbox event.
**Event delivery and explicit Excel generation are implemented.** The 02 canvas still
needs its export/result stages. No accounting submission or payment occurs.
SQLite schema version is 3; the request ledger rejects reuse with
different content, including aliases used when replaying a final decision.

Import `n8n_workflows/01_AP_approval_intake_v8.json` independently, retain its ID,
bind the existing readonly Gmail credential on another instance, then publish.
Its 15 execution nodes and two notes expose business decisions; Python owns
validation, versions, policy and persistence. This step verified real upload and
local review, not a new Gmail run. Three labeled synthetic PDFs/cached analyses
were used without provider calls. See `logs&architechture/phase02_review_log.md`.

## Default demo entry (Phase01 refactor steps 4–5 accepted; historical below)

Use [v7 editor](http://localhost:5678/workflow/APAgentIntakeV7) or
[v7 upload form](http://127.0.0.1:5678/form/ap-agent-intake-v7).
Select **Run Gmail Batch** to replay the existing readonly five-message batch.
The canvas and workflow JSON are unchanged; v5/v6 remain historical versions.
The older setup notes below describe previous stages, not the default entry.

69 backend tests pass. Control verification uses a virtual clock and fake models;
a separate child process exits abruptly to exercise persisted interruption state.
Existing real-provider and real-Gmail execution evidence is retained instead of
repeating paid model calls. See `logs&architechture/phase01_step45_verification.json`.

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

Historical v3 workflow: http://127.0.0.1:5678/form/ap-intake-review-v3
Export: `n8n_workflows/01_AP_intake_review_v3.json` (import and publish on another instance).
The original template and earlier workflows are retained. Notification delivery is Step 6.


## Historical deterministic refactor (v6)

The existing structured extractor is unchanged; no Agent or LangChain is installed yet. `document_stages.py` separates reading, persisted raw analysis and deterministic validation. Legacy `/process` delegates to these services. `intake_stages.py` stores `ap-stage-v1` contracts and event history; n8n passes only run IDs after intake.

- POST `/api/ap/stages/archive`: multipart `metadata` (Source JSON) and optional `file`.
- POST `/api/ap/stages/{run_id}/analyze`: reuse the configured extraction cache or execute the current extractor.
- POST `/api/ap/stages/{run_id}/validate`: validate/save, identify duplicates and create/reuse the pending task.
- POST `/api/ap/stages/{run_id}/notify`: independent claim, local Mailpit SMTP and result persistence.
- POST `/api/ap/stages/{run_id}/exception`: acknowledge an already-persisted failed/skipped outcome.
- GET `/api/ap/stages/{run_id}`: durable current result.

Business outcomes (`continue`, `review_ready`, `failed`, `skipped`) are distinct from HTTP transport success. Failed/skipped runs pass through later processing stages without extraction. Invalid stage order returns 409; missing runs return 404. Email metadata requires a batch and case ID. Model/service failures are recorded at the originating stage, before any exception node. A retry uses the same source identity through archive; invoice/receipt/task reuse is enforced by existing storage rules.

The synchronous compact analysis stage waits for the local cooldown up to 65 seconds, then each provider call still passes the original rate gate. Provider errors are not retried or switched to another provider. Use one application worker. Larger/multi-round Agent execution will require a separate design; it is not implemented here.

Notifications use port 1025 and host `mailpit` by default. `AP_MAILPIT_HOST` may select localhost/127.0.0.1 for isolated local verification only. No external SMTP hosts or credentials are supported. Sending/unknown claims require reconciliation instead of blind retries. This service shares the claim ledger with the legacy n8n SMTP workflow.

See `logs&architechture/phase01_refactor_log.md` for baseline comparison, evidence, limitations and rollback instructions.


## LangChain invoice analysis (v7)

The analysis stage now uses `backend/invoice_agent.py`: LangChain `create_agent`,
Gemini native tool calling, and the existing `Extraction` schema. It exposes only
current-document page reading, literal evidence search and OCR quality tools.
OCR, grounding, arithmetic, duplicate detection and state changes remain deterministic.
`AP_LLM_*` environment variables remain required; only the configured Gemini
endpoint is supported by this adapter. No OpenAI fallback is enabled.

Each analysis permits at most three model requests and six document-tool calls.
The last model request has only the structured-output tool available. Requests
are paced at least 60 seconds apart within the single backend process; restart
and multiworker global rate limiting are not implemented. Provider retries and
schema retries are disabled. Do not bulk-reprocess the historical corpus.

The analysis signature versions prompts, tools and schema separately from OCR.
Old extraction attempts remain available but cannot satisfy the agent cache.
`processing_result.agent_trace` holds local execution metadata (not reasoning);
the review page shows this saved trace. `analysis_cached` on stage responses
identifies reuse rather than a fresh agent run. LangSmith tracing is disabled.
On single-worker application restart, unfinished attempts become failed with
`PROCESS_INTERRUPTED`. Their Agent trace becomes `interrupted`; a model call that
had not returned becomes `unknown`, while completed calls and tools are preserved.
No automatic model retry occurs. Inspect the invoice attempt before explicitly
resubmitting the same source. The intake run can retain its last saved `read`
checkpoint; it is not proof that analysis completed. A completed `analyzed`
checkpoint remains eligible for validation without another model call.
There is no autonomous retry queue. The rate gate is process-local: after a
restart wait at least the configured interval before starting fresh analysis.
Cross-process/restart rate enforcement and provider-side cancellation are not
claimed. Stopping an n8n execution does not guarantee cancellation of an in-flight
backend/provider request.

Open `http://localhost:5678/workflow/APAgentIntakeV7` and choose **Run Gmail Batch**
for the existing readonly five-message test batch. The upload entry is
`http://127.0.0.1:5678/form/ap-agent-intake-v7`. Valid invoices remain pending review.
The HTTP node calls a real Python Agent; it is not an n8n built-in AI Agent node.
