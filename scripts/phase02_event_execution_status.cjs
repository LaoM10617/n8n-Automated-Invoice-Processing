// Read metadata only. Execution payload persistence is disabled for this receiver.
const sqlite3 = require('/usr/local/lib/node_modules/n8n/node_modules/.pnpm/sqlite3@5.1.7_bluebird@3.7.2_supports-color@8.1.1/node_modules/sqlite3');
const db = new sqlite3.Database('/home/node/.n8n/database.sqlite', sqlite3.OPEN_READONLY);
db.all('SELECT id,status,mode,startedAt,stoppedAt,deletedAt FROM execution_entity WHERE workflowId=? ORDER BY id', ['APReviewEventsV1'], (error, rows) => {
  if (error) { console.error(error.message); process.exitCode = 1; }
  else console.log(JSON.stringify({executions: rows}));
});
db.get('SELECT active,activeVersionId,settings FROM workflow_entity WHERE id=?', ['APReviewEventsV1'], (error, row) => {
  if (error) { console.error(error.message); process.exitCode = 1; }
  else console.log(JSON.stringify({workflow: row}));
});
db.close();
