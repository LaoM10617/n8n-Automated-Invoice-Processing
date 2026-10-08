# Invoice Automation Demo

**Email / single-file upload → OCR & Gemini extraction → deterministic validation → automatic approval or human review → selected Excel export.**

## Run locally

1. Copy `.env.example` to `.env` and configure the Gemini API key and local event token. Set `AP_LLM_MIN_INTERVAL_SECONDS=0` to disable artificial request spacing.
2. Start services with `docker compose up -d --build`.
3. Import [`n8n_workflows/AP_current_workflow.json`](n8n_workflows/AP_current_workflow.json), bind the Gmail, native Gemini gateway and header-auth credentials, then publish. See [backend setup](backend/README.md) for credential configuration.
4. Set the email filter and **Approval Settings**, then run the workflow. Complete manual reviews using the invoice links in the notifications.
5. Preview and select approved invoices in the Export Portal before downloading Excel.

| Service | Local address |
|---|---|
| n8n | http://localhost:5678 |
| Demo mailbox (Mailpit) | http://localhost:8025 |
| Export Portal | http://127.0.0.1:8000/exports |

## Scope

- Only approved invoices can be exported. Each export creates a new workbook.
- No DATEV/Lexoffice integration, actual payments or payment reminders.
- The committed workflow is the latest saved editor draft, exported inactive; it may differ from the previously published version.
- Credentials, runtime data and local historical workflow backups are excluded from Git. Older logs/scripts describe historical versions and may reference archived JSON files.

[Demo operations](logs&architechture/AP_native_agent_demo_operations.md) · [Handoff](logs&architechture/handoff.md)
