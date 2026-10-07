"""Independent section-6 receiver; extend with Excel processing in section 7."""
import json
from pathlib import Path
from uuid import uuid4

credential = {'httpHeaderAuth': {'id': 'APReviewEventLocalV1', 'name': 'AP review event local header'}}
nodes = [
    {'id': str(uuid4()), 'name': 'Review Decision Received', 'type': 'n8n-nodes-base.webhook',
     'typeVersion': 2, 'position': [0, 200], 'webhookId': str(uuid4()), 'credentials': credential,
     'parameters': {'httpMethod': 'POST', 'path': 'ap-review-events-v1', 'authentication': 'headerAuth',
                    'responseMode': 'onReceived', 'options': {'responseCode': {'values': {'responseCode': 202}}}}},
    {'id': str(uuid4()), 'name': 'Load Current Decision', 'type': 'n8n-nodes-base.httpRequest',
     'typeVersion': 4.2, 'position': [300, 200], 'credentials': credential,
     'parameters': {'url': "={{ 'http://python-api:8000/api/ap/review-events/' + encodeURIComponent($json.body.event_id) }}",
                    'authentication': 'genericCredentialType', 'genericAuthType': 'httpHeaderAuth',
                    'options': {'timeout': 10000}}},
    {'id': str(uuid4()), 'name': 'Scope and Recovery', 'type': 'n8n-nodes-base.stickyNote',
     'typeVersion': 1, 'position': [-60, -130],
     'parameters': {'width': 820, 'height': 240, 'content': '## Independent review event receiver | Section 6\nAutomatic and manual decisions use the same entry. Header credential is required. Reload the authoritative event, current final status and immutable snapshot reference from Python; never authorize export from webhook fields.\n\nHTTP 202 means accepted, not processed. Excel and result notification are added in the next step. Accepted/failed/unknown events can be explicitly replayed with the same event ID, up to five deliveries. No automatic loop. The Compose external hook excludes the authentication header from serialized execution data; disabling execution saving alone is insufficient. Bind AP review event local header and install the hook before activating on another instance.'}},
]
workflow = {'id': 'APReviewEventsV1', 'name': '02_AP_Review_Events_v1', 'active': False,
            'nodes': nodes, 'connections': {'Review Decision Received': {'main': [[{'node': 'Load Current Decision', 'type': 'main', 'index': 0}]]}},
            'settings': {'executionOrder': 'v1', 'saveDataSuccessExecution': 'none', 'saveDataErrorExecution': 'none',
                         'saveManualExecutions': False, 'saveExecutionProgress': False}, 'pinData': {}}
path = Path(__file__).resolve().parents[1] / 'n8n_workflows/02_AP_review_events_v1.json'
path.write_text(json.dumps(workflow, indent=2) + '\n', encoding='utf-8')
print('Created independent receiver: 2 execution nodes, 1 scope note; no credential values.')
