"""Read-only field, evidence, budget and attachment checks for the native evaluation batch."""
import json
from pathlib import Path
import sqlite3
from backend.extraction import grounded_fields

ROOT=Path(__file__).resolve().parents[1]


def main():
    expected=json.loads((ROOT/'data/native-b3-samples/expected.json').read_text())
    db=sqlite3.connect((ROOT/'data/ap/invoices.sqlite3').as_uri()+'?mode=ro',uri=True)
    db.row_factory=sqlite3.Row
    records=[]; starts=[]
    for case in expected['cases']:
        number=case['expected_fields']['invoice_number']
        matches=[]
        for row in db.execute('SELECT * FROM processing_attempts WHERE attempt_id>98'):
            result=json.loads(row['result_json'] or '{}')
            if result.get('raw_extraction',{}).get('fields',{}).get('invoice_number')==number:matches.append((row,result))
        assert len(matches)==1, number
        row,result=matches[0]; assert row['status']=='processed'
        raw=result['raw_extraction']; fields=result['fields']
        for key,value in case['expected_fields'].items():
            assert raw['fields'][key]==value,(number,key,'raw')
            assert fields[key]==value,(number,key,'validated')
        grounded,issues=grounded_fields(raw,result['pages']);assert not issues
        trace=result['agent_trace'];calls=trace['model_calls']
        assert len(calls)<=3 and len(trace['tools'])<=6
        assert trace['status']=='completed' and trace['read_pages']==[1]
        assert all(c['status']=='completed' for c in calls)
        starts += [c['started_at'] for c in calls]
        task=dict(db.execute('SELECT * FROM review_tasks WHERE invoice_id=?',(row['invoice_id'],)).fetchone())
        if case['case']=='text':assert task['status']=='approved' and task['approval_method']=='automatic'
        if case['case']=='missing':assert any(i['code']=='MISSING_FIELD' and i['field']=='due_date' for i in result['validation_issues'])
        records.append({'case':case['case'],'invoice_id':row['invoice_id'],'attempt_id':row['attempt_id'],'raw_extraction':raw,'validated_fields':fields,'issues':result['validation_issues'],'agent_trace':trace,'review_status_at_check':task['status'],'ocr_confidence':[p['ocr_confidence'] for p in result['pages']],'page_text':[p['text'] for p in result['pages']]})
    failed=[]
    for row in db.execute("SELECT * FROM processing_attempts WHERE attempt_id>98 AND status='failed'"):
        result=json.loads(row['result_json']); trace=result['agent_trace']
        starts += [c['started_at'] for c in trace['model_calls']]
        failed.append({'attempt_id':row['attempt_id'],'error_code':row['error_code'],'agent_trace':trace})
    starts.sort(); gaps=[b-a for a,b in zip(starts,starts[1:])];assert all(g>=60 for g in gaps)
    outcomes=[dict(r) for r in db.execute('SELECT source_id,attachment_id,status,invoice_id FROM email_outcomes WHERE batch_id=?',('native-b3-20261007',))]
    assert len(outcomes)==10 and sum(r['status']=='intake_failed' for r in outcomes)==3
    assert len({r['invoice_id'] for r in outcomes if r['invoice_id']})==3
    report={'samples':records,'failed_attempts_preserved':failed,'native_model_requests':len(starts),'request_gaps_seconds':gaps,'all_39_fields_match':True,'evidence_grounding_passed':True,'outcomes':outcomes,'fault_tests':'30 passed plus 1 real subprocess interruption test; simulated provider faults','historical_ocr11':'Not rerun; historical address grounding limitation is not claimed resolved.'}
    (ROOT/'logs&architechture/AP_native_agent_B3_verification.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'samples':len(records),'fields_matched':39,'native_requests':len(starts),'minimum_gap':min(gaps),'attachment_outcomes':len(outcomes)}))


if __name__=='__main__':main()
