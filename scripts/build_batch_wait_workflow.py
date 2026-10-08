"""Build the minimal batch-wait candidate from the saved published native workflow."""
import copy
import json
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
original = json.loads((ROOT / 'n8n_workflows/AP_native_before_batch_wait_20261007.json').read_text(encoding='utf-8'))
w = copy.deepcopy(original)
by = {n['name']: n for n in w['nodes']}
ops = []


def params(name, value):
    by[name]['parameters'] = value
    ops.append(dict(type='updateNodeParameters', nodeName=name, parameters=value, replace=True))


def add(name, kind, parameters, version, position, notes, auth=False, once=False):
    n = dict(name=name, id=str(uuid4()), type='n8n-nodes-base.' + kind, typeVersion=version,
             parameters=parameters, position=position, notes=notes)
    if auth:
        n['credentials'] = copy.deepcopy(by['Forward Saved Decision']['credentials'])
    by[name] = n
    w['nodes'].append(n)
    ops.append(dict(type='addNode', node=copy.deepcopy(n)))
    if once:
        n['executeOnce'] = True
        ops.append(dict(type='setNodeSettings', nodeName=name, settings={'executeOnce': True}))
    return n


def edge(source, target, out=0, remove=False):
    outputs = w['connections'].setdefault(source, {}).setdefault('main', [])
    while len(outputs) <= out:
        outputs.append([])
    if remove:
        outputs[out] = [e for e in outputs[out] if e['node'] != target]
    else:
        outputs[out].append(dict(node=target, type='main', index=0))
    ops.append(dict(type='removeConnection' if remove else 'addConnection', source=source,
                    target=target, sourceIndex=out, targetIndex=0))


def http(path, method='GET', body=None):
    p = dict(method=method, url=path, options={'timeout': 15000})
    if method == 'POST':
        p.update(authentication='genericCredentialType', genericAuthType='httpHeaderAuth')
    if body:
        p.update(sendBody=True, specifyBody='json', jsonBody=body)
    return p


def condition(expression):
    p = copy.deepcopy(by['Continue Email Batch?']['parameters'])
    p['conditions']['conditions'][0]['leftValue'] = expression
    return p


p = copy.deepcopy(by['Prepare Invoice Files']['parameters'])
p['jsCode'] = p['jsCode'].replace("attachment_id:'0'", "attachment_id:'0',batch_id:'upload-'+$execution.id,case_id:'upload',notification_mode:'batch'")
p['jsCode'] = p['jsCode'].replace("case_id:match[2]", "case_id:match[2],notification_mode:'batch'")
params('Prepare Invoice Files', p)
p = copy.deepcopy(by['Show Upload Result']['parameters'])
p['responseBody'] = "={{ {...$json, formSubmittedText: $json.outcome === 'decision_ready' ? 'Saved decision: ' + $json.review_status + '. Approved records are available at http://127.0.0.1:8000/exports. A batch summary follows in local Mailpit.' : $json.outcome === 'review_ready' ? 'Waiting for human review: ' + $json.review_url + '. You can close this page. A batch reminder follows in local Mailpit.' : 'Result: ' + $json.outcome + '. ' + $json.error_code + '. The batch summary will retain this exception.'} }}"
params('Show Upload Result', p)
params('Start Here', {**by['Start Here']['parameters'], 'content': '### Invoice Intake & Approval\nUpload one invoice or process a selected email batch. The Agent extracts facts; code checks approval rules. All attachments finish processing before this execution waits for human review.'})
params('Reviewer Actions', {**by['Reviewer Actions']['parameters'], 'content': '### Review in the Portal\nOpen the invoice links in the batch reminder in [Mailpit](http://127.0.0.1:8025). Compare the original, save changes, then approve or reject. Wait for Review checks saved decisions every 70 seconds; it never approves. Lower event entries remain for legacy delivery and recovery.'})
by['Reviewer Actions']['position'] = [0, 960]
ops.append(dict(type='setNodePosition', nodeName='Reviewer Actions', position=[0, 960]))
params('Excel Actions', {**by['Excel Actions']['parameters'], 'content': '### Export When Needed\nApproved records are automatically available in the [Export Portal](http://127.0.0.1:8000/exports), including while other invoices wait. Select rows to create Excel. Rejected or pending invoices are excluded. Export is not payment.'})
params('Demo Scope', {**by['Demo Scope']['parameters'], 'content': '### Honest Demo\nRe-uploaded samples reuse saved analysis; they do not call Gemini again. Batch counts separate new and reused invoice records, rejections and technical failures. Stage A remains the explicit rollback. Existing sample and final-expression validation limits still apply.'})

