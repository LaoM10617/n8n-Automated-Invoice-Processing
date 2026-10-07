"""Local export register surface; invoice values are rendered as text by the client."""

PAGE = '''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Export register · Accounts payable</title><script src="/static/outcome_notifications.js" defer></script><script src="/static/export_register.js" defer></script>
<style>
:root{color-scheme:light;--ink:#183044;--muted:#586979;--line:#d4dee5;--bg:#edf2f5;--accent:#126b70}
*{box-sizing:border-box}body{margin:0;color:var(--ink);background:var(--bg);font:16px/1.5 "Segoe UI",Arial,sans-serif}
header{background:var(--ink);color:#fff;padding:24px 32px}h1{font-size:28px;font-weight:600;margin:0}header p{margin:4px 0 0;color:#d5e2e8}
main{max-width:1500px;margin:auto;padding:24px 32px}h2{font-size:20px;margin:0 0 12px}p{max-width:80ch}a{color:var(--accent);text-underline-offset:3px}
.filters{display:flex;flex-wrap:wrap;gap:14px;align-items:end;background:#fff;padding:20px;border:1px solid var(--line)}label{display:block;font-size:14px}
input,select,button{font:inherit;padding:8px 10px;border:1px solid #899eac;border-radius:4px}label input,label select{display:block;margin-top:4px;max-width:220px}
button{background:var(--accent);color:#fff;cursor:pointer}button:disabled{opacity:.45;cursor:default}input[type=checkbox]{accent-color:var(--accent);width:18px;height:18px;cursor:pointer}
:focus-visible{outline:3px solid #c68613;outline-offset:3px}.toolbar{display:flex;align-items:center;justify-content:space-between;gap:16px;padding:18px 0}.toolbar p{margin:0}
.meta{font-size:13px;color:var(--muted)}.message{padding:12px 16px;border-left:4px solid var(--accent);background:#fff;white-space:pre-wrap}.message.error{border-color:#a64029}
.table-wrap{overflow:auto;background:#fff;border:1px solid var(--line)}table{border-collapse:collapse;width:100%;min-width:900px}th,td{padding:12px 14px;text-align:left;border-bottom:1px solid #e7edf1;vertical-align:top}
th{font-size:13px;background:#e3ebf0;color:var(--ink);font-weight:600;white-space:nowrap}.number{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}td{max-width:280px;overflow-wrap:anywhere}td small{display:block;color:var(--muted)}
tbody tr:has(input:checked){background:#eef8f7}#empty{padding:18px;margin:0}#export-history{list-style:none;padding:0;margin:0}#export-history li{border-top:1px solid var(--line);padding:14px 0;display:flex;flex-wrap:wrap;gap:16px;align-items:center;justify-content:space-between}
.history{margin-top:36px}.history p{margin:0 0 16px}#ready{padding:14px 0}footer{margin:28px 0;color:var(--muted);font-size:13px}
@media(max-width:650px){header,main{padding:18px}.filters{padding:14px}.filters label,.filters input,.filters select{width:100%;max-width:none}.toolbar{align-items:start;flex-direction:column}.history li{align-items:start}}
</style></head><body><header><h1>Export register</h1><p>Accounts payable · Approved invoices</p></header>
<main><p>Approved invoices appear here automatically. Preview and select records, then download one combined Excel file.</p>
<div class="filters" role="group" aria-label="Register filters">
<label>Invoice date from<input type="date" id="date-from"></label><label>Invoice date to<input type="date" id="date-to"></label>
<label>Supplier contains<input id="supplier" type="search" maxlength="200" placeholder="All suppliers"></label>
<label>Currency<input id="currency" maxlength="3" placeholder="All currencies" size="12"></label>
<label>Records<select id="mode"><option value="true">Not yet exported</option><option value="false">All approved</option></select></label>
<button id="apply">Apply filters</button></div>
<div id="message" class="message" role="status" aria-live="polite">Loading approved invoices…</div>
<div class="toolbar"><div><p id="count">Loading…</p><p class="meta" id="totals"></p></div><button id="download" disabled>Download Excel</button></div>
<div class="table-wrap"><table><thead><tr><th><input id="select-all" type="checkbox" aria-label="Select all shown invoices"></th><th>Invoice</th><th>Supplier</th><th>Invoice date</th><th>Currency</th><th class="number">Total amount</th><th>Approval</th><th>Export status</th></tr></thead><tbody id="rows"></tbody></table>
<p id="empty" hidden>No approved invoices match these filters. Try All approved, clear the filters, or approve an invoice first.</p></div>
<p class="meta">Totals are shown separately by currency. “Exported” means a file was generated, including earlier single-invoice files; it does not confirm the file was downloaded or submitted.</p>
<div id="ready" hidden><a id="file-link">Download saved Excel</a><p class="meta" id="file-detail"></p><div id="outcome-notification"></div></div>
<section class="history"><h2>Export history</h2><p class="meta">Latest 30 combined files. Downloads reuse saved files. Recovery keeps the original selection and export ID.</p><ul id="export-history"></ul></section>
<footer>Invoice export — not submitted to an accounting system. Approval and export do not mean payment. Local demonstration only.</footer>
</main></body></html>'''
