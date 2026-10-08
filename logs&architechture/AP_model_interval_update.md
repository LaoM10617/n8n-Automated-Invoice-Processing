# Configurable model request interval — 2026-10-08

Removed the hard 60.1-second floor from persistent ModelGate and Stage A in-process gate. Native gateway, extraction and Compose defaults are zero; local .env is explicitly zero. Positive configured intervals remain supported. Provider errors and per-analysis request/tool budgets are unchanged; no automatic provider retry was added.

55 offline tests passed (native analysis, agent controls, processing), including zero-delay native rounds, Stage A intervals 0/2/60, positive cooldown enforcement and provider fault cases. Rebuilt only python-api after checking no active/waiting n8n execution. Live environment value 0 and health HTTP 200 confirmed. No paid model calls or end-to-end timing measurements. Review UI and n8n canvas unchanged.

Review access uses /reviews/{invoice_id}; no generic review-list page exists. Batch 1 links are historical after decisions and must be replaced for later batches.

Rollback: set AP_LLM_MIN_INTERVAL_SECONDS=60 in .env and recreate python-api. To restore the former exact interval use 60.1.
