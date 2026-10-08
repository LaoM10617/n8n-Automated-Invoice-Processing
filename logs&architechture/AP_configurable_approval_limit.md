> Current update: edit **Approval Settings** in n8n to set the ceiling for new runs, then save/publish. Compose is only the legacy fallback. See [n8n settings delivery](AP_n8n_approval_settings_delivery.md).

# Configurable approval ceiling — 2026-10-07

The user requested an explicit amount setting suitable for the rehearsal data. The local deployment now sets `AP_AUTO_APPROVAL_LIMIT_EUR: "1500.00"` under `python-api.environment` in `compose.yaml`. This replaces the previously fixed 10,000 EUR ceiling for new decisions. The backend default without this setting remains 10,000.00 for compatibility.

## Operator procedure

1. Between runs, edit this value in `compose.yaml`, for example `AP_AUTO_APPROVAL_LIMIT_EUR: "1500.00"`.
2. From the project directory run `docker compose up -d python-api`. A plain restart does not reload changed Compose environment settings. No rebuild is needed for subsequent value-only changes.
3. The ceiling applies to subsequent policy evaluations: `0 < gross total < limit` is only eligible for automatic approval; total equal to or above the limit requires human review. Currency must still be EUR and every other validation, duplicate and evidence gate must pass.

This is operator configuration, not an editable n8n IF parameter or a reviewer-page control. No settings UI or new infrastructure was added. An invalid, nonfinite, nonpositive or sub-cent setting fails startup rather than silently falling back. Threshold and policy version are saved in each evaluation snapshot. Existing approved/rejected records are not reopened or relabelled; historical pending records are not automatically reevaluated at startup.

## Implementation and validation

- `backend/reviews.py` reads and validates the ceiling for each review-service instance, compares Decimal values and derives a version such as `eur-gross-under-1500-v1`.
- `backend/test_approval_limit.py` covers 1499.99 / 1500.00 / 1500.01 boundaries, invalid settings and preservation of a final approval after lowering the ceiling.
- Together with existing review-decision and export regressions: **61 passed**. The first sandboxed attempt failed on Windows temporary-directory permissions; the isolated rerun outside that restriction passed.
- Rebuilt/deployed only `python-api`. Runtime readback confirmed `1500.00`, `eur-gross-under-1500-v1`, and HTTP 200 health. No live approval or model call was made.

## Prepared batches

At this ceiling, batch1 and batch2 each retain two automatic candidates plus a FATURA exception. The generated images in batch3–batch5 all exceed the ceiling and therefore become amount-based manual cases; their FATURA images remain exception cases. The manifest and preparation guide record this change; image bytes and original filenames are unchanged.

German explanation: “Die Betragsgrenze ist explizit konfigurierbar. In dieser Demo liegt sie bei 1.500 Euro brutto. Ab diesem Betrag ist eine manuelle Freigabe erforderlich. Unterhalb der Grenze erfolgt die automatische Freigabe nur, wenn auch alle anderen Prüfungen bestanden sind.”
