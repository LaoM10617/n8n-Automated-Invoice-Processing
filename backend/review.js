/* Version-aware local review. Untrusted invoice text is only assigned via textContent/value. */
'use strict';
const invoice = document.querySelector('main').dataset.invoice;
const endpoint = '/api/ap/invoices/' + encodeURIComponent(invoice) + '/review';
const byId = id => document.getElementById(id);
const fields = [...document.querySelectorAll('[data-field]')];
let state;
let dirty = false;
let busy = false;

function message(text) { byId('review-message').textContent = text; }
function buttons() {
  const pending = state && state.status === 'pending' && !busy;
  byId('save-review').disabled = !pending || state.version_conflict;
  byId('approve-review').disabled = !pending || dirty || state.version_conflict || !state.current_revision || !state.validation.can_approve;
  byId('reject-review').disabled = !pending || dirty || state.version_conflict || !state.current_revision;
  byId('adopt-review').hidden = !(pending && state.version_conflict);
  fields.forEach(input => { input.disabled = !pending || state.version_conflict; });
}
async function api(method, body) {
  const response = await fetch(endpoint + (method === 'POST' ? '/decision' : ''), {
    method, headers: {'Content-Type': 'application/json', 'X-AP-Review': '1'},
    ...(body ? {body: JSON.stringify(body)} : {})
  });
  const data = await response.json();
  if (!response.ok) throw new Error((response.status === 409 ? 'Conflict. Refresh and compare. ' : '') + (typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail)));
  return data;
}
function resolution(kind, id, title, previous) {
  const div = document.createElement('div'); div.className = 'resolution';
  div.dataset.kind = kind; div.dataset.id = id;
  const label = document.createElement('label');
  const check = document.createElement('input'); check.type = 'checkbox'; check.checked = !!previous;
  label.append(check, document.createTextNode(' ' + title));
  const note = document.createElement('textarea'); note.placeholder = 'What you checked and why this issue is resolved';
  note.setAttribute('aria-label', title + ' resolution reason'); note.maxLength = 2000; note.value = previous?.reason || '';
  const page = document.createElement('input'); page.type = 'number'; page.min = '1'; page.value = previous?.page || 1;
  page.setAttribute('aria-label', title + ' original page');
  div.append(label, note, document.createTextNode(' Original page '), page);
  div.addEventListener('input', () => { dirty = true; buttons(); });
  byId('resolutions').append(div);
}
function render(data) {
  state = data; dirty = false;
  byId('review-status').textContent = data.status === 'approved' ? 'Approved; export pending' : data.status === 'rejected' ? 'Rejected' : 'Pending review';
  byId('version-detail').textContent = `Revision ${data.current_revision} · Analysis ${data.processing_attempt_id} · ${data.analysis_source} · ${data.reviewer}. Modified values and reasons are recorded in revision history.`;
  fields.forEach(input => {
    input.value = data.current_fields[input.dataset.field] ?? '';
    const machine = document.querySelector(`[data-machine="${input.dataset.field}"]`);
    if (machine) machine.textContent = data.machine_fields[input.dataset.field] ?? 'Not extracted';
  });
  byId('machine-draft').textContent = JSON.stringify(data.raw_extraction, null, 2);
  byId('review-history').textContent = JSON.stringify(data.history.map(r => ({...r, changes: JSON.parse(r.changes_json), changes_json: undefined})), null, 2);
  byId('approval-issues').replaceChildren();
  for (const issue of data.validation.issues) {
    const li = document.createElement('li'); li.textContent = `${issue.code}: ${issue.message}`;
    byId('approval-issues').append(li);
  }
  if (!data.validation.issues.length) {
    const li = document.createElement('li'); li.textContent = 'No current blockers. Compare every field with the original before saving and approving.';
    byId('approval-issues').append(li);
  }
  byId('resolutions').replaceChildren();
  for (const issue of data.validation.machine_issues.filter(i => i.resolvable))
    resolution('evidence', issue.id, `${issue.code}: ${issue.message}`, data.evidence_resolutions.find(r => r.id === issue.id));
  for (const candidate of data.validation.duplicate_candidates)
    resolution('duplicate', candidate.id, `Not a duplicate / justified continuation: ${candidate.invoice_id}`, data.duplicate_resolutions.find(r => r.id === candidate.id));
  if (data.status !== 'pending') byId('resolutions').querySelectorAll('input,textarea').forEach(el => { el.disabled = true; });
  byId('latest-analysis').hidden = !data.version_conflict;
  byId('latest-analysis').querySelector('pre').textContent = JSON.stringify(data.latest_fields, null, 2);
  buttons();
}
function version() { return {expected_revision: state.current_revision, processing_attempt_id: state.processing_attempt_id}; }
async function save(adopt = false) {
  const changes = {};
  if (!adopt) for (const input of fields) {
    const value = input.dataset.field === 'has_adjustments' ? (input.value === '' ? null : input.value === 'true') : input.value.trim() || null;
    if (value !== (state.current_fields[input.dataset.field] ?? null)) changes[input.dataset.field] = value;
  }
  const body = {...version(), changes, reason: byId('review-reason').value, page: Number(byId('review-page').value), evidence_resolutions: [], duplicate_resolutions: []};
  if (adopt) body.adopt_attempt_id = state.latest_attempt_id;
  else for (const div of byId('resolutions').children) {
    if (div.querySelector('[type=checkbox]').checked) body[div.dataset.kind + '_resolutions'].push({id: div.dataset.id, reason: div.querySelector('textarea').value, page: Number(div.querySelector('[type=number]').value)});
  }
  await perform(() => api('PATCH', body), 'Saved. Approval checks have been rerun.');
}
async function perform(action, success) {
  busy = true; buttons();
  try { render(await action()); message(success); }
  catch (error) { message(error.message); }
  finally { busy = false; buttons(); }
}
fields.forEach(input => input.addEventListener('input', () => { dirty = true; buttons(); message('Unsaved changes. Save and recheck before deciding.'); }));
byId('save-review').addEventListener('click', () => save());
byId('adopt-review').addEventListener('click', () => save(true));
for (const decision of ['approve', 'reject']) byId(decision + '-review').addEventListener('click', () => {
  if (dirty) return message('Save changes before deciding.');
  perform(() => api('POST', {...version(), decision, request_id: crypto.randomUUID(), reason: byId('review-reason').value}), decision === 'approve' ? 'Approved; export pending. The decision and snapshot are saved.' : 'Rejected. No export will be created.');
});
api('GET').then(data => { render(data); message(data.version_conflict ? 'Analysis changed. Compare the new analysis below, enter a reason, and explicitly accept it. Saved manual values are retained.' : 'Saved review loaded. Compare with the original.'); }).catch(error => message(error.message));
