"""Preserve v7/v8 and the section-six receiver; derive the final compact business canvases."""
import copy
import json
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1] / 'n8n_workflows'
credential = {'httpHeaderAuth': {'id': 'APReviewEventLocalV1', 'name': 'AP review event local header'}}
intake = json.loads((ROOT / '01_AP_approval_intake_v8.json').read_text(encoding='utf-8'))
intake.update(id='APApprovalIntakeV9', name='01_AP_Approval_Intake_v9', active=False, pinData={})
nodes = {n['name']: n for n in intake['nodes']}
for node in intake['nodes']:
    node['id'] = str(uuid4())
    if 'webhookId' in node:
        node['webhookId'] = str(uuid4())
nodes['Upload Invoice']['parameters'].update(path='ap-approval-intake-v9', formDescription='Upload an AP invoice. Eligible low-value EUR invoices enter the export register automatically; other invoices need review. Results go to local Mailpit. Reuse Upload ID for safe retries.')
handoff = {'id': str(uuid4()), 'name': 'Dispatch Review Outcome', 'type': 'n8n-nodes-base.httpRequest',
           'typeVersion': 4.2, 'position': [1920, -40], 'credentials': credential,
           'parameters': {'method': 'POST', 'url': "={{ 'http://python-api:8000/api/ap/stages/' + $json.run_id + '/handoff' }}",
                          'authentication': 'genericCredentialType', 'genericAuthType': 'httpHeaderAuth', 'options': {'timeout': 15000}}}
intake['nodes'].append(handoff)
intake['connections']['Decision Saved?']['main'][0] = [{'node': handoff['name'], 'type': 'main', 'index': 0}]
intake['connections'][handoff['name']] = {'main': [[{'node': 'Return or Continue', 'type': 'main', 'index': 0}]]}
nodes['Upload Result']['parameters']['responseBody'] = "={{ {...$json, formSubmittedText: $json.outcome === 'decision_ready' ? 'Decision: ' + $json.review_status + '. Export register: http://127.0.0.1:8000/exports. Outcome delivery: ' + $json.event_delivery_status : $json.outcome === 'review_ready' ? 'Manual review: ' + $json.review_url + '. Notification: ' + $json.notification_status : 'Result: ' + $json.outcome + '. ' + $json.error_code} }}"
nodes['Business Overview']['parameters']['content'] = '## AP intake | One shared upload / readonly Gmail flow\nArchive & Read → Invoice Analysis Agent → deterministic validation and approval policy. Eligible EUR gross totals below 10,000 are approved; all exceptions and larger totals go to human review. Final decisions hand off to independent workflow 02; pending tasks notify the reviewer. No waiting for a human inside this workflow.'
nodes['Current Scope']['parameters']['content'] = '## Current Phase02 flow | Derived from v8; v7 and v8 preserved\nPython owns validation, duplicate checks, immutable review revisions, durable events and notification recovery. The Agent extracts; it never approves. Historical pending tasks are not automatically approved.\n\nApproved snapshots appear in the Web export register. Users select records and download a combined Excel file; the batch-ready event also enters workflow 02. Approval, file generation and notification statuses remain separate. Local Mailpit only; no accounting submission or payment. Bind the existing readonly Gmail and AP header credentials. Retry saved IDs; never recreate business decisions to hide failures.'

def hook(name, path, y):
    return {'id': str(uuid4()), 'name': name, 'type': 'n8n-nodes-base.webhook', 'typeVersion': 2,
            'position': [0, y], 'webhookId': str(uuid4()), 'credentials': credential,
            'parameters': {'httpMethod': 'POST', 'path': path, 'authentication': 'headerAuth', 'responseMode': 'onReceived',
                           'options': {'responseCode': {'values': {'responseCode': 202}}}}}

