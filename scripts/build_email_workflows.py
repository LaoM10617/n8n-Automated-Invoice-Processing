import json,copy,uuid
from pathlib import Path
root=Path('n8n_workflows');base=json.loads((root/'01_AP_intake_notify_v4.json').read_text(encoding='utf-8'))
w=copy.deepcopy(base);w['id']='APEmailAttachmentV1';w['name']='01_AP_Email_Attachment_v1'
remove={'Upload Invoice','Normalize Upload','Show Intake Result','Format Intake Result'}
w['nodes']=[n for n in w['nodes'] if n['name'] not in remove]
w['connections']={k:v for k,v in w['connections'].items() if k not in remove}
for c in w['connections'].values():
 for out in c['main']:
  for edge in out:
   if edge['node']=='Format Intake Result':edge['node']='Summarize Attachment'
nodes={n['name']:n for n in w['nodes']}
def add(name,typ,p,x,y,ver=2,**extra):
 n={'id':str(uuid.uuid4()),'name':name,'type':'n8n-nodes-base.'+typ,'typeVersion':ver,'position':[x,y],'parameters':p,**extra};w['nodes'].append(n);return n
def link(a,b,out=0):
 main=w['connections'].setdefault(a,{'main':[]})['main']
 while len(main)<=out:main.append([])
 main[out]=[{'node':b,'type':'main','index':0}]
add('Attachment Input','executeWorkflowTrigger',{'inputSource':'passthrough'},0,200,1.1)
p=copy.deepcopy(nodes['Processing Completed']['parameters']);p['conditions']['conditions'][0]['leftValue']='={{ Boolean($json.supported) }}'
add('Supported Attachment','if',p,240,200,2.3)
link('Attachment Input','Supported Attachment');link('Supported Attachment','Store Original and Register Intake');link('Supported Attachment','Summarize Attachment',1)
add('Summarize Attachment','code',{'jsCode':"""const source=$('Attachment Input').first().json;
let intake={}, review={}, processing={};
try {intake=$('Store Original and Register Intake').first().json;} catch {}
try {processing=$('Extract Validate and Check Duplicates').first().json;} catch {}
try {review=$('Create Review Task').first().json;} catch {}
const saved=intake.body || {};
const status=!source.supported?'skipped':!saved.receipt_id?'intake_failed':review.body?.review_status==='pending'?'review_ready':processing.body?.processing_status==='processed'?'review_failed':'processing_failed';
const reason=!source.supported?source.skip_reason:status==='review_ready'?'PENDING_REVIEW':`HTTP_${(status==='intake_failed'?intake:status==='processing_failed'?processing:review).statusCode || 'NETWORK_ERROR'}`;
return [{json:{source_namespace:source.source_namespace,source_id:source.source_id,attachment_id:source.attachment_id,batch_id:source.batch_id,case_id:source.case_id,status,reason_code:reason,receipt_id:saved.receipt_id || null,invoice_id:saved.invoice_id || null}}];"""},3300,240)
add('Persist Email Outcome','httpRequest',{'method':'POST','url':'http://python-api:8000/api/ap/email-outcomes','sendBody':True,'specifyBody':'json','jsonBody':'={{ $json }}','options':{'timeout':30000}},3540,240,4.2)
link('Summarize Attachment','Persist Email Outcome')
# Read current configuration before deciding whether a model call is needed.
add('Read Current Processing','httpRequest',{'url':"={{ 'http://python-api:8000/api/ap/invoices/' + $json.body.invoice_id }}",'options':copy.deepcopy(nodes['Extract Validate and Check Duplicates']['parameters']['options'])},850,20,4.2)
p=copy.deepcopy(nodes['Processing Completed']['parameters']);p['conditions']['conditions'][0]['leftValue']="={{ Boolean($json.body && $json.body.processing_status === 'processed' && $json.body.processing_result?.pipeline_version === 'step4-layout-v1' && $json.body.processing_result?.model === 'gemini-3.5-flash-lite' && $json.body.processing_result?.model_base_url === 'https://generativelanguage.googleapis.com/v1beta/openai') }}"
add('Current Gemini Cache','if',p,1080,20,2.3)
add('Pace Uncached Model Call','wait',{'amount':65,'unit':'seconds'},1080,-180,1.1,webhookId=str(uuid.uuid4()))
link('Intake Accepted','Read Current Processing');link('Read Current Processing','Current Gemini Cache');link('Current Gemini Cache','Extract Validate and Check Duplicates');link('Current Gemini Cache','Pace Uncached Model Call',1);link('Pace Uncached Model Call','Extract Validate and Check Duplicates')
nodes['Scope and Template Provenance']['parameters']['content']='## One email attachment per child execution\nGmail parent runs serially with one item per call. Same storage, processing, review and notification APIs as upload v4. Unsupported/no attachments get a persisted skipped outcome. Invalid PDF content is rejected by the backend and counted. Uncached calls wait 65 seconds; the backend rate gate remains authoritative. Cache condition reflects the current Gemini configuration; update it when switching model. SMTP is local Mailpit only. No mailbox mutation or deletion. Based on the preserved original template and v4; not a claim of Gmail runtime verification.'
(root/'01_AP_email_attachment_v1.json').write_text(json.dumps(w,indent=2)+'\n')
# Parent reuses the original Gmail Get Many pattern but a manual, batch-scoped query.
p={'id':'APGmailIntakeV1','name':'01_AP_Gmail_Intake_v1','nodes':[],'connections':{},'settings':{'executionOrder':'v1','timezone':'Europe/Berlin','saveDataSuccessExecution':'all','saveDataErrorExecution':'all'},'active':False,'pinData':{}}
original=json.loads((root/'Email invoice archiving & data extraction.json').read_text(encoding='utf-8'))
g=copy.deepcopy(next(n for n in original['nodes'] if n['name']=='Get many messages'))
g['id']=str(uuid.uuid4());g['position']=[250,200];g.pop('credentials',None)
existing_parent = root/'01_AP_gmail_intake_v1.json'
if existing_parent.exists():
 previous_parent = json.loads(existing_parent.read_text(encoding='utf-8'))
 previous_gmail = next(n for n in previous_parent['nodes'] if n['name']=='Get many messages')
 if previous_gmail.get('credentials'):
  g['credentials'] = previous_gmail['credentials']
