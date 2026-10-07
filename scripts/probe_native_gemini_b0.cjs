// Offline probe against the packages installed in the n8n container.
// No credentials, provider requests, workflow execution or business writes.
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const { createRequire } = require('node:module');

const root = '/usr/local/lib/node_modules/n8n/node_modules/.pnpm';
const packageDirectory = fs.readdirSync(root).find(name => name.startsWith('@n8n+n8n-nodes-langchain@'));
const base = path.join(root, packageDirectory, 'node_modules/@n8n/n8n-nodes-langchain');
const localRequire = createRequire(path.join(base, 'package.json'));
const { ChatGoogleGenerativeAI } = localRequire('@langchain/google-genai');
const { LmChatGoogleGemini } = localRequire(path.join(base, 'dist/nodes/llms/LmChatGoogleGemini/LmChatGoogleGemini.node.js'));

async function main() {
  const node = new LmChatGoogleGemini();
  const model = new ChatGoogleGenerativeAI({
    apiKey: 'offline-probe-not-a-credential',
    model: 'gemini-3.5-flash-lite',
    baseUrl: 'http://127.0.0.1:1',
  });
  const starts = [];
  const fakeProvider = async () => { starts.push(performance.now()); return 'offline'; };
  await model.caller.call(fakeProvider);
  await model.caller.call(fakeProvider);
  assert.equal(starts.length, 2);
  assert.ok(starts[1] - starts[0] < 60000);
  const source = fs.readFileSync(path.join(base, 'dist/nodes/llms/LmChatGoogleGemini/LmChatGoogleGemini.node.js'), 'utf8');
  assert.ok(source.includes('baseUrl: credentials.host'));
  assert.ok(!source.includes('maxRetries:'));
  console.log(JSON.stringify({
    mode: 'offline-constructor-and-caller-probe',
    provider_requests: 0,
    versions: node.description.version,
    model: model.model,
    caller_max_retries: model.caller.maxRetries,
    fake_call_spacing_ms: starts[1] - starts[0],
    node_sets_max_retries: false,
    credential_host_forwarded: true,
    limitations: 'Does not validate Google acceptance, Agent execution, schema compatibility or proxy behavior.',
  }, null, 2));
}
main().catch(error => { console.error(error.message); process.exitCode = 1; });
