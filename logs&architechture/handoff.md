# Handoff — AP invoice test fixtures

Date: 2026-10-06

## Latest implementation — Step 5 review (2026-10-06)

Persistent review tasks and read-only review pages are deployed. n8n APIntakeReviewV3 is imported, published and tested at /form/ap-intake-review-v3. Replays reuse the task; source conflicts stop at intake. Poppler page previews replace an iframe that rendered blank in the browser. 49 tests pass; real container recreation preserves the task and original. No model calls or Git commit this turn. Next: Step 6 local Mailpit notification, with notification status separate from task creation. Approval/rejection/editing/export remain unimplemented. See log_2026-10-06_step05_review.md and step_05_review_verification.json.

## Latest verification — Gemini field ownership (2026-10-06)

Three real Gemini calls, at least 65 seconds apart, no retries/OpenAI/bulk run. Same-model OCR11 old-input comparison: 8/10 checked fields; new input: 9/10. New input recovers net amount and supplier city/state/postcode, but still omits Causeway from supplier address because layout isolates that word. Evidence checks do not detect this omission. Alternate text-layout A: 9/9 fields match. This is a single-run combined reading/layout diagnostic, not a controlled repeated benchmark or buyer-field extraction. New process results are persisted; old attempts retained. See log_2026-10-06_layout_gemini_validation.md and the three layout_gemini_* evidence JSON files. Guide now marks Step 4 as implemented with this open quality issue; next is Step 5, idempotent review tasks and a real minimal read-only review page. No review tasks created or code changed in this verification. No Git commit.

## Latest implementation — Local layout and Paddle comparison (2026-10-06)

Migrated SITECO geometry ideas into backend/pdf_layout.py; source project unchanged. Native PDF word boxes use pdfplumber 0.11.10. Small-image pages can stay native with an explicit warning; safe single-scan pages preserve original pixels and placement. Low-resolution images use a separate 2x OCR working image. All paths retain tokens, physical rows, lines, blocks, raw text, units and page dimensions. Gemini now receives row/block metadata, but no LLM calls were made in this change. Version: layout-quality-v3 / step4-layout-v1. The rebuilt backend is deployed; n8n unchanged. Existing stored results are not automatically rerun.

47 tests pass. All 16 fixtures completed offline reading. Three diagnostic cases: previous Tesseract 24/26 selected literal spans; optimized Tesseract 26/26; isolated PaddleOCR mobile 26/26. This is a tuned diagnostic comparison, not semantic field accuracy or held-out OCR accuracy. Paddle is slower here and remains benchmark-only. Reproduction scripts under test_data/ocr_benchmark; decision, caveats and results in decision_2026-10-06_local_layout.md, local_layout_results.json, ocr_layout_comparison.json, paddle_ocr_comparison_raw.json and tesseract_variants_raw.json. Next: small paced Gemini validation of field ownership on OCR11/new layouts; review task/page still pending. No Git commit.

## Latest fix — OCR TSV parsing (2026-10-06)

Diagnosed OCR 11: TSV quote handling leaked control rows into text; fixed with QUOTE_NONE and regression coverage. 43 tests pass; backend deployed. Current page version text-quality-v2 and pipeline step4-v6 invalidate old OCR caches on explicit processing, without automatic model calls. Six local-only Tesseract probes on original/resized OCR 11 images recovered 739.69 under all tested configurations; supplier text/column ordering varied. This is not an end-to-end benchmark. Historical supplier-address misclassification was also found outside the original eight-field score. Read-only SITECO parser review and candidate-engine research are recorded in `ocr_quality_review_2026-10-06.md`. Layout migration/image routing remains proposed, not implemented. No provider calls or Git commit in this change.

## Latest configuration — Gemini primary (2026-10-06)

User preference supersedes the previous OpenAI default. Active `.env`: Gemini `gemini-3.5-flash-lite` through Google's OpenAI-compatible endpoint. Only one real Gemini extraction was called and passed for invoice A; no OpenAI calls in this change. Previous 16-document metrics remain OpenAI-only. Model URL/name/key are the switching interface; recreate python-api after changing them. No automatic fallback. A 60-second single-worker request gate and explicit 429 errors prevent rapid repeated requests. Evaluator defaults to one document, spaces batches by 65 seconds and stops on 429. Cache now includes model and endpoint identity. 42 offline regression tests pass. See `decision_2026-10-06_gemini_switch.md` and `gemini_switch_verification.json`. No commit created.

