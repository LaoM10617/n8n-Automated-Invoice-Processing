"""Derive a compact opt-in policy workflow from v7; preserve the original file."""
import copy
import json
from pathlib import Path
from uuid import uuid4

root = Path(__file__).resolve().parents[1] / 'n8n_workflows'
workflow = json.loads((root / '01_AP_agent_intake_v7.json').read_text(encoding='utf-8'))
workflow.update(id='APApprovalIntakeV8', name='01_AP_Approval_Intake_v8', active=False, pinData={})
nodes = {node['name']: node for node in workflow['nodes']}
for node in workflow['nodes']:
    node['id'] = str(uuid4())
    if 'webhookId' in node:
        node['webhookId'] = str(uuid4())
nodes['Upload Invoice']['parameters'].update(path='ap-approval-intake-v8', formDescription='AP intake with deterministic approval. Eligible EUR gross totals below 10,000 are approved; exceptions go to local review. Export delivery is not connected yet. Reuse Upload ID to retry.')
validation = nodes['Validate & Save Result']
validation['parameters']['url'] = "={{ 'http://python-api:8000/api/ap/stages/' + $json.run_id + '/validate-policy' }}"
validation['parameters'].update(sendHeaders=True, headerParameters={'parameters': [{'name': 'X-AP-Review', 'value': '1'}]})
validation['name'] = 'Validate & Apply Approval Policy'
decision = copy.deepcopy(nodes['Route Outcome'])
decision.update(id=str(uuid4()), name='Decision Saved?', position=[1680, 140])
decision['parameters']['conditions']['conditions'][0]['leftValue'] = "={{ $json.outcome === 'decision_ready' }}"
workflow['nodes'].append(decision)
nodes['Route Outcome']['position'] = [1920, 240]
nodes['Notify Reviewer']['position'] = [2160, 140]
nodes['Record Exception']['position'] = [2160, 340]
nodes['Return or Continue']['position'] = [2400, 140]
nodes['Upload Result']['position'] = [2640, 240]
nodes['Upload Result']['parameters']['responseBody'] = "={{ {...$json, formSubmittedText: $json.outcome === 'decision_ready' ? 'Decision: ' + $json.review_status + '. Event saved; export delivery pending. Review: ' + $json.review_url : $json.outcome === 'review_ready' ? 'Manual review: ' + $json.review_url + '. Notification: ' + $json.notification_status : 'Result: ' + $json.outcome + '. ' + $json.error_code} }}"
connections = workflow['connections']
connections['Validate & Apply Approval Policy'] = {'main': [[{'node': 'Decision Saved?', 'type': 'main', 'index': 0}]]}
del connections['Validate & Save Result']
for connection in connections.values():
    for output in connection['main']:
        for edge in output:
            if edge['node'] == 'Validate & Save Result':
                edge['node'] = 'Validate & Apply Approval Policy'
connections['Decision Saved?'] = {'main': [
    [{'node': 'Return or Continue', 'type': 'main', 'index': 0}],
    [{'node': 'Route Outcome', 'type': 'main', 'index': 0}]]}
nodes['Business Overview']['parameters'].update(content='## AP intake | Deterministic approval and human review\nUpload / readonly Gmail → Archive & Read → Invoice Analysis Agent → Validate & Apply Approval Policy. Approved/rejected decisions return immediately; pending reviews notify the local reviewer. Technical checks, versions and audit records stay in Python.', width=2800)
nodes['Current Scope']['parameters'].update(content='## Derived from APAgentIntakeV7; v7 is preserved\nOnly newly created review tasks enter automatic policy here. Existing pending tasks require explicit reevaluation. EUR gross total must be positive and below 10,000; all validation, evidence, quality and duplicate checks must pass. AI never approves. Human edits remain manual.\n\nBoth decisions save an immutable snapshot and durable event. The independent 02 workflow and Excel delivery are not connected in this step. Mailpit is local only. No payment, external accounting, mailbox deletion or external notification. Bind the existing readonly Gmail credential after import. This export is inactive for safe import.', width=2800)
names = {node['name'] for node in workflow['nodes']}
assert len(names) == len(workflow['nodes'])
assert all(edge['node'] in names for connection in connections.values() for output in connection['main'] for edge in output)
(root / '01_AP_approval_intake_v8.json').write_text(json.dumps(workflow, indent=2) + '\n', encoding='utf-8')
print(f'{len(names) - 2} execution nodes, 2 notes; v7 unchanged.')
