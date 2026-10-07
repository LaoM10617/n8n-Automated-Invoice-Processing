/* Database-backed preview. A download freezes exactly the selected approval events. */
'use strict';
const byId = id => document.getElementById(id);
const filterIds = ['date-from', 'date-to', 'supplier', 'currency', 'mode'];
let rows = [], selected = new Set(), busy = false, stale = true, loadedMode = true;
let maxRows = 500;
function message(text, error = false) { byId('message').textContent = text; byId('message').classList.toggle('error', error); }
async function api(url, body) {
  const response = await fetch(url, body === undefined ? {cache: 'no-store'} : {
    method: 'POST', headers: {'Content-Type': 'application/json', 'X-AP-Review': '1'}, body: JSON.stringify(body)
  });
  const data = await response.json();
  if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail));
  return data;
}
function totals(items) {
  // Decimal strings are summed as scaled integers, never binary floating-point money.
  const sums = new Map();
  for (const row of items) {
    const parts = row.total_amount.split('.'), scale = (parts[1] || '').length;
    let amount = BigInt(parts.join(''));
    const previous = sums.get(row.currency) || {amount: 0n, scale};
    const nextScale = Math.max(scale, previous.scale);
    amount = amount * 10n ** BigInt(nextScale - scale) + previous.amount * 10n ** BigInt(nextScale - previous.scale);
    sums.set(row.currency, {amount, scale: nextScale});
  }
  return [...sums].sort().map(([currency, {amount, scale}]) => {
    const digits = amount.toString().padStart(scale + 1, '0');
    return currency + ' ' + (scale ? digits.slice(0, -scale) + '.' + digits.slice(-scale) : digits);
  }).join(' · ') || 'No amount selected';
}
function controls() {
  byId('apply').disabled = busy;
  filterIds.forEach(id => { byId(id).disabled = busy; });
  byId('download').disabled = busy || stale || !selected.size || selected.size > maxRows;
  byId('select-all').disabled = busy || stale || !rows.length;
  byId('select-all').checked = rows.length > 0 && selected.size === rows.length;
  byId('select-all').indeterminate = selected.size > 0 && selected.size < rows.length;
  document.querySelectorAll('#rows input').forEach(input => { input.disabled = busy || stale; });
  document.querySelectorAll('#export-history button').forEach(button => { button.disabled = busy; });
  byId('count').textContent = `${rows.length} matching invoices · ${selected.size} selected`;
  byId('totals').textContent = 'Matching: ' + totals(rows) + ' | Selected: ' + totals(rows.filter(row => selected.has(row.event_id))) + ` · Up to ${maxRows} per file`;
}
function renderRows() {
  byId('rows').replaceChildren();
  for (const row of rows) {
    const tr = document.createElement('tr'), selection = document.createElement('td'), checkbox = document.createElement('input');
    checkbox.type = 'checkbox'; checkbox.checked = selected.has(row.event_id);
    checkbox.setAttribute('aria-label', 'Select invoice ' + row.invoice_number);
    checkbox.addEventListener('change', () => { checkbox.checked ? selected.add(row.event_id) : selected.delete(row.event_id); controls(); });
    selection.append(checkbox); tr.append(selection);
    const invoice = document.createElement('td'), link = document.createElement('a'), revision = document.createElement('small');
    link.href = '/reviews/' + encodeURIComponent(row.invoice_id); link.textContent = row.invoice_number;
    revision.textContent = 'Revision ' + row.review_revision;
    invoice.append(link, revision); tr.append(invoice);
    for (const [value, numeric] of [[row.supplier_name], [row.invoice_date], [row.currency], [row.total_amount, true], [row.approval_method], [row.exported ? 'Exported' : 'Not yet exported']]) {
      const td = document.createElement('td'); td.textContent = value; if (numeric) td.className = 'number'; tr.append(td);
    }
    byId('rows').append(tr);
  }
  byId('empty').hidden = rows.length > 0;
  controls();
}
async function refresh() {
  const params = new URLSearchParams({only_unexported: byId('mode').value});
  for (const [id, key] of [['date-from', 'date_from'], ['date-to', 'date_to'], ['supplier', 'supplier'], ['currency', 'currency']]) {
    if (byId(id).value.trim()) params.set(key, byId(id).value.trim());
  }
  stale = true; selected.clear(); controls();
  const data = await api('/api/ap/export-register?' + params);
  rows = data.rows; maxRows = data.max_batch_rows; loadedMode = byId('mode').value === 'true'; stale = false;
  renderRows();
}
async function history() {
  const data = await api('/api/ap/export-batches');
  byId('export-history').replaceChildren();
  for (const batch of data) {
    const li = document.createElement('li'), text = document.createElement('div'), detail = document.createElement('small'), button = document.createElement('button');
    text.textContent = `${batch.row_count} invoices · ${batch.status} · ${batch.created_at}`;
    detail.className = 'meta'; detail.textContent = `Export ${batch.export_id} · Attempts ${batch.attempts}/5${batch.last_error ? ' · ' + batch.last_error : ''}`;
    text.append(document.createElement('br'), detail);
    button.textContent = 'Open saved export'; button.addEventListener('click', () => run(async () => showBatch(await api('/api/ap/export-batches/' + batch.export_id))));
    li.append(text, button); byId('export-history').append(li);
  }
  if (!data.length) { const li = document.createElement('li'); li.textContent = 'No combined Excel files yet.'; byId('export-history').append(li); }
}
function showBatch(batch, download = false) {
  byId('ready').hidden = false;
  const link = byId('file-link'); link.hidden = !batch.download_url;
  if (batch.download_url) { link.href = batch.download_url; link.download = ''; }
  byId('file-detail').textContent = `${batch.row_count} invoices · Export ${batch.export_id} · ${batch.status} · File ${batch.file_health}`;
  byId('ready').querySelector(':scope > button')?.remove();
  window.showOutcomeNotification('batch', batch.export_id, byId('outcome-notification'));
  if (!batch.download_url) {
    const retry = document.createElement('button'); retry.textContent = 'Retry this export';
    retry.disabled = batch.attempts >= batch.max_attempts;
    retry.addEventListener('click', () => run(async () => {
      const result = await api('/api/ap/export-batches/' + batch.export_id + '/retry', {});
      await refresh(); await history(); showBatch(result, true); message('Excel recovered. The original selection is unchanged.');
    })); byId('ready').append(retry);
  }
  if (download && batch.download_url) link.click();
}
async function run(action) {
  if (busy) return;
  busy = true; controls();
  try { await action(); }
  catch (error) { message(error.message + ' Refresh the register or open export history to retry the saved selection.', true); await history().catch(() => {}); }
  finally { busy = false; controls(); }
}
filterIds.forEach(id => byId(id).addEventListener('input', () => {
  stale = true; selected.clear(); renderRows(); message('Filters changed. Apply filters before selecting invoices.');
}));
byId('apply').addEventListener('click', () => run(async () => { await refresh(); await history(); message('Preview updated. Select invoices to download.'); }));
byId('select-all').addEventListener('change', () => { selected = new Set(byId('select-all').checked ? rows.map(row => row.event_id) : []); renderRows(); });
byId('download').addEventListener('click', () => run(async () => {
  const batch = await api('/api/ap/export-batches', {event_ids: [...selected], only_unexported: loadedMode});
  showBatch(batch, true); await refresh(); await history(); message('Excel saved. Use Download saved Excel if your browser did not start the download.');
}));
run(async () => { await refresh(); await history(); message('Select invoices to create a combined Excel file. Approval records remain unchanged.'); });