## Latest implementation — Step 4 (2026-10-06)

This section supersedes older pending-OCR/501 status below. Original template and Step 3 export remain unchanged.

- Implemented `backend/document_text.py`, `extraction.py`, `validation.py`; updated `app.py`, Docker image and Compose. Real per-page native text/Tesseract OCR, OpenAI gpt-4.1-mini structured extraction, literal evidence checks, Decimal/date/currency validation, source idempotence and business-duplicate candidates are persisted. Processing attempts retain raw drafts and technical errors; current pipeline is step4-v5.
- Added `n8n_workflows/01_AP_intake_process_v2.json`. JSON/connections checked, imported and published in the local n8n instance as APIntakeProcessV2. Actual text/OCR, amount mismatch, same-ID retry and conflicting-file branches verified. Use http://127.0.0.1:5678/form/ap-intake-process-v2 . The export remains inactive for other-instance imports. No workflow credentials are required; OpenAI credentials live only in the backend environment.
- OpenAI key was tested successfully with real structured-output calls. User key text files and `.env` are ignored by Git. Gemini/Grok are not integrated. `.env.example` contains no key. Model calls use user-authorized test invoices.
- `test_data/first_round/expected_fields.json` records visually reviewed source mappings; `evaluate.py --process` exercises the real API and may incur model cost. Application processing never reads reference answers.
- 40 regression tests passed. Real final evaluation: 16/16 processed, 123/128 strict field matches (including nulls and duplicated fixtures), all expected issue codes present. Text cases match. Three OCR invoice numbers contain extra whitespace; OCR case 11 misses supplier name/net amount. These are documented limits, not silently repaired. This is a development set, not unseen-layout accuracy.
- C retains 129.00 and receives TOTAL_MISMATCH. Different-layout A remains a separate invoice with a business-duplicate candidate. New receipts preserve new sources; identical bytes reuse invoice_id. Missing supplier identity returns not_evaluable. All successful results still require manual review.
- Real post-restart verification: original SHA-256 matches, processed result retained, cached process call returns the same attempt. One application worker is required. Synchronous processing and conservative OCR routing are demo limitations.
- Evidence: `step_04_verification.json` (pre-key failure/OCR), `step_04_field_evaluation_v2.json` (early prompt baseline), `step_04_field_evaluation.json` (final), `step_04_n8n_verification.json` (actual form + restart), `decision_2026-10-06_step04_processing.md` (decisions/limits). Backend README and phase guide updated. No Git commit made in this step.
- Run: set ignored `.env` using `.env.example`; `docker compose up -d --build python-api`. Local instance is already running. For another n8n instance import v2, publish it and ensure HTTP nodes can resolve `http://python-api:8000` on the same Compose network.
- Next: Step 5 real review-task persistence and a minimal original/fields/issues/duplicates page, then Step 6 test notifications. No review link, approval, export, email trigger, due-date scheduler or external mail sending has been implemented in this step. review_status=not_created and review_url=null remain explicit.

## Latest implementation — Step 3 n8n upload (2026-10-06)

Step 3 is now verified through the running n8n instance. Current setup supersedes the earlier single-container checkpoint below.

