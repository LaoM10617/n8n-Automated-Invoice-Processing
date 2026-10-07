// n8n 2.42.3 retains initial webhook data even when execution saving is disabled.
// Keep the credential readable by Header Auth, but exclude it from serialized headers.
function protectReviewHeader(req) {
  const path = (req.url || '').split('?')[0];
  if (!['ap-review-events-v1', 'ap-review-export-v1', 'ap-batch-export-v1', 'ap-unified-review-a2-v1', 'ap-unified-excel-a2-v1', 'ap-native-review-b2-v2', 'ap-native-excel-b2-v2'].some(name => ['/webhook/' + name, '/webhook-test/' + name].includes(path))) return;
  const name = 'x-ap-event-token';
  const value = req.headers[name];
  if (value !== undefined) {
    Object.defineProperty(req.headers, name, {value, enumerable: false, configurable: true, writable: true});
    for (let i = 0; i < req.rawHeaders.length; i += 2) {
      if (req.rawHeaders[i].toLowerCase() === name) req.rawHeaders[i + 1] = '[REDACTED]';
    }
  }
}

module.exports = {n8n: {ready: [async function(instance) {
  instance.server.prependListener('request', protectReviewHeader);
}]}};
