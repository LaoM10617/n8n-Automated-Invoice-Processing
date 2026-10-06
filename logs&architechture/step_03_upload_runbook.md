# Step 3 — n8n upload intake

Verified on 2026-10-06 with n8n 2.42.3.

## Files and provenance

- Original template: `n8n_workflows/Email invoice archiving & data extraction.json`, preserved unchanged.
- Derived workflow: `n8n_workflows/01_AP_intake_upload_v1.json`.
- Instance workflow name: `01_AP_Intake_Upload_v1`; ID: `APIntakeUploadV1`.
- The derived slice adapts the original Code and HTTP Request node patterns. Gmail is replaced with Form Trigger for this step; Drive, SFTP, Sheets, AI and deletion branches are not included. These are intentional substitutions, not claims of template features already working.

## Start and use

From the project root:

```powershell
docker compose up -d --build python-api
docker compose up -d n8n
docker compose ps
```

Wait for `python-api` to be healthy before uploading.

- Upload form: http://127.0.0.1:5678/form/ap-intake-upload-v1
- Workflow editor: http://127.0.0.1:5678/workflow/APIntakeUploadV1
- Backend API documentation: http://127.0.0.1:8000/docs

Enter a unique **Upload ID** and choose one PDF, JPEG or PNG. Start with `test_data/first_round/text_pdf/01_invoice_A.pdf`, then an image PDF from `test_data/first_round/ocr/`.

The form waits for the backend response and displays invoice ID, receipt ID, duplicate flags and the input inspection hint. Success means the original is stored. It does not mean OCR, validation or review has run.

Use the same Upload ID and same file to test a retry: the receipt ID stays unchanged. Use a new Upload ID with the same file to create a new receipt linked to the existing content. Reuse an existing Upload ID with a different file to test HTTP 409; the form reports that the upload was not accepted.

Upload IDs are required and limited to 200 characters by the workflow. The source namespace is fixed to `n8n-ap-upload-v1`; one-file submissions use attachment ID `0`. Do not regenerate the Upload ID during a retry.

## Nodes

1. **Upload Invoice**: Form Trigger with one required file and a required Upload ID. Supported Form Trigger 2.1 response-node mode is used to show the real result after the HTTP call.
2. **Normalize Upload**: retains the binary as `data`; sets AP direction and stable source fields. No invoice extraction or filename-dependent business logic.
3. **Store Original and Register Intake**: multipart POST to `http://python-api:8000/api/ap/intakes`. The file parameter uses the n8n binary field directly, not base64 JSON.
4. **Format Intake Result**: handles HTTP 200/201 and rejected HTTP responses; no failed response is reported as stored. Network/timeout errors stop execution and remain visible in n8n.
5. **Show Intake Result**: returns the form's completion text through Respond to Webhook.

A handled rejection can have a successful n8n execution status: inspect `intake_success` and `backend_status` in Format Intake Result to distinguish business acceptance from orchestration completion.

## Runtime and persistence

Compose now contains `n8n` and `python-api`. Containers communicate via the Compose service name. Browser links use loopback, not `python-api` and not the n8n container's localhost.

Python storage is the ignored host directory `data/ap`, mounted to `/data/ap`; it contains originals and SQLite. n8n retains its existing named volume. Neither service is exposed beyond loopback on the host. No credentials or outbound email are required for this upload slice.

The backend source is copied into its image: run `docker compose up -d --build python-api` after backend changes. Do not simultaneously run the host Uvicorn service on port 8000.

## Import state

The saved JSON is intentionally inactive for safe import into another instance. The current local instance copy was imported and published for the verified local form URL. The original template's workflow was not replaced or activated.

If importing into a different instance, import the derived JSON, confirm the API service URL, and publish it before using the production form URL. Importing the same ID again updates this derived workflow; export any subsequent manual edits before replacing it. Workflow JSON exports must remain under `n8n_workflows/`.

CLI publication while n8n is running requires a restart to load that state; this was done for the current import. Standard UI publishing does not need that CLI workaround.

## Verification and remaining scope

See `step_03_upload_verification.json`: text intake/replay, OCR intake/replay, new-source identical content, conflicting source key, original byte retrieval and backend restart persistence passed. The successful initial text upload preceded the recorded replay case. Both containers remain running.

JSON parsing, connection checks, target-instance import, local publication and actual Form Trigger HTTP execution have been verified. There are no credential bindings needed for this slice. HTTP multipart requests exercised the actual generated form endpoint; browser interaction was not separately automated.

OCR PDF acceptance only verifies transfer and storage. `/process` is still HTTP 501; structured extraction, business duplicate detection, review tasks, review links, notifications and Gmail integration are future steps.
