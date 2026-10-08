# Editable n8n approval settings — 2026-10-07

## Current operation

Open workflow `J4xPbnTCAgYFVNzJ`, double-click **Approval Settings**, and edit `auto_approval_limit_eur` (current value `1500.00`). Enter a positive amount using a decimal point and no currency symbol or grouping separators. Keep the field as a fixed value. Save and publish before the next production upload; manual editor runs use the draft. No container restart is needed for n8n setting changes.

Both Fetch Invoice Emails and Upload Invoice feed this shared node. It preserves the input fields and binary attachments, and runs before the invoice loop. All files in that execution receive the setting from its workflow snapshot. The backend saves it in each intake run before analysis, then uses that saved value during approval evaluation, including after restart.

The comparison remains `0 < EUR gross total < ceiling`; equality requires human review. Evidence, dates, arithmetic, duplicate and other approval gates still apply. Existing approved/rejected records remain final. Replayed existing records retain their original decision policy; the current intake setting does not rewrite historical approvals. Historical pending records are not silently reevaluated.

The Compose variable is now a fallback for legacy callers without a workflow setting. The visible n8n value takes precedence for this workflow.

## Changes and safeguards

- One Edit Fields node, **Approval Settings**, plus the existing attachment preparation mapping. Added the existing service credential to Save Invoice & Read Text.
- `backend/intake_stages.py`: validates, authorizes and persists `source.auto_approval_limit_eur`; forwards the saved ceiling at validation. An explicit override requires the existing event-token credential. End users cannot select an approval ceiling in the upload form or attachment.
- `backend/reviews.py`: accepts an invocation-specific ceiling without changing shared service state; saves its derived version and amount in the existing decision-policy snapshot.
- No new tables, services, settings UI or model calls. The user's removed old review-event branch and current layout edits were preserved. The existing Excel-event branch remains.
- Saved original draft: `n8n_workflows/AP_native_before_approval_settings_20261007.json`; exact published result: `n8n_workflows/AP_native_approval_settings_published_20261007.json`.
- Published version: `5242a2e1-f0f9-4f45-ba5c-ab5aea42bc31`; active version and draft matched on readback.

## Verification

- **73 isolated tests passed**, including override authentication, invalid values, passing/blocking ceilings on the same source amount, persistence across application restart/configuration changes, existing amount boundaries and final-decision/export regressions. An initial test failure used the TestClient default host rejected by the existing origin guard; the test was corrected to localhost, with no guard change.
- SDK validation passed for 38 nodes. Existing empty sample-output schemas produce expression-path warnings. Connections and actual outputs were checked; the existing large-canvas warning is accepted to keep business decisions visible, rather than introduce more grouping in this targeted change.
- n8n test executions **520** (one email, three attachments) and **521** (upload) passed. Actual Settings and preparation nodes preserved binary data and propagated `1500.00` to every attachment. Gmail, HTTP, model and notification outputs were pinned; no real mail fetch or inference occurred in these tests. Evidence: `AP_approval_settings_verification.json`.
- Published upload tested with an existing approved native-analysis cache: run `19eefa52-b49d-47ae-bacb-937b3d688b99`. Backend received `1500.00`; no new processing attempt, native analysis, approval event or Excel batch. Evidence: `AP_approval_settings_live_verification.json`. This tests real transport and credential binding, not fresh extraction or a new approval.

## German explanation

“Die Freigabegrenze kann direkt im Workflow angepasst werden. Für jeden Verarbeitungslauf speichern wir den verwendeten Wert. So bleiben die Entscheidungen nachvollziehbar, auch wenn wir die Grenze später ändern.”

At 1,500 EUR, batch1 and batch2 still have two low-value automatic candidates; generated invoices in batch3–batch5 require amount-based human review. FATURA exceptions remain manual. Changing the ceiling does not fix inconsistent invoice amounts.
