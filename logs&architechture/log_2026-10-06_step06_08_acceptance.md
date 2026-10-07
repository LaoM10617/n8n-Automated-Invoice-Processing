# Phase 01 steps 6–8 acceptance — 2026-10-06

## Result and boundary

Steps 6–8 are implemented and verified in the local instance. Real upload and real Outlook-to-Gmail attachments reach persisted originals, extraction/validation/duplicate checks, pending review tasks and local Mailpit notifications. Review remains read-only. No approval, rejection, export, payment or reminder implementation was added. Original templates and v1–v3 workflow exports are unchanged. Changes remain uncommitted.

## Implementation and decisions

- `backend/notifications.py`: persistent claim/result API independent of review task creation. Concurrent/replayed claims reuse the latest attempt. Confirmed failures can create a retry attempt; `sending`/`unknown` are not automatically retried because SMTP delivery may already have happened. An operator must reconcile those states against Mailpit before recording a result. No exactly-once SMTP guarantee is claimed.
- `backend/email_receipts.py`: per-source attachment outcomes and batch reconciliation. Provider message ID plus attachment ordinal identifies a source; equal bytes reuse an invoice across new messages, while different bytes retain separate invoices and business-duplicate candidates.
- n8n owns MIME attachments, serial child calls and SMTP; the same backend owns upload/email storage, processing, task and notification state. The original template's Gmail Get Many node was adapted, with a controlled manual batch query and readonly Gmail scope. This supersedes the earlier upload-only status.
- Mailpit v1.27.4 binds only loopback ports 8025/1025 and stores mail under `data/mailpit`. No external SMTP relay is configured. Test account mapping and credentials remain in private runtime configuration; workflow exports contain credential references, not secrets.
- `scripts/email_batch.py` generates MIME fixtures and SHA-256 manifests, sends only to local Mailpit, then fetches stored MIME and submits each attachment through the local n8n bridge. This is real local SMTP, not Gmail. External delivery in this acceptance used authorized Outlook browser sends; automated external sending is not implemented.

## Verification levels

| Workflow ID | JSON / node targets | Imported | Published | Credential binding | Real execution |
| --- | --- | --- | --- | --- | --- |
| APIntakeNotifyV4 | Pass | Yes | Yes | Local Mailpit SMTP | Upload, replay, notification outage/retry |
| APEmailAttachmentV1 | Pass | Yes | Yes | Local Mailpit SMTP | Gmail and local child runs |
| APGmailIntakeV1 | Pass | Yes | No: manual trigger only | Gmail readonly | Executions 381/385 (2 messages), 389/398 (5 messages) all success |
| APLocalEmailBridgeV1 | Pass | Yes | Yes | Uses child | Local SMTP batches and replay |

Exports remain inactive for safe import into another instance. Instance status is independently recorded in `phase01_instance_status.json`. OAuth callback uses localhost; sign in to n8n on that same hostname before connecting Gmail. The earlier 127.0.0.1 session did not authenticate the localhost callback and produced Unauthorized; reconnecting after localhost login resolved it without broadening scope.

## Counts and evidence

| Batch / transport | Messages | Valid receipts | Linked tasks | Failed items | Skipped items |
| --- | ---: | ---: | ---: | ---: | ---: |
| phase01-connect-001 / real Outlook → Gmail | 5 | 4 | 2 | 2 | 2 |
| phase01-local-connect-001 / Mailpit | 2 | 3 | 2 | 0 | 0 |
| phase01-local-scenarios-001 / Mailpit | 9 | 7 | 4 | 2 | 3 |
| phase01-local-throughput-001 / Mailpit | 100 | 100 | 1 | 0 | 0 |

Counts of linked tasks overlap between batches and must not be summed. Five external emails were explicitly authorized and sent: single valid, two valid attachments, no attachment, broken PDF, and valid+broken+text mixed attachments. Each invalid item is independently recorded; mixed mail's valid invoice still succeeds. Gmail permissions are readonly; no emails were deleted. Gmail five-message replay preserves the same 4 receipt IDs and 2 tasks. Same-file new messages retain different source records; local business-duplicate case uses different PDF bytes and remains a separate invoice.

