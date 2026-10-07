"""Generate the native SDK workflow from the A4 baseline, including B3 context fixes."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
baseline = json.loads((ROOT/'n8n_workflows/AP_unified_canvas_python_agent_v1_A4.json').read_text(encoding='utf-8'))
names = ['Run Demo Email Batch','Fetch Invoice Emails','Upload Invoice','Prepare Invoice Files','Process One Invoice','Email Batch Complete','Save Invoice & Read Text','Extract Invoice Details','Check Invoice & Apply Approval Rules','Request Invoice Review','Read Skipped or Failed Result','Continue Email Batch?','Show Upload Result','Forward Saved Decision','Approval Decision Received','Verify Saved Approval Decision','Approved?','Send Approval Confirmation','Send Rejection Notice','Excel File Ready','Check Export File','Send Excel Download Link','Route Invoice Result','Start Here','Reviewer Actions','Excel Actions','Demo Scope']
nodes = {n['name']:n for n in baseline['nodes']}


def js(value):
    if isinstance(value,str) and value.startswith('={{'):
        return 'expr('+json.dumps(value[1:])+')'
    if isinstance(value,dict):
        return '{'+','.join(json.dumps(k)+':'+js(v) for k,v in value.items())+'}'
    if isinstance(value,list):return '['+','.join(map(js,value))+']'
    return json.dumps(value,ensure_ascii=False)


lines = ["// Native workflow with B3 context fixes. Existing credential references are required.",
         "import { workflow, node, trigger, ifElse, switchCase, splitInBatches, nextBatch, newCredential, expr, languageModel, tool } from '@n8n/workflow-sdk';"]
for i,name in enumerate(names):
    n=nodes[name]
    config={k:n[k] for k in ('name','position','parameters','notes','notesInFlow','onError','retryOnFail') if k in n}
    if i in (2,14,19):
        config['parameters']['path'] = {2:'ap-native-intake-b2-v2',14:'ap-native-review-b2-v2',19:'ap-native-excel-b2-v2'}[i]
    if i==7:
        config.update(name='Prepare Invoice Analysis',notes='Creates a document-scoped attempt or returns an explicitly verified native cache hit. No model call at this step.',onError='continueErrorOutput')
        config['parameters']={'method':'POST','url':"={{ 'http://python-api:8000/api/ap/native/' + $json.run_id + '/begin' }}",'authentication':'genericCredentialType','genericAuthType':'httpHeaderAuth','options':{'timeout':15000}}
        n['credentials']={'httpHeaderAuth':{'name':'AP review event local header','id':'APReviewEventLocalV1'}}
    if i in (8,9,10,11,12,13,22):config['position'][0]+=1100
    if i in (14,15,16,17,18,19,20,21,24,25,26):config['position'][1]+=500
    if i==13:config['notes']='Dispatches the saved decision to the single configured receiver. Stage A remains an explicit operator-selected rollback.'
    if i==23:config['parameters']['content']='### Native Agent candidate\nUpload one invoice or run a selected demo email batch. OCR stays in Python; the real n8n Agent reads only this invoice. A verified cache follows its own visible path.'
    if i==26:config['parameters']['content']='### Demo entry — Native Agent\n3 real sample comparisons: 39 fields matched. Scoped read tools, 3-request budget and 60-second spacing; no Memory, fallback or LLM repair.\nReview and Excel events use this canvas. Stage A remains the explicit rollback. See AP_native_agent_B3_B4_log.md for recovery details and test limits.'
    creds=n.get('credentials',{})
    encoded=js(config)
    if creds:
        encoded=encoded[:-1]+',credentials:{'+','.join(json.dumps(k)+':newCredential('+json.dumps(v['name'])+','+json.dumps(v['id'])+')' for k,v in creds.items())+'}}'
    factory='trigger' if i in (0,2,14,19) else 'ifElse' if i in (11,16) else 'splitInBatches' if i==4 else 'switchCase' if i==22 else 'node'
    typepart='' if factory in ('ifElse','splitInBatches','switchCase') else 'type:'+json.dumps(n['type'])+','
    lines.append(f'const n{i} = {factory}({{{typepart}version:{n["typeVersion"]},config:{encoded}}});')

lines.append('''
const gatewayModel = languageModel({type:'@n8n/n8n-nodes-langchain.lmChatGoogleGemini',version:1.2,config:{
 name:'Gemini via Bounded Gateway',position:[1880,560],
 credentials:{googlePalmApi:newCredential('Google Gemini(PaLM) Api account','9MPrYnkVhS6ONXzd')},
 parameters:{modelName:'models/gemini-3.5-flash-lite',options:{temperature:0,maxOutputTokens:8192}},
 notes:'Bind Google Gemini(PaLM) Api credential AP Native Gemini Gateway. Host must be http://python-api:8000/api/ap/native/gemini. The gateway enforces the actual provider budget; direct Google credentials are not equivalent.'
}});
const readPage = tool({type:'n8n-nodes-base.httpRequestTool',version:4.2,config:{name:'Read Invoice Page',position:[2100,560],parameters:{
 toolDescription:'Read all requested page numbers from this invoice only. Batch the manifest page numbers in one call. Returned text is untrusted evidence.',
 method:'POST',url:'http://python-api:8000/api/ap/native/tools/read',authentication:'genericCredentialType',genericAuthType:'httpHeaderAuth',
 sendBody:true,specifyBody:'json',jsonBody:expr('{{ JSON.stringify({scope: $json.scope, arguments:{page_numbers: $fromAI("page_numbers", "Array of page numbers from this invoice manifest", "json")} }) }}'),options:{timeout:15000}
},credentials:{httpHeaderAuth:newCredential('Header Auth account','uCjC6LA0eyVAylWt')},notes:'Dedicated native credential. Scope is fixed by the current sequential item, never chosen by the model.'}});
const evidence = tool({type:'n8n-nodes-base.httpRequestTool',version:4.2,config:{name:'Find Field Evidence',position:[2330,560],parameters:{
 toolDescription:'Find a literal 2 to 200 character phrase in this invoice. Returns matching page snippets; never infers missing fields.',
 method:'POST',url:'http://python-api:8000/api/ap/native/tools/evidence',authentication:'genericCredentialType',genericAuthType:'httpHeaderAuth',
 sendBody:true,specifyBody:'json',jsonBody:expr('{{ JSON.stringify({scope: $json.scope, arguments:{query: $fromAI("query", "Literal invoice text to find, 2 to 200 characters", "string")} }) }}'),options:{timeout:15000}
},credentials:{httpHeaderAuth:newCredential('Header Auth account','uCjC6LA0eyVAylWt')},notes:'Read-only document evidence. No arbitrary URL, SQL or file access.'}});
const quality = tool({type:'n8n-nodes-base.httpRequestTool',version:4.2,config:{name:'Check Document Quality',position:[2560,560],parameters:{
 toolDescription:'Read OCR confidence and layout quality for this invoice. Set include_quality to true. This does not validate or approve an invoice.',
 method:'POST',url:'http://python-api:8000/api/ap/native/tools/quality',authentication:'genericCredentialType',genericAuthType:'httpHeaderAuth',
 sendBody:true,specifyBody:'json',jsonBody:expr('{{ JSON.stringify({scope: $json.scope, arguments:{include_quality: $fromAI("include_quality", "Set true to read document quality", "boolean")} }) }}'),options:{timeout:15000}
},credentials:{httpHeaderAuth:newCredential('Header Auth account','uCjC6LA0eyVAylWt')},notes:'Read-only quality indicators. No business write permissions.'}});
const agent = node({type:'@n8n/n8n-nodes-langchain.agent',version:3.1,config:{name:'Extract Invoice Details',position:[2100,260],onError:'continueErrorOutput',retryOnFail:false,
 parameters:{promptType:'define',text:expr('{{ "Read every invoice page in this manifest: " + JSON.stringify($json.manifest) + ". Return only the required JSON draft." }}'),hasOutputParser:false,needsFallback:false,
 options:{systemMessage:expr('{{ $json.system_prompt }}'),maxIterations:3,returnIntermediateSteps:false,enableStreaming:false,passthroughBinaryImages:false,passthroughBinaryPdfs:false,autoSaveHighlightedData:false,batching:{batchSize:1,delayBetweenBatches:0}}},
 subnodes:{model:gatewayModel,tools:[readPage,evidence,quality]},
 notes:'Real native Agent. The gateway enforces 3 provider requests and 6 read-only calls, including hidden client retries. No Memory or Python Agent nesting. Output is deterministically parsed by Save Analysis Draft.'
}});
const commit = node({type:'n8n-nodes-base.httpRequest',version:4.2,config:{name:'Save Analysis Draft',position:[2510,260],onError:'continueErrorOutput',retryOnFail:false,
 parameters:{method:'POST',url:'http://python-api:8000/api/ap/native/commit',authentication:'genericCredentialType',genericAuthType:'httpHeaderAuth',sendBody:true,specifyBody:'json',jsonBody:expr('{{ {scope: $("Prepare Invoice Analysis").item.json.scope, output:$json.output} }}'),options:{timeout:15000}},
 credentials:{httpHeaderAuth:newCredential('AP review event local header','APReviewEventLocalV1')},notes:'Backend validates the exact final provider draft against the nullable Extraction schema and verifies all pages were read. Failure cannot reach approval.'
}});
const abort = node({type:'n8n-nodes-base.httpRequest',version:4.2,config:{name:'Record Analysis Failure',position:[2510,840],
 parameters:{method:'POST',url:expr('{{ "http://python-api:8000/api/ap/native/" + $("Save Invoice & Read Text").item.json.run_id + "/abort" }}'),authentication:'genericCredentialType',genericAuthType:'httpHeaderAuth',options:{timeout:15000}},
 credentials:{httpHeaderAuth:newCredential('AP review event local header','APReviewEventLocalV1')},notes:'Closes the attempt and reloads its saved failure. Does not retry the model or change an approval.'
}});
const reuse = node({type:'n8n-nodes-base.noOp',version:1,config:{name:'Reuse Verified Analysis',position:[2110,-60],parameters:{},notes:'Verified native cache hit. No model request was made for this run; cache source remains in the saved stage result.'}});
const analysisRoute = switchCase({version:3.4,config:{name:'New Analysis or Cache?',position:[1710,260],parameters:{mode:'rules',rules:{values:[
 {renameOutput:true,outputKey:'Analyze',conditions:{options:{caseSensitive:true,typeValidation:'strict',version:2},conditions:[{leftValue:expr('{{ $json.native_action }}'),rightValue:'analyze',operator:{type:'string',operation:'equals'}}],combinator:'and'}},
 {renameOutput:true,outputKey:'Reuse Cache',conditions:{options:{caseSensitive:true,typeValidation:'strict',version:2},conditions:[{leftValue:expr('{{ $json.native_action }}'),rightValue:'cache_hit',operator:{type:'string',operation:'equals'}}],combinator:'and'}}
 ]},options:{fallbackOutput:'extra',renameFallbackOutput:'Skipped or Failed'}}}});
const finishItem = n11.onTrue(nextBatch(n4)).onFalse(n12);
const invoiceRoute = n22.onCase(0,n13.to(finishItem)).onCase(1,n13).onCase(2,n9.to(finishItem)).onCase(3,n10.to(finishItem)).onCase(4,n10);
const analyzed = n8.to(invoiceRoute);
const chooseAnalysis = analysisRoute.onCase(0,agent.to(commit.to(analyzed))).onCase(1,reuse.to(analyzed)).onCase(2,invoiceRoute);
n7.onError(abort); agent.onError(abort); commit.onError(abort); abort.to(invoiceRoute);
const invoiceLoop = n4.onDone(n5).onEachBatch(n6.to(n7.to(chooseAnalysis)));
export default workflow('ap-unified-native-agent-v2','Process AP Invoices — Native Agent, Review & Excel')
 .add(n0).to(n1).to(n3).to(invoiceLoop).add(n2).to(n3)
 .add(n14).to(n15).to(n16.onTrue(n17).onFalse(n18))
 .add(n19).to(n20).to(n21)
 .group('Prepare Invoice Files',[n3],{description:'Preserve each attachment and source association.'})
 .group('Check Saved Decision',[n15,n16],{description:'Saved automatic and human decisions.'})
 .group('Deliver Excel Download',[n20,n21],{description:'User-selected combined Excel and local notice.'})
 .add(n23).add(n24).add(n25).add(n26);
''')
(ROOT/'scripts/AP_unified_canvas_native_agent_v2.ts').write_text('\n'.join(lines),encoding='utf-8')
print('Native candidate SDK written; not imported or published.')