add('Read Saved Invoice Decision', 'httpRequest', http("={{ 'http://python-api:8000/api/ap/stages/' + $json.run_id }}"), 4.4, [3408, 0], 'Approval already saved the exportable snapshot. This batch sends one final summary; no per-invoice result email.')
add('Human Review Pending', 'httpRequest', http("={{ 'http://python-api:8000/api/ap/stages/' + $json.run_id }}"), 4.4, [3408, 256], 'The saved review task awaits a person. Continue processing other attachments before sending the batch reminder and waiting.')
add('Read Batch Status', 'httpRequest', http('http://python-api:8000/api/ap/intake-batches', 'POST', "={{ {run_ids: $input.all().map(item => item.json.run_id)} }}"), 4.4, [1168, 1088], 'Freeze this execution’s completed intake runs once and read current review states. No model call or approval.', True, True)
add('Pending Reviews?', 'if', condition('={{ $json.pending > 0 || $json.unresolved > 0 }}'), 2.3, [1456, 1088], 'Only this intake batch controls the wait; processing failures and rejected invoices remain separate counts.')
add('Notify Pending Reviews', 'httpRequest', http("={{ 'http://python-api:8000/api/ap/intake-batches/' + $json.batch_id + '/notify/pending' }}", 'POST'), 4.4, [1744, 1264], 'Send one local reminder with pending invoice links. A durable claim prevents duplicate or uncertain sends.', True)
add('Wait for Review', 'wait', {'resume': 'timeInterval', 'amount': 70, 'unit': 'seconds'}, 1.1, [2032, 1264], 'Persist this execution while waiting 70 seconds. Human review happens in the existing portal; no automatic approval or repeated reminder.')
add('Read Latest Review Status', 'httpRequest', http("={{ 'http://python-api:8000/api/ap/intake-batches/' + $json.batch_id }}"), 4.4, [2320, 1264], 'Reload current database decisions for the fixed batch, including edits and rejections.')
add('Reviews Still Pending?', 'if', condition('={{ !$json.complete }}'), 2.3, [2608, 1264], 'Pending or unresolved reviews return to Wait. The summary runs only after all review decisions are final.')
add('Send Batch Summary', 'httpRequest', http("={{ 'http://python-api:8000/api/ap/intake-batches/' + $json.batch_id + '/notify/summary' }}", 'POST'), 4.4, [2896, 1088], 'Send one local summary: new/reused records, approvals, rejections, failures and skips. Include the export portal link; do not create Excel.', True)

for old, new in [('Forward Saved Decision', 'Read Saved Invoice Decision'), ('Request Invoice Review', 'Human Review Pending')]:
    for source, connection in list(w['connections'].items()):
        for index, output in enumerate(connection.get('main', [])):
            if any(e['node'] == old for e in output):
                edge(source, old, index, True)
                edge(source, new, index)
    edge(old, 'Continue Email Batch?', remove=True)
    edge(new, 'Continue Email Batch?')
    ops.append(dict(type='removeNode', nodeName=old))
    w['nodes'] = [n for n in w['nodes'] if n['name'] != old]
    del w['connections'][old]
edge('Email Batch Complete', 'Read Batch Status')
edge('Show Upload Result', 'Read Batch Status')
edge('Read Batch Status', 'Pending Reviews?')
edge('Pending Reviews?', 'Notify Pending Reviews')
edge('Pending Reviews?', 'Send Batch Summary', 1)
edge('Notify Pending Reviews', 'Wait for Review')
edge('Wait for Review', 'Read Latest Review Status')
edge('Read Latest Review Status', 'Reviews Still Pending?')
edge('Reviews Still Pending?', 'Wait for Review')
edge('Reviews Still Pending?', 'Send Batch Summary', 1)
w['settings']['executionTimeout'] = -1
ops.append(dict(type='setWorkflowSettings', settings={'executionTimeout': -1}))


def js(value):
    if isinstance(value, str) and value.startswith('={{'):
        return 'expr(' + json.dumps(value[1:]) + ')'
    if isinstance(value, dict):
        return '{' + ','.join(json.dumps(k) + ':' + js(v) for k, v in value.items()) + '}'
    if isinstance(value, list):
        return '[' + ','.join(map(js, value)) + ']'
    return json.dumps(value, ensure_ascii=False)


