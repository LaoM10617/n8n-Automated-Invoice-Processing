// Actual installed n8n Agent sequence, with in-memory tools and fake provider transport.
const fs=require('node:fs'), path=require('node:path'), assert=require('node:assert/strict');
const {createRequire}=require('node:module');
const root='/usr/local/lib/node_modules/n8n/node_modules/.pnpm';
const dir=fs.readdirSync(root).find(n=>n.startsWith('@n8n+n8n-nodes-langchain@'));
const base=path.join(root,dir,'node_modules/@n8n/n8n-nodes-langchain');
const req=createRequire(path.join(base,'package.json'));
const {ChatGoogleGenerativeAI}=req('@langchain/google-genai');
const {DynamicStructuredTool}=req('@langchain/core/tools');
const {z}=req('zod');
const {prepareMessages,preparePrompt}=req(path.join(base,'dist/nodes/agents/Agent/agents/ToolsAgent/common.js'));
const {createAgentSequence}=req(path.join(base,'dist/nodes/agents/Agent/agents/ToolsAgent/V3/helpers/createAgentSequence.js'));
const calls=[];
const system='AP_NATIVE_SCOPE:offline\nReturn JSON with missing values null.';
global.fetch=async(url,init)=>{
 const request=new Request(url,init); const body=await request.json();
 assert.ok(new URL(request.url).pathname.endsWith(':generateContent'));
 assert.equal(body.systemInstruction.parts[0].text,system);
 calls.push(body);
 const parts=calls.length===1 ? [{functionCall:{name:'Read_Invoice_Page',args:{page_numbers:[1]}}}] : [{text:'{"missing":null}'}];
 return new Response(JSON.stringify({candidates:[{content:{role:'model',parts},finishReason:'STOP'}],usageMetadata:{totalTokenCount:1}}),{status:200,headers:{'Content-Type':'application/json'}});
};
async function main(){
 const model=new ChatGoogleGenerativeAI({model:'models/gemini-3.5-flash-lite',apiKey:'offline-only',baseUrl:'http://python-api:8000/api/ap/native/gemini',maxRetries:0});
 const read=new DynamicStructuredTool({name:'Read_Invoice_Page',description:'Read the current invoice.',schema:z.object({page_numbers:z.array(z.number())}),func:async()=>JSON.stringify({pages:[{page:1,text:'Offline invoice only'}]})});
 const messages=await prepareMessages({getNode:()=>({typeVersion:3.1}),getInputData:()=>[{json:{}}]},0,{systemMessage:system,passthroughBinaryImages:false,passthroughBinaryPdfs:false,model});
 const sequence=createAgentSequence(model,[read],preparePrompt(messages),{},undefined,undefined,undefined,false);
 const input={system_message:system,input:'Read pages [1].',chat_history:[],steps:[]};
 const actions=await sequence.invoke(input);
 assert.equal(actions[0].tool,'Read_Invoice_Page');
 const observation=await read.invoke(actions[0].toolInput);
 const result=await sequence.invoke({...input,steps:[{action:actions[0],observation}]});
 assert.equal(JSON.parse(result.returnValues.output).missing,null);
 assert.equal(calls.length,2);
 console.log(JSON.stringify({provider_requests:0,installed_native_sequence:true,fake_model_requests:2,tool_calls:1,non_streaming:true,system_scope_preserved:true,nullable_output:true,limits:'Not an n8n engine, credential or real Google quality test.'},null,2));
}
main().catch(e=>{console.error(e.stack);process.exitCode=1;});