def http(name, url, x, y, method='GET'):
    return {'id': str(uuid4()), 'name': name, 'type': 'n8n-nodes-base.httpRequest', 'typeVersion': 4.2,
            'position': [x, y], 'credentials': credential,
            'parameters': {'method': method, 'url': url, 'authentication': 'genericCredentialType',
                           'genericAuthType': 'httpHeaderAuth', 'options': {'timeout': 15000}}}

route = copy.deepcopy(nodes['Decision Saved?'])
route.update(id=str(uuid4()), name='Approved or Rejected?', position=[600, 100])
route['parameters']['conditions']['conditions'][0]['leftValue'] = "={{ $json.category === 'review_approved' }}"
notify_url = "={{ 'http://python-api:8000/api/ap/outcomes/' + $json.kind + '/' + encodeURIComponent($json.id) + '/notify' }}"
result = {'id': 'APReviewExportV1', 'name': '02_AP_Review_Export_v1', 'active': False, 'pinData': {},
          'settings': {'executionOrder': 'v1', 'saveDataSuccessExecution': 'none', 'saveDataErrorExecution': 'none', 'saveManualExecutions': False, 'saveExecutionProgress': False},
          'nodes': [hook('Review Decision Received', 'ap-review-export-v1', 100),
                    http('Load Current Decision', "={{ 'http://python-api:8000/api/ap/outcomes/review/' + encodeURIComponent($json.body.event_id) }}", 300, 100), route,
                    http('Notify Approval and Register', notify_url, 920, 0, 'POST'),
                    http('Notify Rejection', notify_url, 920, 220, 'POST'),
                    hook('Excel Batch Ready', 'ap-batch-export-v1', 510),
                    http('Verify Saved Excel Batch', "={{ 'http://python-api:8000/api/ap/outcomes/batch/' + encodeURIComponent($json.body.export_id) }}", 300, 510),
                    http('Notify Excel Download', notify_url, 600, 510, 'POST')], 'connections': {}}
for source, targets in [('Review Decision Received', ['Load Current Decision']), ('Load Current Decision', ['Approved or Rejected?']),
                        ('Approved or Rejected?', ['Notify Approval and Register', 'Notify Rejection']),
                        ('Excel Batch Ready', ['Verify Saved Excel Batch']), ('Verify Saved Excel Batch', ['Notify Excel Download'])]:
    result['connections'][source] = {'main': [[{'node': name, 'type': 'main', 'index': 0}] for name in targets]}
for y, title, content in [(-240, 'Decision and Export Contract', '## Independent outcome workflow\nReview decisions and completed Excel batches have separate entries. Read authoritative state from Python before routing. Approved snapshots are already in the Web export register; approval does not automatically create a file. Users preview/select/download combined Excel, then receive a batch download notice.'),
                         (750, 'Recovery and Local Scope', '## Durable recovery; local demonstration only\nHeader credentials and the Compose privacy hook are required on both webhook paths. HTTP 202 is acceptance, not business completion. Python persists bounded transport/SMTP attempts; uncertain SMTP sends require Mailpit Message-ID reconciliation, never blind resend. Only confirmed notification delivery completes the review event. Notification failure never reapproves or regenerates Excel. No external mail, accounting submission or payment.')]:
    result['nodes'].append({'id': str(uuid4()), 'name': title, 'type': 'n8n-nodes-base.stickyNote', 'typeVersion': 1,
                            'position': [-40, y], 'parameters': {'content': content, 'width': 1250, 'height': 220}})
for workflow, filename in [(intake, '01_AP_approval_intake_v9.json'), (result, '02_AP_review_export_v1.json')]:
    names = {n['name'] for n in workflow['nodes']}
    assert len(names) == len(workflow['nodes'])
    assert all(edge['node'] in names for connection in workflow['connections'].values() for output in connection['main'] for edge in output)
    (ROOT / filename).write_text(json.dumps(workflow, indent=2) + '\n', encoding='utf-8')
    print(workflow['id'], sum(n['type'] != 'n8n-nodes-base.stickyNote' for n in workflow['nodes']), 'execution nodes; JSON and connections checked')
