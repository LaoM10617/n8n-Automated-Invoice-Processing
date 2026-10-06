# Handoff — AP invoice test fixtures

Date: 2026-10-06

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
