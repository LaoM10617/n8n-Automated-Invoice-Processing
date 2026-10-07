// Offline evaluation with the instance's own expression implementation.
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const root='/usr/local/lib/node_modules/n8n/node_modules/.pnpm';
const dir=fs.readdirSync(root).find(n=>n.startsWith('n8n-workflow@'));
const {Expression}=require(path.join(root,dir,'node_modules/n8n-workflow'));
const evaluator=new Expression('Europe/Berlin');
const data={$json:{scope:'offline-current-document'},$:()=>({last:()=>({json:{scope:'offline-current-document'}})}),$fromAI:(key)=>({page_numbers:[1,2],query:'Invoice',include_quality:true})[key],JSON};
const cases=[['page_numbers','json'],['query','string'],['include_quality','boolean']];
for(const [key,type] of cases){
 const expression='{{ JSON.stringify({scope: $json.scope, arguments:{'+key+': $fromAI("'+key+'", "Offline test", "'+type+'")} }) }}';
 const result=evaluator.renderExpression(expression,{...data});
 assert.equal(JSON.parse(result).scope,'offline-current-document');
 assert.deepEqual(JSON.parse(result).arguments[key],data.$fromAI(key));
}
console.log(JSON.stringify({expressions:3,passed:true,provider_requests:0}));
