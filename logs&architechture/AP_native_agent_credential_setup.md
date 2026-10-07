# Bind the native Agent candidate credentials

Candidate: [AP Invoices — Native Agent Candidate B2](http://localhost:5678/workflow/J4xPbnTCAgYFVNzJ). Keep it unpublished. Stage A remains the live demo.

Latest check (2026-10-07): both existing credentials were updated from the user-provided local_key.txt with explicit authorization. All four candidate nodes retain the correct references. The live n8n metadata-only probe passed both authentication checks (HTTP 200). No further credential setup is needed. The instructions below are for future rotation. In Header Auth, the internal **Name** field must be `X-AP-Native`.

The backend gateway is deployed. These two credentials use a **local gateway key**, not your Google API key. Google authentication remains in Python. The gateway key cannot authenticate approval/export endpoints.

## 1. Copy the local gateway key

Run this yourself in PowerShell at the project root. It copies the value to your clipboard without displaying it. Do not paste it into chat, workflow parameters or documents.

```powershell
docker compose exec -T python-api python -c "from backend.native_analysis import proxy_key; print(proxy_key())" | Set-Clipboard
```

## 2. Create the Gemini credential in n8n

Open `Gemini via Bounded Gateway` → credential selector → create a **Google Gemini(PaLM) Api** credential:

| Field | Value |
| --- | --- |
| Credential name | `AP Native Gemini Gateway` |
| Host | `http://python-api:8000/api/ap/native/gemini` |
| API Key | Paste the clipboard value |

Save it and bind it to `Gemini via Bounded Gateway`. The model stays `models/gemini-3.5-flash-lite`. The credential test only reads the local model list and does not call Google. Do not use the default Google Host for this candidate: it would bypass the gateway controls.

## 3. Create the read-only tool credential

Create a **Header Auth** credential:

| Field | Value |
| --- | --- |
| Credential name | `AP Native Read Tools` |
| Name | `X-AP-Native` |
| Value | Paste the same clipboard value |

Bind this one credential to `Read Invoice Page`, `Find Field Evidence` and `Check Document Quality`. Keep their URLs and scope expressions unchanged.

The existing event credential is already bound to Begin/Commit/Abort and the existing business event nodes. Do not bind that event credential to Agent tools.

After saving, reply that the two credentials have been created. Codex can discover their IDs and check all four bindings. Do not publish or run historical email batches yet; the real model evaluation is the next B3 step.

## Key lifecycle

The local key is derived with HMAC from the existing event secret using a separate domain. Rotating `AP_REVIEW_EVENT_TOKEN` invalidates these two local credentials too; repeat the clipboard step and update both credentials. The provider key is never copied into n8n by this procedure.

The user initially created both credentials in the UI, then explicitly authorized updating their values from local_key.txt. The update used the official n8n CLI with the existing IDs; no additional credentials were created. Temporary import data was removed and local_key.txt is Git-ignored. No key is included in this document or workflow exports.