- Added `backend/Dockerfile` and `.dockerignore`; Compose adds `python-api` with a healthcheck, loopback port 8000 and host persistence at `data/ap`. Existing n8n service/volume retained. Both containers are running; Python was restarted and stored records/originals remained readable.
- Created `n8n_workflows/01_AP_intake_upload_v1.json`, a derived upload slice from the original template. Original file matches Git HEAD unchanged; original instance workflow `aQNIbEjnPAcluLxf` was not replaced.
- Imported and published new instance workflow `APIntakeUploadV1` / `01_AP_Intake_Upload_v1`. Local form: http://127.0.0.1:5678/form/ap-intake-upload-v1 . Export file remains inactive for safe import elsewhere.
- Actual chain: Form Trigger → Normalize Upload → multipart HTTP intake → Format Intake Result → Respond to Webhook. Stable user-entered Upload ID provides replay control; single-file binary data is preserved.
- Verified: initial text PDF intake; text replay; OCR PDF intake and replay; new-source identical content; same-source different bytes rejected with 409. Downloaded originals match input bytes. Restart persistence passed. Details: `step_03_upload_verification.json`.
- Verification levels: JSON parse and connection targets checked; target-instance import and local publication done; actual n8n HTTP form executions passed. No external credentials required. Browser UI interaction was not separately automated.
- Scope remains intake only: processing returns 501, review_status=not_created, no OCR/validation/review/notification/email workflow execution. A successful OCR-file upload is not OCR accuracy validation.
- Instructions and failure semantics: `step_03_upload_runbook.md`. Next is Step 4: expected OCR fields/source mapping, OCR adapter and real `/process` implementation.
- No Git commit was created for this implementation; changes remain available for review.

## Local Git and Docker checkpoint (2026-10-06)

Initialized a local Git repository at the project root. No remote or GitHub repository created; no new README added. Initial commit message requested by the user:

> Complete the design of the n8n workflow, import templates, identify reusable modules, finalize the Python backend design, prepare test data, and implement the Python backend interfaces.

This message summarizes the checkpoint; "import templates" refers to the template file present in the project, not verified import into the running n8n instance.

Tracked scope includes backend, Compose, workflow template, design/handoff documents, synthetic fixture sources and first-round PDFs. Ignore rules exclude private materials, runtime databases, virtual environment, temporary/generated output directories, environment files and the full FATURA corpus. These local files were not deleted. Selected first-round samples remain tracked.

Docker inspection confirmed the existing `pexonconsulting-n8n-1` container was already running with `n8nio/n8n:2.42.3`. Ran `docker compose up -d n8n` without replacing the service or deleting volumes. Readiness endpoint `http://127.0.0.1:5678/healthz/readiness` returned HTTP 200 and status ok. Persistent volume `pexonconsulting_n8n_data` is mounted at `/home/node/.n8n`. This supersedes the earlier unverified Docker-state note below.

Current strategy: one n8n container, loopback port 5678, Europe/Berlin timezone, named persistent volume. Python remains a separate local service at this checkpoint; add it to the same Compose network later. No npm installation removed and no workflow activation or credential migration performed.

Run from project root: `docker compose up -d` to start, `docker compose stop` to stop, `docker compose restart n8n` to restart. Do not use `docker compose down -v` for routine stopping because it deletes the volume. Closing the browser does not stop n8n.

## Latest implementation — minimal AP intake backend (2026-10-06)

This section supersedes the earlier fixture-only next step. Historical fixture notes below remain unchanged.

### Implemented

- `backend/app.py`: FastAPI app factory, SQLite storage, persistent originals, PDF/JPEG/PNG intake, source-key idempotency, identical-content reuse, metadata/original retrieval and health capabilities.
- Existing invoice processing endpoint explicitly returns HTTP 501. OCR, structured extraction, arithmetic validation, business-duplicate matching, review tasks/pages and notifications are not implemented. No mock extraction or review URL is returned.
- `backend/requirements.txt`, `requirements-dev.txt`, `README.md`, `test_intake.py` and project `.gitignore` added. Dependencies installed in project-local `.venv` (bundled Python 3.12); no global Python packages changed.
- Architecture summary, AP workflow and Chinese phase guide updated. Current decision/contract: `decision_2026-10-06_intake_ocr.md`.
- Original n8n template, Compose and source test materials unchanged. No n8n workflow generated/imported or email sent.

### First-round material check

All 16 PDFs opened successfully. Five text PDFs each contain one page and a text layer; eleven OCR PDFs each contain one page, one raster image and zero extracted text characters. Poppler renders of OCR cases 1 and 11 were visually sampled and readable. This is not OCR accuracy verification. Source mapping and human-reviewed expected fields for renamed OCR cases remain to be added before extraction acceptance.