g['parameters']={'operation':'getAll','returnAll':True,'simple':False,'filters':{'q':'subject:AP-DEMO subject:phase01-connect-001'},'options':{'downloadAttachments':True,'dataPropertyAttachmentsPrefixName':'attachment_'}}
p['nodes'].append(g)
def pn(name,typ,params,x,ver=2):
 p['nodes'].append({'id':str(uuid.uuid4()),'name':name,'type':'n8n-nodes-base.'+typ,'typeVersion':ver,'position':[x,200],'parameters':params})
def pl(a,b,out=0):
 main=p['connections'].setdefault(a,{'main':[]})['main']
 while len(main)<=out:main.append([])
 main[out]=[{'node':b,'type':'main','index':0}]
pn('Run Controlled Batch','manualTrigger',{},0,1)
pn('Split Email Attachments','code',{'jsCode':"""const results=[];
for (const [i,item] of $input.all().entries()) {
 const j=item.json;
 const match=String(j.subject || '').match(/^\\[AP-DEMO\\]\\[([A-Za-z0-9_-]{1,80})\\]\\[([A-Za-z0-9_-]{1,80})\\]/);
 if (!match || !j.id) throw new Error('Expected a batch-tagged email with a provider message ID.');
 const keys=Object.keys(item.binary || {});
 for (const key of keys.length?keys:['none']) {
  const b=item.binary?.[key];
  const supported=Boolean(b && ['application/pdf','image/png','image/jpeg'].includes(b.mimeType));
  results.push({json:{source_type:'email',source_namespace:'gmail:ap-test-inbox',source_id:String(j.id),attachment_id:key,batch_id:match[1],case_id:match[2],supported,skip_reason:b?'UNSUPPORTED_ATTACHMENT':'NO_ATTACHMENTS'},...(b?{binary:{data:b}}:{}),pairedItem:{item:i}});
 }
}
return results;"""},500)
pn('One Attachment at a Time','splitInBatches',{'batchSize':1,'options':{}},750,3)
pn('Process Attachment','executeWorkflow',{'source':'database','workflowId':{'__rl':True,'value':'APEmailAttachmentV1','mode':'id'},'mode':'once','options':{'waitForSubWorkflow':True}},1000,1.3)
pn('Batch Finished','noOp',{},1250,1)
pl('Run Controlled Batch','Get many messages');pl('Get many messages','Split Email Attachments');pl('Split Email Attachments','One Attachment at a Time');pl('One Attachment at a Time','Batch Finished');pl('One Attachment at a Time','Process Attachment',1);pl('Process Attachment','One Attachment at a Time')
pn('Scope and Provenance','stickyNote',{'content':'## Gmail intake - manual batch only\nDerived from original Get many messages template. Bind the dedicated Gmail credential, grant read-only scope, and confirm the batch query before execution. No scheduling or mailbox deletion. Each MIME attachment ordinal retains its provider message ID. Child handles invalid items independently. Account mapping stays in private runtime configuration, not this export. Gmail binding and live execution must be verified separately.','height':250,'width':850},0,1)
p['nodes'][-1]['position']=[0,-100]
(root/'01_AP_gmail_intake_v1.json').write_text(json.dumps(p,indent=2)+'\n')
for obj in (w,p):
 names={n['name'] for n in obj['nodes']}
 assert all(k in names and all(e['node'] in names for out in c['main'] for e in out) for k,c in obj['connections'].items())
print('Attachment child and Gmail parent: JSON and targets valid; existing Gmail binding preserved if present.')

