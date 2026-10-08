# Native analysis manual re-execution recovery — 2026-10-08

## Decision

Supersedes the previous rule that a processing attempt always blocks Prepare Invoice Analysis. The user requested support for n8n manual step re-execution after stopping an execution. No workflow nodes, model, approval rules or infrastructure were added.

An authenticated call to Prepare now recovers a complete persisted provider draft after schema, finish reason, tool completion and page coverage checks. The existing deterministic invoice validation still runs afterwards. Expired scope time does not invalidate an already received complete draft. Provider outcomes marked unknown are not recovered as successful drafts.

If an old native attempt is partial, explicit Prepare re-execution supersedes it, preserves its attempt trace, and issues a new scope. Old scopes cannot write the new draft. The single-worker service lock serializes this operation with provider calls. Re-running the same intake run replaces its scope mapping; the old processing-attempt row remains for audit. Lifecycle failures can re-enter Prepare; provider, schema and business failures are not silently treated as successful.

This is restart/recovery at the Prepare boundary, not arbitrary suspension of a provider request or restoration of an Agent conversation. A partial attempt may require new paid calls when the user executes the Agent again. Do not run competing manual executions for the same invoice. Retry from Prepare or the batch entry, not an Agent node carrying an obsolete scope. Provider errors still have no implicit retry or Python fallback.

## Changes and verification

- backend/native_analysis.py: recover persisted drafts, supersede partial attempts, recover lifecycle failure states.
- backend/test_native_analysis.py: regressions for same/new intake runs, expiry, stale scope rejection, and service restart.
- 30 offline tests passed across native analysis, intake stages and workflow approval settings. No live Gemini calls were made.
- Rebuilt and started only python-api using docker compose. n8n was not upgraded or modified.
- Checked no running/waiting n8n execution before deployment.
- SQLite backup: data/baselines/native-resume-20261008/before.sqlite3.
- Live attempts 104 and 105 closed as PROCESS_INTERRUPTED; neither had model calls. Attempt 106 recovered through the deployed /begin endpoint as analyzed/cache_hit from its saved complete response (two historical calls).
- Invoice, attempt, review task, review event and export batch counts unchanged. See AP_native_resume_verification.json.
- Full new paid n8n end-to-end execution was not performed. Existing canvas results may be stale: refresh/reset the displayed execution and start the intended batch again. Fully recovered analysis routes through Reuse Verified Analysis; the two incomplete invoices can now start fresh attempts.

## Rollback

Restore the previous native_analysis.py and rebuild python-api if necessary. The database backup is for deliberate recovery only; do not overwrite subsequent user work with it. No data was deleted.
