"""Review surface. Invoice-provided text is escaped; writes use the versioned API."""

from html import escape
import json


def render_review(invoice, task):
    def safe(value):
        return escape(str(value), quote=True) if value is not None else '<span class="missing">Not extracted</span>'

    result = invoice.get('review_machine_result', invoice.get('processing_result')) or {}
    fields = result.get('fields') or {}
    original = escape(invoice['original_ref'], quote=True)
    preview = (''.join(f'<p class="meta">Page {page}</p><img loading="lazy" alt="Original invoice page {page}" src="{original.rsplit("/", 1)[0]}/preview/{page}">' for page in range(1, invoice['inspection']['page_count'] + 1))
               if invoice['media_type'] == 'application/pdf' else f'<img alt="Original invoice" src="{original}">')
    labels = [('supplier_name', 'Supplier'), ('supplier_address', 'Supplier address'),
              ('supplier_tax_id', 'Supplier tax ID'), ('invoice_number', 'Invoice number'),
              ('invoice_date', 'Invoice date'), ('due_date', 'Due date'), ('currency', 'Currency'),
              ('net_amount', 'Net amount'), ('tax_amount', 'Tax amount'), ('total_amount', 'Total amount'),
              ('discount_amount', 'Discount'), ('shipping_amount', 'Shipping')]
    rows = ''.join(f'<tr><th scope="row"><label for="field-{key}">{label}</label></th><td data-machine="{key}">{safe(fields.get(key))}</td><td><input disabled id="field-{key}" data-field="{key}" aria-label="{label}" /></td></tr>' for key, label in labels)
    issues = result.get('validation_issues') or []
    issue_html = ''.join(f'<li><strong>{safe(i["code"])}</strong><p>{safe(i["message"])}</p><small>Field: {safe(i["field"])}</small></li>' for i in issues)
    issue_html = f'<ul class="issues">{issue_html}</ul>' if issues else '<p>No rule exceptions recorded. Compare every field with the original.</p>'
    candidates = ''.join(f'<li><a href="/api/ap/invoices/{escape(c["invoice_id"], quote=True)}/original" target="_blank" rel="noopener">Open candidate original</a><p>{safe(c["invoice_id"])}</p><small>Basis: {safe(c["basis"])}<br>Currency match: {safe(c["currency_matches"])} · Total match: {safe(c["total_matches"])}</small></li>' for c in invoice['duplicate_candidates'])
    candidates = f'<ul class="issues">{candidates}</ul>' if candidates else f'<p>Result: {safe(invoice["business_duplicate_status"])}</p>'
    sources = ''.join(f'<tr><td>{safe(r["source_type"])}</td><td>{safe(r["original_filename"])}</td><td>{safe(r["source_id"])}</td></tr>' for r in invoice['receipts'])
    evidence = (result.get('raw_extraction') or {}).get('evidence', [])
    evidence_html = ''.join(f'<li><strong>{safe(e["field"])}</strong> · Page {safe(e["page"])}<blockquote>{safe(e["quote"])}</blockquote></li>' for e in evidence)
    trace = result.get('agent_trace')
    trace_html = safe(json.dumps(trace, indent=2)) if trace else 'Legacy extraction: no agent execution trace.'
    notice = ''
    if invoice['processing_status'] != 'processed':
        notice = '<div class="alert">Current processing is incomplete. This task remains pending; no approval has occurred.</div>'
    elif (task.get('extraction_attempt_id') or task['created_attempt_id']) != invoice['processing_attempt_id']:
        notice = '<div class="alert">Processing changed after this task was created. Compare the bound review with the latest analysis before deciding.</div>'
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Invoice review · {safe(fields.get('invoice_number') or invoice['invoice_id'])}</title><script src="/static/review.js" defer></script>
<style>
:root{{color-scheme:light;--ink:#183044;--muted:#586979;--line:#d4dee5;--paper:#fff;--bg:#edf2f5;--accent:#126b70}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--ink);font:16px/1.5 "Segoe UI",Arial,sans-serif}}
header{{background:#183044;color:white;padding:22px 32px;display:flex;justify-content:space-between;align-items:center;gap:20px}}
h1{{font-size:26px;font-weight:600;margin:0}}header p{{margin:4px 0 0;color:#d5e2e8}}.status{{background:#f3d99b;color:#463912;padding:6px 14px;border-radius:5px;white-space:nowrap}}
main{{max-width:1600px;margin:auto;padding:24px 32px}}.intro{{display:flex;justify-content:space-between;gap:20px;align-items:center;margin-bottom:20px}}.intro p{{margin:0;max-width:78ch}}
.workspace{{display:grid;grid-template-columns:minmax(0,1.15fr) minmax(360px,1fr);gap:24px;align-items:start}}
.document{{position:sticky;top:16px;background:#dce5eb;border:1px solid var(--line)}}.bar{{padding:12px 18px;background:white;display:flex;justify-content:space-between;gap:16px}}
.document{{max-height:85vh;overflow:auto}}img{{display:block;width:100%;height:auto}}
section{{background:var(--paper);padding:22px 24px;margin-bottom:18px;border:1px solid var(--line);border-radius:6px}}h2{{font-size:19px;margin:0 0 14px}}a{{color:var(--accent);text-underline-offset:3px}}a:focus-visible,summary:focus-visible{{outline:3px solid #c68613;outline-offset:4px}}
table{{border-collapse:collapse;width:100%;table-layout:fixed}}th,td{{text-align:left;vertical-align:top;padding:10px 0;border-bottom:1px solid #e7edf1;overflow-wrap:anywhere;white-space:pre-wrap}}th{{width:39%;font-weight:500;color:var(--muted);padding-right:14px}}td{{font-variant-numeric:tabular-nums}}
.missing{{color:#8a5a12;font-style:italic}}.issues{{list-style:none;margin:0;padding:0}}.issues li{{padding:12px 0;border-bottom:1px solid var(--line);overflow-wrap:anywhere}}.issues p{{margin:5px 0}}small,.meta{{font-size:13px;color:var(--muted)}}.meta{{overflow-wrap:anywhere}}.alert{{padding:16px;background:#fff1cf;border-left:4px solid #b78019;margin-bottom:20px}}summary{{cursor:pointer;color:var(--accent)}}blockquote{{white-space:pre-wrap;overflow-wrap:anywhere;border-left:3px solid var(--line);padding-left:12px;margin:10px 0}}footer{{padding:8px 0 24px;color:var(--muted);font-size:13px}}
@media(max-width:900px){{header,main{{padding:18px}}.workspace{{grid-template-columns:1fr}}.document{{position:static}}iframe{{height:65vh;min-height:380px}}.intro{{display:block}}.intro a{{display:inline-block;margin-top:10px}}}}
input,select,textarea,button{{font:inherit;max-width:100%;padding:8px;border:1px solid #899eac;border-radius:4px}}input[data-field]{{width:100%}}textarea{{width:100%;min-height:65px}}button{{cursor:pointer;background:#126b70;color:white;margin:6px 8px 6px 0}}button:disabled{{opacity:.45;cursor:default}}.resolution{{border-top:1px solid var(--line);padding:12px 0}}#review-message{{white-space:pre-wrap}}th{{width:25%}}.workspace{{grid-template-columns:minmax(0,1fr) minmax(540px,1.15fr)}}@media(max-width:1000px){{.workspace{{grid-template-columns:1fr}}}}:focus-visible{{outline:3px solid #c68613;outline-offset:2px}}
</style></head><body>
<header><div><h1>Invoice review</h1><p>Accounts payable · {safe(fields.get('invoice_number') or 'Invoice details')}</p></div><span class="status" id="review-status">Loading review</span></header>
<main data-invoice="{escape(invoice['invoice_id'], quote=True)}"><div class="intro"><p>Compare the original, machine draft and saved review. Original machine evidence remains read-only. Reviewer identity is a local demonstration identity.</p><a href="">Refresh saved data</a></div>
{notice}<div id="review-message" role="status" aria-live="polite" class="alert">Loading saved review…</div>
<div class="workspace"><div class="document"><div class="bar"><strong>Original document</strong><a href="{original}" target="_blank" rel="noopener">Open original in new tab</a></div>{preview}</div>
<div><section><h2>Review fields</h2><p class="meta" id="version-detail"></p><table><thead><tr><th>Field</th><th>Machine value</th><th>Current review value</th></tr></thead><tbody>{rows}</tbody></table>
<p><label for="field-has_adjustments">Totals include adjustments</label> <select disabled id="field-has_adjustments" data-field="has_adjustments"><option value="">Unknown</option><option value="false">No</option><option value="true">Yes</option></select></p>
<details><summary>Original machine draft (read-only)</summary><pre id="machine-draft" style="white-space:pre-wrap;overflow-wrap:anywhere"></pre></details>
</section>
<section><h2>Current approval checks</h2><ul id="approval-issues"></ul><div id="resolutions"></div>
<label for="review-page">Original page checked</label> <input id="review-page" type="number" min="1" max="{invoice['inspection']['page_count']}" value="1">
<p><label for="review-reason">Change or decision reason</label><textarea id="review-reason" maxlength="2000"></textarea></p>
<button id="save-review" disabled>Save changes</button><button id="approve-review" disabled>Approve</button><button id="reject-review" disabled>Reject</button>
<button id="adopt-review" hidden>Accept latest analysis</button>
<p class="meta">Approval creates a saved decision; export delivery is not connected yet. No payment occurs.</p>
<details id="latest-analysis" hidden><summary>New analysis to compare</summary><pre style="white-space:pre-wrap;overflow-wrap:anywhere"></pre></details></section>
<section><details><summary>Saved revision history and manual sources</summary><pre id="review-history" style="white-space:pre-wrap;overflow-wrap:anywhere"></pre></details></section>
<section><h2>Machine exceptions (preserved) <small>({len(issues)})</small></h2>{issue_html}</section>
<section><h2>Possible duplicates <small>({len(invoice['duplicate_candidates'])})</small></h2>{candidates}</section>
<section><details><summary>Analysis agent execution</summary><p class="meta">Saved execution trace. Reopening or replaying cached analysis does not make new model calls. No model reasoning is stored.</p><pre style="white-space:pre-wrap;overflow-wrap:anywhere">{trace_html}</pre></details></section>
<section><details><summary>Extraction evidence</summary><ul class="issues">{evidence_html or '<li>No evidence available.</li>'}</ul></details></section>
<section><details><summary>Receipt history and record details</summary><table><thead><tr><th>Source</th><th>File</th><th>Source ID</th></tr></thead><tbody>{sources}</tbody></table>
<p class="meta">Invoice: {safe(invoice['invoice_id'])}<br>Review task: {safe(task['review_id'])}<br>Created: {safe(task['created_at'])}<br>Processing: {safe(invoice['processing_status'])}<br>Model: {safe(result.get('model'))}<br>Bound machine attempt: {safe(task.get('extraction_attempt_id') or task['created_attempt_id'])}</p></details></section></div></div>
<footer>Approval does not mean exported or paid. Automatic approval uses deterministic rules, never an AI decision.</footer></main></body></html>'''
