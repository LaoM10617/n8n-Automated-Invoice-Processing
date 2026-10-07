"""Run the retained Python Agent on the same new sample pages, without changing invoice history.

Execute inside python-api after the native sample batch has finished. Only the
shared provider cooldown is updated in the business DB. Results are separate.
"""
import json
from pathlib import Path
import sqlite3
from backend.invoice_agent import extract_fields, trace_sink
from backend.model_gate import ModelGate, current_gate
from backend.extraction import grounded_fields
from backend.validation import validate
from backend.document_text import ProcessingError

DEST=Path('/data/ap/evaluations/native-b3/python_comparison.json')


def connect():
    db=sqlite3.connect('/data/ap/invoices.sqlite3'); db.row_factory=sqlite3.Row
    return db


def main():
    if DEST.exists(): raise SystemExit('Comparison already exists; inspect it instead of rerunning paid calls.')
    DEST.parent.mkdir(parents=True,exist_ok=True)
    with connect() as db:
        all_attempts=[dict(r) for r in db.execute('SELECT attempt_id,status,result_json FROM processing_attempts WHERE attempt_id>98')]
        samples=[r for r in all_attempts if r['status']=='processed']
    assert len(samples)==3 and all(json.loads(r['result_json']).get('raw_extraction') for r in samples)
    native_calls=sum(len(json.loads(r['result_json'])['agent_trace']['model_calls']) for r in all_attempts)
    report={'native_requests_before_comparison':native_calls,'total_request_budget':18,'python_requests':0,'samples':[]}
    def save(): DEST.write_text(json.dumps(report,indent=2)+'\n')
    class BudgetGate(ModelGate):
        def reserve(self,interval):
            if native_calls+report['python_requests']>=18:
                raise ProcessingError('EVALUATION_BUDGET','Comparison budget exhausted; no request sent.')
            super().reserve(interval)
            report['python_requests']+=1; save()
    gate_token=current_gate.set(BudgetGate(connect))
    try:
        for sample in samples:
            native=json.loads(sample['result_json'])
            record={'native_attempt_id':sample['attempt_id']}; report['samples'].append(record)
            def trace(value): record['agent_trace']=value;save()
            token=trace_sink.set(trace)
            try:
                raw=extract_fields(native['pages'])
                grounded,evidence_issues=grounded_fields(raw,native['pages'])
                fields,issues,arithmetic=validate(grounded)
                record.update(raw_extraction=raw,fields=fields,validation_issues=issues+evidence_issues,arithmetic_check=arithmetic,status='completed')
            except ProcessingError as exc: record.update(status='failed',error_code=exc.code)
            finally: trace_sink.reset(token);save()
            print(json.dumps({'attempt':sample['attempt_id'],'comparison':record['status'],'python_requests':report['python_requests']}),flush=True)
    finally: current_gate.reset(gate_token)


if __name__=='__main__': main()
