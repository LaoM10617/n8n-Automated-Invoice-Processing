# Native Agent demo operations

Current canvas: [Process AP Invoices — Native Agent, Review & Excel](http://localhost:5678/workflow/J4xPbnTCAgYFVNzJ).

1. Open [Upload Invoice](http://127.0.0.1:5678/form/ap-native-intake-b2-v2). Upload one PDF or supported image. Use a clearly marked demo document.
2. The backend archives and reads the document. A real n8n Agent uses Gemini and tools restricted to that document. The gateway enforces at most three provider requests, six read tools and at least 60 seconds between provider requests. A fresh analysis commonly takes more than a minute.
3. `Reuse Verified Analysis` means a saved native result was reused. It does not imply that the model ran again. Re-uploading the B3 fixtures demonstrates this path.
4. Deterministic validation decides automatic approval or human review. Open the invoice-specific review link in [local Mailpit](http://127.0.0.1:8025/). Compare the original, save edits and approve or reject. Approval is not payment.
5. Open the [Export Portal](http://127.0.0.1:8000/exports). Select approved rows and create/download a combined Excel file. Pending and rejected invoices are excluded. A review decision does not create an Excel file automatically.
6. Review decisions and completed files enter the two lower canvas branches as separate executions. Their notifications remain local to Mailpit.

For the manual email demo, inspect the Gmail query and select a new demo batch before running `Run Demo Email Batch`. Run the batch through exactly one workflow. The B3 multi-attachment regression used synthetic email-shaped input; it did not re-fetch Gmail.

## Validation boundary

Three real native analyses and three old Python comparisons matched all 39 fields. The third native draft needed explicit backend recovery after an n8n expression failure. The final save expression was checked with three actual closed drafts, and the full published upload route with cached native analyses. No extra fresh paid analysis was run after that final expression repair. The historical OCR11 address evidence limitation remains unresolved.

The 2026-10-07 evaluation budget is exhausted: 18 real Gemini requests. Further evaluation with new documents requires a new explicit budget; ordinary cached replays do not call the model.

## Explicit rollback

Stage A remains available at [Python Agent canvas](http://localhost:5678/workflow/7xXB2pjXOE1EQ2bY) and [Stage A upload](http://127.0.0.1:5678/form/ap-unified-intake-a2-v1).

To select Stage A, stop starting new demo runs and wait for any active analysis to finish. Change both values in `compose.yaml`:

```yaml
AP_REVIEW_EVENT_URL: http://n8n:5678/webhook/ap-unified-review-a2-v1
AP_BATCH_EVENT_URL: http://n8n:5678/webhook/ap-unified-excel-a2-v1
```

Run `docker compose up -d python-api`, then use the Stage A upload/canvas. Switch both URLs back to `ap-native-review-b2-v2` and `ap-native-excel-b2-v2` to select the native canvas again. Never configure two receivers for one event. This is an operator-selected version change, never a silent model-error fallback. Existing native and Python histories remain distinct.

Do not import the historical B2 JSON over the live B4 version. The current instance export is `n8n_workflows/AP_unified_canvas_native_agent_v2_B4.json`. Credentials remain in n8n; do not paste keys into workflow parameters, screenshots or logs.

## Two honest interview demo paths

**Automatic approval:** open the saved text sample [review and audit record](http://127.0.0.1:8000/reviews/4ff2e34b-6dff-48d8-901c-e64a800fb9f4). Show the original, native extraction/evidence and automatic decision, then its approved row in the Export Portal. Narrate: “The Agent extracts document facts. Code checks evidence, amounts, duplicates and approval policy. Approval makes the snapshot selectable; it does not pay or export automatically.” Re-uploading `data/native-b3-samples/text.pdf` demonstrates a cache replay, not fresh reasoning.

**High-value manual review:** open the saved scan [review and audit record](http://127.0.0.1:8000/reviews/13e7a901-c037-41b0-a84b-b246176848ca). Show EUR 11,900, the original machine address and the human line-format revision, then the manual approval. Show the combined Excel and local download notice. Narrate: “The high-value invoice required a person. The saved human revision is the exported version; the machine draft remains visible.” This record is already approved: demonstrate its history, never pretend to approve it live again. A fresh interactive approval demonstration requires a new labeled document and a separately authorized model budget.

Both paths use independent asynchronous executions: upload does not wait for a person, and approval/file events appear separately on the same canvas. Use the saved audit record to join them; do not simulate a single continuous green execution. The [missing-date example](http://127.0.0.1:8000/reviews/0a40d391-8fd0-4193-9081-851d595e4a3a) remains rejected and is excluded from Excel.

## Where to inspect failures and recover

- Open the invoice review/audit page for the source, raw draft, human revisions, validation issues and model/tool trace. A cache replay is explicitly labeled; an unknown provider outcome is not permission to rerun it.
- Inspect the saved notification status on the review/export interface and local Mailpit. n8n execution retention is disabled; the durable business ledger is authoritative.
- For an undelivered review event, fix the receiver/configuration first, then reuse its existing ID: `docker compose exec -T python-api python -m backend.review_events EVENT_ID`. This is bounded delivery, not re-approval. A processed event is a no-op; never invent a replacement ID.
- For missing/corrupt Excel, inspect `GET /api/ap/export-batches/EXPORT_ID`, then explicitly use the existing batch recovery action or `POST /api/ap/export-batches/EXPORT_ID/retry` with the local `X-AP-Review: 1` header. Check the same ID, frozen members and expected hash. Do not create a different selection to hide a failed export.
- For uncertain notification delivery, check/reconcile the saved notice before retrying. Use the existing notification controls; do not regenerate the Excel or repeat approval to resend a notice.
- For a technical Agent failure, keep its failed attempt and trace. Resolve the cause and decide explicitly whether a new analysis is appropriate. There is no automatic Python fallback.

## Roll back the unified canvas itself

For the original split 01/02 version, select `/form/ap-approval-intake-v9` and set both compose targets to `http://n8n:5678/webhook/ap-review-export-v1` and `http://n8n:5678/webhook/ap-batch-export-v1`. Recreate python-api as above. Keep originals, approvals, native analysis tables, traces and Excel files. Never run the same email batch in multiple versions.

The three receiver configurations were rehearsed on 2026-10-07 using existing event/export IDs; all business rows and files stayed unchanged and the native configuration was restored. See `AP_final_delivery_rollback_verification.json`. The backup is a local application/data backup, not a complete n8n credential disaster-recovery bundle. Keep the n8n volume and credentials; never use `docker compose down -v` as a rollback step.

Out of scope: scheduled Phase03 checks/reports, external accounting software, real payments, real CFO email delivery, and continuous updates to one fixed Excel workbook.