Across all batches there are 4 pending review tasks and 4 successfully delivered review notifications, plus 1 retained failed notification attempt from the deliberate Mailpit outage. Replaying already-notified invoices produces no additional notifications. Mailpit contains 115 messages: 111 local input fixtures plus 4 review notices. Actual notice review link was clicked and displayed the matching invoice, fields, exceptions and original page image. See `step_06_notification_verification.json`.

- 52 backend tests passed (2 existing warnings). All workflow JSON and node connection targets parse/check successfully; `git diff --check` passes.
- Exactly two new Gemini processing attempts (83,84), recorded at 20:00:56.720Z and 20:02:06.537Z (69.817 seconds apart), completed for uncached representative documents. No OpenAI fallback. All Gmail and 100-message throughput processing reused caches. This is not a model throughput benchmark.
- 100 local SMTP inputs were received. Final cached attachment processing took 81.297 seconds with 0 new processing attempts. Initial overlapping send/process invocation caused manifest bookkeeping loss, not missing mail; all 100 unique provider IDs were reconciled and the full processing pass rerun. Send duration is unavailable (`null`); receiver arrival span was 21.642 seconds. The tool now refuses processing before the manifest confirms every SMTP send. Do not interpret arrival span as a measured end-to-end send duration.
- Backend and Mailpit were force-recreated with persistent volumes. All table counts, 115 stored messages and the two Gmail-linked original SHA-256 hashes remained identical; services are healthy. See `phase01_restart_verification.json`.
- Per-batch JSON reports, `phase01_gmail_executions.json` (sanitized IDs, no bodies), `phase01_instance_status.json` and `phase01_gmail_success.jpg` provide supporting evidence. Historical evidence is retained.

## Runbook

1. Start existing services: `docker compose up -d`. Upload notification entry: http://127.0.0.1:5678/form/ap-intake-notify-v4 . Mailpit: http://127.0.0.1:8025 . Backend: http://127.0.0.1:8000 . Old v3 entry remains historical and has no notification step.
2. Gmail: sign into http://localhost:5678, open APGmailIntakeV1, inspect the batch-scoped query, and manually Execute workflow. Current query only retrieves AP-DEMO / phase01-connect-001. Replays are safe for existing source IDs. There is intentionally no unattended inbox polling. For a new batch update the query and verify account/recipient/count authorization before external sending.
3. On another instance import the four new workflow JSON files, bind the dedicated Gmail readonly credential and Mailpit SMTP (`mailpit:1025`, no TLS/login), publish the attachment child, upload and bridge workflows. Then run Gmail manually. Never treat JSON import as a successful credential test.
4. Generate local fixtures with `.venv/Scripts/python.exe scripts/email_batch.py generate --batch NEW_ID --limit 9`; then `send-local --batch NEW_ID`, then `process-local --batch NEW_ID` sequentially. For cached throughput add `--profile throughput --limit 100` only on generate. Never run send/process simultaneously. New batch IDs preserve old fixtures. These commands may call the model for uncached files; serial 65-second waits and backend 60-second gate apply.
5. Inspect `/api/ap/email-batches/BATCH_ID` and `/api/ap/invoices/INVOICE_ID/notifications`. Notification scope includes previous batches for shared invoices; failure count is attachment outcome count, not failed email count.
6. `scripts/build_email_workflows.py` regenerates the child/parent from preserved templates and v4, preserving an existing Gmail credential reference. It does not import or publish. Model-cache condition reflects current Gemini configuration and must be updated when switching models; the backend cache/gate remains authoritative. Runtime changes require explicit import/revalidation.

## Known limitations

OCR11 supplier address still omits Causeway. No-rule-exception status is not proof of extraction accuracy. SMTP interruption can leave sending/unknown requiring manual reconciliation. Network failure before outcome persistence is visible as an n8n failed execution and must be replayed/reconciled, not counted as a persisted outcome. The batch API counts processed source outcomes, not unseen mailbox messages, so compare against the sender manifest/provider IDs. Local harness and external browser delivery are separate paths; large external-mail and model-throughput tests were not performed. Gmail OAuth remains a test application; reconnect through its existing credential if provider authorization expires. Backend and bridge are unauthenticated local demo interfaces bound to loopback host ports.