### Verification actually completed

- `pytest backend/test_intake.py`: 22 tests passed after final code change (1.75 seconds). Each of the 16 selected PDFs is uploaded and downloaded byte-for-byte in isolated temporary storage.
- Additional cases: same-key replay, new-source identical bytes, changed bytes under an existing key (409), different-layout candidate not prematurely merged, PNG/JPEG content detection, invalid/empty/over-limit files, missing record, four concurrent retries and persistent reads after app recreation.
- One non-failing dependency warning: Starlette deprecates its httpx TestClient adapter. Test adapter migration can be handled with a dependency update; no application failure observed.
- Actual HTTP smoke: temporary Uvicorn server on 127.0.0.1:18080; health and OpenAPI 200, image-PDF intake 201, original byte match, processing 501. Server stopped after the check. Isolated smoke storage: `tmp/backend-http-smoke`.
- Sandbox initially blocked pip network and pytest temporary directories. Authorized elevated tool execution installed dependencies and ran local tests successfully. No unresolved approval block.
- `docker compose ps` could not access the Docker pipe in the sandbox; no deployment attempted, and current container state is not verified.

### Run and API

From project root: `.venv/Scripts/python.exe -m uvicorn backend.app:create_app --factory --host 127.0.0.1 --port 8000`.

Open `http://127.0.0.1:8000/docs`. Default storage is `data/ap`; override with AP_DATA_DIR. Persist both database and originals. There is no server left running from this task. Full English instructions are in `backend/README.md`.

POST `/api/ap/intakes` multipart fields: file, source_type (upload/email), source_namespace, source_id, attachment_id. The four source fields identify retries; new sources retain distinct receipts even when content shares invoice_id. Different bytes under the same source key return 409. Original filenames are metadata only, never disk paths.

### Limits and next step

- OCR-required inspection is an input hint, not OCR execution. Nonempty PDF text has not been quality-assessed. Text/image/hybrid quality routing and real OCR must be implemented before this phase can pass.
- First-round final acceptance must include real OCR and text extraction, independently scored from business validation. Preserve printed wrong amounts; do not normalize away business errors.
- Current service is a loopback-only, unauthenticated demo; no production deployment. File/DB operations handle ordinary errors, but abrupt process crashes can leave orphan originals. No parser isolation or recovery reconciliation yet.
- Next: map the 11 OCR cases to sources/expected values, choose and connect an OCR adapter, implement `/process` against saved originals, then structured extraction/validation and business matching. Do not read annotation files in the processing path.
- After processing works, implement the review task/page and test notifications; wire n8n upload/email to these real interfaces. Downstream export and due checks remain reserved.

## Latest revision — visible demo labels removed

User request on 2026-10-06 supersedes the original visible-marking requirement. Removed the SYNTHETIC / DEMO ONLY banner, Demo company prefixes, DEMO invoice prefixes, fictional-address labels, demo payment terms and no-payment notices from all rendered invoices. Names remain invented; addresses now use invented street/city text. Invoice prefixes are now INV-A/B/C. Synthetic provenance remains in this log and manifest only. Earlier generation details below describe the initial version where they conflict with this revision.

Updated input.json, generate.py, verify.py, both adapted templates, four HTML files, all five PDFs, all five OCR-ready PNG renders in verification/, extracted text, manifest hashes/expected fields and visual_review.json. PDF text checks confirm no visible synthetic/demo/fictional/no-payment markers. All five regenerated pages were visually inspected without observed overlap or clipping. Text extraction and arithmetic checks pass; C still prints 129.00. The 01/03 SHA-256 values remain equal and 01/04 remain different. No workflow or business implementation changed or tested.

## Completed scope

Created five synthetic English, EUR, text-layer invoice PDFs in `test_data/ap_invoices/`, using fixed October 2026 dates and 19% test VAT. This implements the user's five-case fixture request, superseding the earlier plan's initial three normal samples for this task only. No business rules or workflow implementation changed.

