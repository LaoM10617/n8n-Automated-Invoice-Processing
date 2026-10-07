const assert = require('node:assert/strict');
const hook = require('./n8n_review_header_privacy.cjs');
let listener;
hook.n8n.ready[0]({server: {prependListener(event, callback) {
  assert.equal(event, 'request'); listener = callback;
}}});
const request = {url: '/webhook/ap-review-events-v1', headers: {'x-ap-event-token': 'test-secret'}, rawHeaders: ['X-AP-Event-Token', 'test-secret']};
listener(request);
assert.equal(request.headers['x-ap-event-token'], 'test-secret');
assert.equal(JSON.stringify(request).includes('test-secret'), false);
const unrelated = {url: '/webhook/other', headers: {'x-ap-event-token': 'unchanged'}, rawHeaders: []};
listener(unrelated);
assert.equal(JSON.stringify(unrelated).includes('unchanged'), true);
listener({url: '/webhook/ap-review-events-v1', headers: {}, rawHeaders: []});
console.log('Header authentication access, serialization privacy, missing token and path isolation passed.');

for (const path of ['/webhook/ap-review-export-v1', '/webhook-test/ap-review-export-v1', '/webhook/ap-batch-export-v1', '/webhook-test/ap-batch-export-v1']) {
 const req = {url:path,headers:{'x-ap-event-token':'new-secret'},rawHeaders:['X-AP-Event-Token','new-secret']};
 listener(req);
 assert.equal(req.headers['x-ap-event-token'],'new-secret');
 assert.equal(JSON.stringify(req).includes('new-secret'),false);
}
console.log('Both final outcome webhook paths passed.');

for (const name of ['ap-unified-review-a2-v1', 'ap-unified-excel-a2-v1', 'ap-native-review-b2-v2', 'ap-native-excel-b2-v2']) {
 for (const prefix of ['/webhook/', '/webhook-test/']) {
  const req = {url:prefix+name+'?probe=1',headers:{'x-ap-event-token':'unified-secret'},rawHeaders:['X-AP-Event-Token','unified-secret']};
  listener(req);
  assert.equal(req.headers['x-ap-event-token'],'unified-secret');
  assert.equal(JSON.stringify(req).includes('unified-secret'),false);
 }
}
console.log('Unified production and test paths preserve authentication without serializing the token.');
