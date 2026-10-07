import copy,json,uuid
from pathlib import Path
root=Path('n8n_workflows')
def read(f):return json.loads((root/f).read_text())
u=read('01_AP_intake_notify_v4.json'); e=read('01_AP_email_attachment_v1.json'); g=read('01_AP_gmail_intake_v1.json')
w=copy.deepcopy(e);w.update(id='APUnifiedIntakeV5',name='01_AP_Unified_Intake_v5',active=False,versionId=str(uuid.uuid4()),pinData={})
remove={'Attachment Input','Scope and Template Provenance','Summarize Attachment','Persist Email Outcome'}
w['nodes']=[n for n in w['nodes'] if n['name'] not in remove]
w['connections']={k:v for k,v in w['connections'].items() if k not in remove}
for c in w['connections'].values():
 for out in c['main']:
  for edge in out:
   if edge['node']=='Summarize Attachment':edge['node']='Summarize Result'
def add(n):
 n=copy.deepcopy(n);n['id']=str(uuid.uuid4())
 if 'webhookId' in n:n['webhookId']=str(uuid.uuid4())
 w['nodes'].append(n);return n
def node(name,t,p,ver=2):return add({'name':name,'type':'n8n-nodes-base.'+t,'typeVersion':ver,'parameters':p,'position':[0,0]})
def link(a,b,out=0):
 main=w['connections'].setdefault(a,{'main':[]})['main']
 while len(main)<=out:main.append([])
 main[out]=[{'node':b,'type':'main','index':0}]
def by(name):return next(n for n in w['nodes'] if n['name']==name)
for n in u['nodes']:
 if n['name'] in ('Upload Invoice','Normalize Upload','Show Intake Result'):add(n)
by('Upload Invoice')['parameters']['path']='ap-unified-intake-v5'
by('Upload Invoice')['parameters']['formDescription']='Unified AP intake. Upload one invoice or run the controlled Gmail batch from the editor. Existing sources and invoices are reused.'
by('Normalize Upload')['parameters']['jsCode']=by('Normalize Upload')['parameters']['jsCode'].replace("direction: 'AP',", "direction: 'AP', supported: true,")
for n in g['nodes']:
 if n['name'] not in ('Process Attachment','Scope and Provenance'):add(n)
for a in ('Run Controlled Batch','Get many messages','Split Email Attachments'):
 w['connections'][a]=copy.deepcopy(g['connections'][a])
link('Upload Invoice','Normalize Upload');link('Normalize Upload','One Attachment at a Time')
link('One Attachment at a Time','Batch Finished');link('One Attachment at a Time','Prepare Item',1)
node('Prepare Item','code',{'jsCode':"const i=$input.first(); return [{json:{...i.json,ctx:{source:i.json}},...(i.binary?{binary:i.binary}:{}),pairedItem:{item:0}}];"})
link('Prepare Item','Supported Attachment')
# Carry per-item state through each HTTP response using paired-item lineage.
# Never use first() on a previously executed node inside a multi-item loop.
for name,prev,key in [('Store Original and Register Intake','Prepare Item','intake'),('Read Current Processing','Capture Intake','current'),('Extract Validate and Check Duplicates','Capture Current','processing'),('Create Review Task','Capture Processing','review'),('Claim Notification','Capture Review','claim')]:
 cap={'intake':'Capture Intake','current':'Capture Current','processing':'Capture Processing','review':'Capture Review','claim':'Capture Claim'}[key]
 old=copy.deepcopy(w['connections'][name])
 node(cap,'code',{'jsCode':f"const response=$input.first().json; const previous=$('{prev}').item.json.ctx; return [{{json:{{...response,ctx:{{...previous,{key}:response}}}},pairedItem:{{item:0}}}}];"})
 w['connections'][cap]=old;link(name,cap)
