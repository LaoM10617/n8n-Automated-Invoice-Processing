# Unified Phase 01 canvas — 2026-10-06

## Delivery

`n8n_workflows/01_AP_unified_intake_v5.json` is a single workflow with 37 nodes including three English section notes. Both the form and controlled manual Gmail entry run the same inline storage, cache/pacing, extraction/validation/duplicate, review-task and local-notification chain. There are no Execute Workflow or child-workflow dependencies. Python and Mailpit remain required services. Original workflows, templates and backend are unchanged in this integration.

Instance ID: `APUnifiedIntakeV5`; name: `01_AP_Unified_Intake_v5`.
Editor: http://localhost:5678/workflow/APUnifiedIntakeV5
Production upload: http://127.0.0.1:5678/form/ap-unified-intake-v5

The local test-only email bridge remains a separate historical test utility, not an entry in this business canvas. Phase 02/03 are not included.

## Input and output behavior

Upload ID/source namespace semantics remain unchanged. Both entries feed a one-item loop. Capture nodes preserve current-item context using n8n paired-item lineage; no previous node's first run is used to summarize the current attachment. Unsupported and invalid attachments therefore retain null invoice/receipt IDs rather than inheriting an earlier successful attachment. Gmail outcomes return to the loop; upload outcomes return to the form response. Existing Gmail batch filters and readonly credentials are retained. SMTP continues to local Mailpit only.

To run Gmail in the editor, select **Run Controlled Batch** using the trigger selector beside **Execute workflow**, then execute. The current query is `subject:AP-DEMO subject:phase01-connect-001`. To upload, use the production form link; do not wait on the manual Gmail trigger. No mailbox polling or new external email sends were added.

## Verification by level

- JSON parses; all node names/IDs and connection targets validated, no accidental self-edge, no subworkflow call. English notes and three-row canvas visually checked.
- Imported into the actual local n8n instance and published. Gmail and Mailpit credential references are bound and the existing Gmail credential executed successfully. Export is inactive for another-instance import; rebind credentials there.
- Gmail execution 408 and replay 411: success, 5 messages / 8 outcomes each. Four review_ready, two intake_failed (422), two skipped (unsupported/no attachment). Receipt IDs, invoice IDs and outcomes match the pre-integration batch. No attachment result leaked across loop iterations.
- Production form executions 409 and 410: success, same Upload ID + same PDF returned the same receipt/invoice/task and existing sent notification. One new source receipt (159 versus 158), no new invoice/task/notification/model attempt. Existing totals: 4 review tasks, 5 notification attempts (4 sent and 1 historical failure), 84 processing attempts.
- Production form source conflict: same Upload ID + different PDF returned intake_failed / HTTP_409, null receipt/invoice, and no processing or task creation.
- No new model calls or external email sends. Fresh SMTP delivery/failure and uncached model pacing were not re-exercised in this integration; they retain the previous implementations. Historical step06–08 evidence covers those behaviors, not a new v5 SMTP delivery claim. Backend code was unchanged, so the prior 52-test result applies to that unchanged code; no redundant full backend suite was run.

During construction an accidental shared connection-object reference generated capture-node self-edges; fixed with deep copying before validation. CLI re-import updated the editable graph but production retained the earlier history snapshot. Diagnostic execution 407 was manually canceled. Saving and publishing the corrected version through the editor fixed the production snapshot; upload tests above then passed. The canceled diagnostic record is retained. Final export was read back from the actual instance; only active=false and removal of instance owner/history metadata differ. A final layout-only publication changed no node parameters or connections.

Evidence: `unified_v5_executions.json`, `unified_v5_upload_verification.json`, `unified_v5_verification.json`, `unified_v5_canvas.jpg`.

## Maintenance

`scripts/build_unified_workflow.py` reproduces the integration from preserved v4 and email v1 exports. It writes a new inactive JSON, not a live deployment. After regeneration/import, verify the actual published snapshot; do not assume a CLI import refreshes production history. Keep existing credentials private. Cache condition matches current Gemini configuration and must be reviewed when changing model. The 65-second wait and backend 60-second gate remain in place. Review stays read-only/pending; OCR11 Causeway omission remains. No Git commit was created.
