> Current policy update (2026-10-07): the deployed gross EUR limit is now 1,500.00. Batch1 and batch2 retain two automatic candidates; the generated invoices in batch3 through batch5 now require manual review because their totals exceed the limit. File names retain their original preparation labels.

# Five rehearsal batches — 2026-10-07

User-approved composition: two newly generated automatic-approval candidates and one unchanged FATURA exception-review image per batch. Images only; no PDFs or model calls.

## Files and expected routes

| Batch | Automatic candidate 1 (EUR) | Automatic candidate 2 (EUR) | Manual exception source |
|---|---:|---:|---|
| batch1 | 981.75 | 1130.50 | Template12_Instance0.jpg |
| batch2 | 1338.75 | 1487.50 | Template17_Instance101.jpg |
| batch3 | 1695.75 | 1844.50 | Template18_Instance105.jpg |
| batch4 | 2052.75 | 2201.50 | Template46_Instance0.jpg |
| batch5 | 2409.75 | 2558.50 | Template12_Instance102.jpg |

## Verification and limits

All ten generated source-field sets pass the existing backend deterministic validation. They use unique invoice numbers, explicit EUR amounts below 10,000, a 19% VAT amount, an explicit due date and no adjustments. This is not proof of successful OCR, Agent extraction, evidence checks or automatic approval. All five copied originals match source bytes; all fifteen image hashes are distinct. The generated layout and all five manual originals were visually inspected. No application data, workflow settings or approval rules were changed.

The FATURA cases have inconsistent printed totals; some also have discounts or conflicting line-item currency. Use them to demonstrate inspection and rejection/requesting a corrected invoice. Do not invent values to obtain approval. These cases do not demonstrate the high-value approval threshold.

Machine-readable source fields, original annotation values and SHA-256 hashes are in `test_data/demo_batch_manifest.json`. Only the three images in each batch directory should be attached; do not attach the manifest.

## Email selection

The existing Gmail query is fixed to `subject:AP-DEMO subject:phase01-connect-001`. Compatible subjects include `[AP-DEMO][phase01-connect-001][batch1] Demo invoices` through `[AP-DEMO][phase01-connect-001][batch5] Demo invoices`. The case tag does not isolate a fetch: all messages matching the fixed query can be returned, including previous rounds. For five isolated rehearsals, explicitly narrow the query to the intended case or use a new batch tag and matching query per round. No query was changed by this preparation.

## German demonstration wording

> Zwei Rechnungen sind als Kandidaten für die automatische Freigabe vorbereitet. Die dritte enthält widersprüchliche Beträge und soll zur manuellen Prüfung weitergeleitet werden. Die tatsächliche Entscheidung trifft das System erst nach der Extraktion und Validierung.

> Bei einer widersprüchlichen Rechnung korrigiere ich die Beträge nicht ohne Beleg. Ich lehne sie ab beziehungsweise fordere eine korrigierte Rechnung an.