by('Classify SMTP Result')['parameters']['jsCode']=by('Classify SMTP Result')['parameters']['jsCode'].replace("$('Claim Notification').first()","$('Capture Claim').item")
# Final notification responses recover context via current item's claim lineage.
node('Capture Notification','code',{'jsCode':"const r=$input.first().json; const ctx=$('Capture Claim').item.json.ctx; return [{json:{ctx:{...ctx,notification:r}},pairedItem:{item:0}}];"})
link('Record Notification Result','Capture Notification');link('Capture Notification','Summarize Result')
node('Summarize Result','code',{'jsCode':"""const c=$input.first().json.ctx;
const s=c.source, intake=c.intake || {}, processing=c.processing || {}, review=c.review || {};
const saved=intake.body || {};
const status=!s.supported?'skipped':!saved.receipt_id?'intake_failed':review.body?.review_status==='pending'?'review_ready':processing.body?.processing_status==='processed'?'review_failed':'processing_failed';
const failed=status==='intake_failed'?intake:status==='processing_failed'?processing:review;
const notification=(c.notification || c.claim)?.body?.status || 'not_started';
return [{json:{source_type:s.source_type,source_namespace:s.source_namespace,source_id:s.source_id,attachment_id:s.attachment_id,batch_id:s.batch_id,case_id:s.case_id,status,reason_code:!s.supported?s.skip_reason:status==='review_ready'?'PENDING_REVIEW':`HTTP_${failed.statusCode || 'NETWORK_ERROR'}`,receipt_id:saved.receipt_id || null,invoice_id:saved.invoice_id || null,review_url:review.body?.review_url || null,notification_status:notification},pairedItem:{item:0}}];"""})
p=copy.deepcopy(by('Supported Attachment')['parameters']);p['conditions']['conditions'][0]['leftValue']="={{ $json.source_type === 'email' }}"
node('Email Result', 'if',p,2.3);link('Summarize Result','Email Result')
n=add(next(n for n in e['nodes'] if n['name']=='Persist Email Outcome'))
n['parameters']['jsonBody']="={{ {source_namespace:$json.source_namespace,source_id:$json.source_id,attachment_id:$json.attachment_id,batch_id:$json.batch_id,case_id:$json.case_id,status:$json.status,reason_code:$json.reason_code,receipt_id:$json.receipt_id,invoice_id:$json.invoice_id} }}"
link('Email Result','Persist Email Outcome');link('Persist Email Outcome','One Attachment at a Time')
node('Format Upload Result','code',{'jsCode':"const r=$input.first().json; return [{json:{...r,formSubmittedText:r.status==='review_ready'?`Invoice stored. Review pending: ${r.review_url}. Notification: ${r.notification_status}. Read-only review.`:`Review not ready: ${r.reason_code}. Records retained; retry the same Upload ID after resolving the error.`}}];"})
link('Email Result','Format Upload Result',1);link('Format Upload Result','Show Intake Result')
# A compact three-row canvas; all processing is inline, no child workflow calls.
rows=[['Run Controlled Batch','Get many messages','Split Email Attachments','One Attachment at a Time','Prepare Item','Supported Attachment','Store Original and Register Intake','Capture Intake','Intake Accepted'],['Read Current Processing','Capture Current','Current Gemini Cache','Pace Uncached Model Call','Extract Validate and Check Duplicates','Capture Processing','Processing Completed','Create Review Task','Capture Review','Review Ready'],['Claim Notification','Capture Claim','Send Required','Send Local Review Email','Classify SMTP Result','Record Notification Result','Capture Notification','Summarize Result','Email Result']]
for y,row in enumerate(rows):
 for x,name in enumerate(row):by(name)['position']=[x*235,y*430]
for name,pos in {'Upload Invoice':[0,-220],'Normalize Upload':[235,-220],'Batch Finished':[705,-220],'Persist Email Outcome':[1880,1100],'Format Upload Result':[2115,1100],'Show Intake Result':[2350,1100]}.items():by(name)['position']=pos
node('Overview','stickyNote',{'content':'## PHASE 01 | Unified upload + Gmail\nBoth entries run the same inline processing chain. Gmail is a readonly manual batch (phase01-connect-001); no new external mail is sent. Upload uses the production form path ap-unified-intake-v5. Original v4 and email workflows are preserved.','width':2200,'height':190},1)['position']=[0,-470]
node('Processing Notes','stickyNote',{'content':'## Persistence, validation and review\nPython owns originals, OCR/Gemini extraction, validation, duplicate candidates and pending tasks. Capture nodes carry the CURRENT item context through the loop; unsupported/invalid attachments cannot inherit an earlier result. Cache condition matches the current Gemini configuration. Uncached requests wait 65 seconds; the backend enforces its own rate limit.','width':2200,'height':180},1)['position']=[0,210]
node('Notification Notes','stickyNote',{'content':'## Local notification and outcomes\nMailpit SMTP only. Notification claims/results are independent from review tasks; sent/sending/unknown are not resent automatically. Email outcomes return to the attachment loop; upload results return to the form. No approval, rejection, export or payment. Export is inactive; credential references must be rebound on another instance.','width':2200,'height':170},1)['position']=[0,630]
# All node IDs/webhook IDs belong to this new version.
for n in w['nodes']:
 n['id']=str(uuid.uuid4())
 if 'webhookId' in n:n['webhookId']=str(uuid.uuid4())
names={n['name'] for n in w['nodes']}
assert len(names)==len(w['nodes'])
assert all(a in names and all(e['node'] in names for out in c['main'] for e in out) for a,c in w['connections'].items())
assert not any(n['type']=='n8n-nodes-base.executeWorkflow' for n in w['nodes'])
(root/'01_AP_unified_intake_v5.json').write_text(json.dumps(w,indent=2)+'\n')
print(len(w['nodes']),'nodes; JSON/connections valid; all processing inline')