Source: local `D:/Projects/synthetic-invoice-gen`, upstream https://github.com/alamgirqazi/synthetic-invoice-gen, commit `bd20ae9b0a3fa4a6080ef883c7c734ffc87c2b18`. Code license: MIT; retained at `test_data/ap_invoices/templates/LICENSE`.

## Generation and schema

Inspected the README, `generate_synthetic_data.py`, `render_receipts.py`, and both source templates. The rendering schema uses `supplier_name`, `customer_name`, `invoice_number`, `document_date`, `due_date`, `document_currency`, `line_items`, `taxes`, and `document_total_net/tax/amount`. Line items use numeric quantity/unit_price/amount/tax_amount and string tax_rate; tax summaries use base/rate/value/code.

Retained manually authored inputs in `input.json`; cases 01, 03 and 04 reference exactly the same business record. `generate.py` renders adapted upstream formal_corporate and modern_minimal Jinja2 templates. Adaptations add the prominent SYNTHETIC — DEMO ONLY banner, fixed fonts/colors, readable widths, and replace fixed 30-day/debit wording with the actual due date and a no-payment notice. No real people, accounts or credentials are included.

The upstream LLM/data-generation stage and arithmetic correction are bypassed. Its random context helper is also bypassed because it can inject bank/payment data. C's supplied total is rendered verbatim. WeasyPrint could not load Windows GObject/Pango, so `print_pdfs.cjs` uses headless Microsoft Edge to print the same rendered HTML to text PDFs. No rasterization or noise is applied to the final PDFs. Case 03 uses a byte copy, not a second rendering.

## Files and reproduction

- `test_data/ap_invoices/input.json`: fixed records and five-case mapping.
- `generate.py`, `print_pdfs.cjs`, `verify.py`: local generation and artifact checks.
- `templates/`: adapted upstream templates and MIT notice; four rendered HTML files are also retained.
- Five PDFs and English `manifest.json`: expected fields, arithmetic outcomes, duplicate relationships and actual SHA-256 hashes.
- `verification/`: extracted text and Poppler page renders for all five PDFs; `visual_review.json` records completed visual inspection.

Use the bundled Python at `C:/Users/13020/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe` to run `test_data/ap_invoices/generate.py`, then the bundled Node to run `test_data/ap_invoices/print_pdfs.cjs`, then bundled Python for `test_data/ap_invoices/verify.py`. Run from the project root. Jinja2 was installed into project-local `tmp/invoice_gen_deps`; the script loads it there. Printing requires the bundled Playwright and installed Edge; verification requires pdfplumber and pdftoppm. Re-generation requires renewed visual inspection. PDF metadata may change hashes between runs, but 01/03 must remain identical within a run.

## Actual verification

- Five PDFs opened successfully; each has one page, extractable text, no embedded raster image, and text coordinates inside page bounds.
- Required names, addresses, invoice numbers, dates, EUR, item descriptions/prices/amounts, 19% rate and totals checked against the fixed inputs. The alternate layout splits address lines; extraction checks account for that presentation.
- Decimal arithmetic verified item quantity x price, line tax, net and tax sums. A: 100.00 + 19.00 = 119.00. B: 250.00 + 47.50 = 297.50. C: 100.00 + 19.00 = 119.00 while printed total remains 129.00; expected TOTAL_MISMATCH difference +10.00.
- 01 and 03 SHA-256 equal; 01 and 04 SHA-256 different. Exact values are in manifest.json.
- All five pages rendered with Poppler and visually inspected: readable banner, fields and tables; no observed clipping, overlap, missing glyphs or extra pages. Case 04 visibly uses a different layout.
- No n8n workflow, compose file, business implementation or source generator file modified. No application intake, duplicate detection service, approval, export, payment or workflow execution was tested. Fixture checks are not workflow acceptance.

## Next step and delivery semantics

Use these fixtures in the future AP intake/extraction checks. For repeated delivery, reuse the original source identifier AND attachment identifier. An identical PDF with a new source identifier is a new receipt, not proof of repeated delivery. The manifest supplies matching sample upload IDs for 01/03 and a distinct upload ID for 04. Supplier+invoice number is the intended business-duplicate relationship, subject to the eventual backend policy. The normal fixtures still require manual approval under the current project design.
