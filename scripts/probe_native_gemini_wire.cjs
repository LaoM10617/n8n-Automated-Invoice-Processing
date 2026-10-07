// Exercise the installed Gemini serializer with an in-memory fake transport.
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const {createRequire} = require('node:module');
const root='/usr/local/lib/node_modules/n8n/node_modules/.pnpm';
const dir=fs.readdirSync(root).find(n=>n.startsWith('@n8n+n8n-nodes-langchain@'));
const req=createRequire(path.join(root,dir,'node_modules/@n8n/n8n-nodes-langchain/package.json'));
const {ChatGoogleGenerativeAI}=req('@langchain/google-genai');
const calls=[];
global.fetch=async (url,init)=>{
  const request=new Request(url,init);
  const body=await request.json();
  calls.push({path:new URL(request.url).pathname,body,headerPresent:request.headers.has('x-goog-api-key'),queryKey:new URL(request.url).searchParams.has('key')});
  return new Response(JSON.stringify({candidates:[{content:{role:'model',parts:[{text:'{"missing":null}'}]},finishReason:'STOP'}],usageMetadata:{totalTokenCount:1}}),{status:200,headers:{'Content-Type':'application/json'}});
};
async function main(){
  const model=new ChatGoogleGenerativeAI({model:'gemini-3.5-flash-lite',apiKey:'offline-only',baseUrl:'http://python-api:8000/api/ap/native/gemini',maxRetries:0});
  const bound=model.bindTools([{name:'Read_Invoice_Page',description:'Read current pages only.',schema:{type:'object',properties:{page_numbers:{type:'array',items:{type:'integer'}}},required:['page_numbers']}}]);
  const result=await bound.invoke([{role:'system',content:'AP_NATIVE_SCOPE:offline\nReturn JSON.'},{role:'user',content:'Pages: [1]'}]);
  assert.equal(calls.length,1);
  assert.equal(calls[0].path,'/api/ap/native/gemini/v1beta/models/gemini-3.5-flash-lite:generateContent');
  assert.ok(calls[0].headerPresent);
  assert.equal(calls[0].queryKey,false);
  assert.equal(calls[0].body.systemInstruction.parts[0].text,'AP_NATIVE_SCOPE:offline\nReturn JSON.');
  assert.equal(JSON.parse(result.content).missing,null);
  console.log(JSON.stringify({provider_requests:0,fake_transport_calls:calls.length,path:calls[0].path,body_keys:Object.keys(calls[0].body),auth_header:true,auth_query:false,nullable_text_preserved:true,tool_names:calls[0].body.tools.flatMap(t=>t.functionDeclarations.map(f=>f.name))},null,2));
}
main().catch(e=>{console.error(e.message);process.exitCode=1;});
