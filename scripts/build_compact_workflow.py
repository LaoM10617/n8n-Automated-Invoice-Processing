"""Build the compact deterministic canvas; v5 is preserved verbatim."""
import copy,json,uuid
from pathlib import Path
root=Path('n8n_workflows')
v5=json.loads((root/'01_AP_unified_intake_v5.json').read_text())
nodes={n['name']:n for n in v5['nodes']}
w={'id':'APCompactIntakeV6','name':'01_AP_Compact_Intake_v6','nodes':[],'connections':{},'settings':{'executionOrder':'v1','timezone':'Europe/Berlin','saveDataSuccessExecution':'all','saveDataErrorExecution':'all'},'active':False,'pinData':{}}
def add(name,typ,p,pos,ver=2):
 n={'name':name,'id':str(uuid.uuid4()),'type':'n8n-nodes-base.'+typ,'typeVersion':ver,'position':pos,'parameters':p};w['nodes'].append(n);return n
def clone(old,name,pos):
 n=copy.deepcopy(nodes[old]);n.update(name=name,id=str(uuid.uuid4()),position=pos)
 if 'webhookId' in n:n['webhookId']=str(uuid.uuid4())
 w['nodes'].append(n);return n
def link(a,b,port=0):
 outs=w['connections'].setdefault(a,{'main':[]})['main']
 while len(outs)<=port:outs.append([])
 outs[port]=[{'node':b,'type':'main','index':0}]
clone('Run Controlled Batch','Run Gmail Batch',[0,200]);clone('Get many messages','Gmail',[240,200])
u=clone('Upload Invoice','Upload Invoice',[240,-30]);u['parameters']['path']='ap-compact-intake-v6';u['parameters']['formDescription']='Compact AP intake. Existing extractor; no agent yet. Review stays read-only. Reuse Upload ID to retry.'
prepare=nodes['Split Email Attachments']['parameters']['jsCode']
prepare=prepare.replace(" const j=item.json;", """ const j=item.json;
 if (j['Upload ID'] !== undefined) {
  const keys=Object.keys(item.binary || {}), source=String(j['Upload ID']).trim();
  if (keys.length!==1 || !source || source.length>200) throw new Error('One file and a valid Upload ID are required.');
  results.push({json:{source_type:'upload',source_namespace:'n8n-ap-upload-v1',source_id:source,attachment_id:'0'},binary:{data:item.binary[keys[0]]},pairedItem:{item:i}});continue;
 }
""")
prepare=prepare.replace("...(b?{binary:{data:b}}:{})", "binary:{data:b || {data:'',mimeType:'application/x-ap-no-attachment',fileName:'no-attachment'}}")
prepare=prepare.replace(",supported,skip_reason:b?'UNSUPPORTED_ATTACHMENT':'NO_ATTACHMENTS'",'')
add('Prepare Attachments','code',{'jsCode':prepare},[480,140]);clone('One Attachment at a Time','Process Each Invoice',[720,140]);clone('Batch Finished','Batch Complete',[720,-50])
options={'timeout':180000}
add('Archive & Read Document','httpRequest',{'method':'POST','url':'http://python-api:8000/api/ap/stages/archive','sendBody':True,'contentType':'multipart-form-data','bodyParameters':{'parameters':[{'name':'metadata','value':'={{ JSON.stringify($json) }}'},{'parameterType':'formBinaryData','name':'file','inputDataFieldName':'data'}]},'options':options},[960,140],4.2)
for name,action,pos in [('Extract Invoice Fields','analyze',[1200,140]),('Validate & Save Result','validate',[1440,140]),('Notify Reviewer','notify',[1920,60]),('Record Exception','exception',[1920,270])]:
 add(name,'httpRequest',{'method':'POST','url':"={{ 'http://python-api:8000/api/ap/stages/' + $json.run_id + '/"+action+"' }}",'options':options},pos,4.2)
route=copy.deepcopy(nodes['Email Result']['parameters']);route['conditions']['conditions'][0]['leftValue']="={{ $json.outcome === 'review_ready' }}"
add('Route Outcome','if',route,[1680,140],2.3)
r=copy.deepcopy(route);r['conditions']['conditions'][0]['leftValue']="={{ $json.source.source_type === 'email' }}"
add('Return or Continue','if',r,[2160,140],2.3)
add('Upload Result','respondToWebhook',{'respondWith':'json','responseBody':"={{ {...$json, formSubmittedText: $json.outcome === 'review_ready' ? 'Review pending: ' + $json.review_url + '. Notification: ' + $json.notification_status : 'Result: ' + $json.outcome + '. ' + $json.error_code} }}",'options':{}},[2400,240],1.4)
for a,b in [('Run Gmail Batch','Gmail'),('Gmail','Prepare Attachments'),('Upload Invoice','Prepare Attachments'),('Prepare Attachments','Process Each Invoice'),('Process Each Invoice','Batch Complete'),('Archive & Read Document','Extract Invoice Fields'),('Extract Invoice Fields','Validate & Save Result'),('Validate & Save Result','Route Outcome'),('Route Outcome','Notify Reviewer'),('Notify Reviewer','Return or Continue'),('Record Exception','Return or Continue'),('Return or Continue','Process Each Invoice')]:link(a,b)
link('Process Each Invoice','Archive & Read Document',1);link('Route Outcome','Record Exception',1);link('Return or Continue','Upload Result',1)
add('Business Overview','stickyNote',{'content':'## PHASE 01 | Compact deterministic workflow\nUpload or run the readonly Gmail test batch. All business stages are inline. Python owns source isolation, originals/OCR, extraction cache and cooldown, validation, review tasks and notification delivery. Historical v5 is preserved.','width':2500,'height':180},[0,-280],1)
add('Current Scope','stickyNote',{'content':'## Current extractor, NOT an agent\nExtract Invoice Fields uses the existing Gemini structured extractor. LangChain Agent is a future step. Backend stage results share a persisted run_id contract; failed/skipped stages pass through without model calls. Failures are recorded immediately, before Record Exception.\n\nNotify Reviewer sends only to local Mailpit. Sent/unknown/in-flight notifications are not resent automatically. No approval, rejection, export, mailbox deletion or external sending. Export is inactive; bind the existing Gmail readonly credential after import on another instance.','width':2500,'height':230},[0,490],1)
assert all(a!=e['node'] for a,c in w['connections'].items() for o in c['main'] for e in o)
(root/'01_AP_compact_intake_v6.json').write_text(json.dumps(w,indent=2)+'\n',encoding='utf-8')
print(len(w['nodes']),'nodes including notes')