names = {n['name']: 'n' + str(i) for i, n in enumerate(w['nodes'])}
subnames = {'Gemini via Bounded Gateway', 'Read Invoice Page', 'Find Field Evidence', 'Check Document Quality'}
lines = ["import {workflow,node,trigger,ifElse,switchCase,splitInBatches,nextBatch,newCredential,expr,languageModel,tool} from '@n8n/workflow-sdk';"]
ordered = sorted(w['nodes'], key=lambda n: n['name'] not in subnames)
for n in ordered:
    kind = n['type'].split('.')[-1]
    factory = 'languageModel' if n['name'] == 'Gemini via Bounded Gateway' else 'tool' if n['name'] in subnames else 'trigger' if kind in ('manualTrigger', 'formTrigger', 'webhook') else {'if': 'ifElse', 'switch': 'switchCase', 'splitInBatches': 'splitInBatches'}.get(kind, 'node')
    config = {k: n[k] for k in ('name', 'parameters', 'position', 'notes', 'onError', 'retryOnFail', 'executeOnce') if k in n}
    encoded = js(config)[:-1]
    if n.get('credentials'):
        encoded += ',credentials:{' + ','.join(json.dumps(k) + ':newCredential(' + json.dumps(v['name']) + ',' + json.dumps(v['id']) + ')' for k, v in n['credentials'].items()) + '}'
    if kind == 'agent':
        encoded += ',subnodes:{model:' + names['Gemini via Bounded Gateway'] + ',tools:[' + ','.join(names[x] for x in ('Read Invoice Page', 'Find Field Evidence', 'Check Document Quality')) + ']}'
    typepart = '' if factory in ('ifElse', 'switchCase', 'splitInBatches') else 'type:' + json.dumps(n['type']) + ','
    lines.append(f"const {names[n['name']]}={factory}({{{typepart}version:{n['typeVersion']},config:{encoded}}},output:[{{}}]}});")


def v(name):
    return names[name]


lines += [
    f"const waitPath={v('Wait for Review')}.to({v('Read Latest Review Status')}.to({v('Reviews Still Pending?')}.onTrue({v('Wait for Review')}).onFalse({v('Send Batch Summary')})));",
    f"const batchPath={v('Read Batch Status')}.to({v('Pending Reviews?')}.onTrue({v('Notify Pending Reviews')}.to(waitPath)).onFalse({v('Send Batch Summary')}));",
    f"const finish={v('Continue Email Batch?')}.onTrue(nextBatch({v('Process One Invoice')})).onFalse({v('Show Upload Result')}.to(batchPath));",
    f"const route={v('Route Invoice Result')}.onCase(0,{v('Read Saved Invoice Decision')}.to(finish)).onCase(1,{v('Read Saved Invoice Decision')}).onCase(2,{v('Human Review Pending')}.to(finish)).onCase(3,{v('Read Skipped or Failed Result')}.to(finish)).onCase(4,{v('Read Skipped or Failed Result')});",
    f"const analyzed={v('Check Invoice & Apply Approval Rules')}.to(route);",
    f"const analysis={v('New Analysis or Cache?')}.onCase(0,{v('Extract Invoice Details')}.to({v('Save Analysis Draft')}.to(analyzed))).onCase(1,{v('Reuse Verified Analysis')}.to(analyzed)).onCase(2,route);",
    f"{v('Prepare Invoice Analysis')}.onError({v('Record Analysis Failure')}); {v('Extract Invoice Details')}.onError({v('Record Analysis Failure')}); {v('Save Analysis Draft')}.onError({v('Record Analysis Failure')}); {v('Record Analysis Failure')}.to(route);",
    f"const invoices={v('Process One Invoice')}.onDone({v('Email Batch Complete')}.to(batchPath)).onEachBatch({v('Save Invoice & Read Text')}.to({v('Prepare Invoice Analysis')}.to(analysis)));",
    f"export default workflow('ap-native-batch-wait',{js(w['name'])}).add({v('Run Demo Email Batch')}).to({v('Fetch Invoice Emails')}).to({v('Prepare Invoice Files')}).to(invoices).add({v('Upload Invoice')}).to({v('Prepare Invoice Files')})",
    f".add({v('Approval Decision Received')}).to({v('Verify Saved Approval Decision')}).to({v('Approved?')}.onTrue({v('Send Approval Confirmation')}).onFalse({v('Send Rejection Notice')}))",
    f".add({v('Excel File Ready')}).to({v('Check Export File')}).to({v('Send Excel Download Link')})",
]
for group in w['nodeGroups']:
    lines.append('.group(' + json.dumps(group['name']) + ',[' + ','.join(v(n) for n in group['nodeNames']) + '],' + js({'description': group['description']}) + ')')
for name in ('Start Here', 'Reviewer Actions', 'Excel Actions', 'Demo Scope'):
    lines.append('.add(' + v(name) + ')')
lines[-1] += ';'
(ROOT / 'n8n_workflows/AP_native_batch_wait_candidate.json').write_text(json.dumps(w, indent=2, ensure_ascii=False), encoding='utf-8')
(ROOT / 'n8n_workflows/AP_native_batch_wait_operations.json').write_text(json.dumps(ops, indent=2, ensure_ascii=False), encoding='utf-8')
(ROOT / 'scripts/AP_native_batch_wait.ts').write_text('\n'.join(lines), encoding='utf-8')
print(f'{len(w["nodes"])} nodes; {len(ops)} operations. Candidate only; not published.')
