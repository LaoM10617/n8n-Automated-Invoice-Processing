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
