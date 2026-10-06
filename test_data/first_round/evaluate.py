"""Evaluate the API against reviewed fixtures; never used by the backend."""

import argparse
from datetime import datetime, timezone
from decimal import Decimal
import json
from pathlib import Path
import time

import httpx


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--process', action='store_true', help='Upload and invoke real processing; may call the configured paid model.')
    parser.add_argument('--limit', type=int, default=1, help='Maximum documents; default 1. Use 16 explicitly for the full set.')
    parser.add_argument('--interval', type=float, default=65, help='Seconds between documents; default 65.')
    args = parser.parse_args()
    if args.limit < 1 or args.interval < 60:
        parser.error('Use a positive limit and an interval of at least 60 seconds.')
    root = Path(__file__).resolve().parent
    report_path = root.parents[1] / 'logs&architechture/step_04_field_evaluation_latest.json'
    expected = json.loads((root / 'expected_fields.json').read_text(encoding='utf-8'))['cases']
    results = []
    with httpx.Client(base_url='http://127.0.0.1:8000', trust_env=False, timeout=180) as client:
        for case in expected[:args.limit]:
            path = root / case['file']
            if not args.process:
                continue
            if results:
                time.sleep(args.interval)
            response = client.post('/api/ap/intakes', data={
                'source_type': 'upload', 'source_namespace': 'step4-field-evaluation',
                'source_id': case['file'], 'attachment_id': '0'},
                files={'file': (path.name, path.read_bytes(), 'application/pdf')})
            response.raise_for_status()
            invoice_id = response.json()['invoice_id']
            processed = client.post(f'/api/ap/invoices/{invoice_id}/process')
            results.append({'file': case['file'], 'invoice_id': invoice_id, 'process_http_status': processed.status_code})
            print(case['file'], processed.status_code, flush=True)
            if processed.status_code == 429:
                print('Rate limit reached; stopping without retry or provider fallback.', flush=True)
                break
        for result, case in zip(results, expected):
            response = client.get(f"/api/ap/invoices/{result['invoice_id']}")
            response.raise_for_status()
            actual = response.json()
            fields = actual.get('extracted_fields')
            result['processing_status'] = actual['processing_status']
            result['processing_error'] = actual['processing_error']
            result['business_duplicate_status'] = actual['business_duplicate_status']
            result['comparisons'] = []
            if fields is None:
                continue
            for field, value in case['expected_fields'].items():
                observed = fields.get(field)
                if field.endswith('_amount') and value is not None and observed is not None:
                    same = Decimal(value) == Decimal(observed)
                else:
                    same = value == observed
                result['comparisons'].append({'field': field, 'expected': value, 'actual': observed, 'match': same})
            codes = {i['code'] for i in actual['validation_issues']}
            result['missing_expected_issue_codes'] = sorted(set(case['expected_issue_codes']) - codes)
    if not args.process:
        parser.error('Use --process to explicitly run real extraction and potentially paid model calls.')
    comparisons = [c for r in results for c in r['comparisons']]
    report = {'checked_at': datetime.now(timezone.utc).isoformat(),
              'scope': 'First-round development fixtures only, not unseen-template accuracy. Strict field comparison; nulls counted explicitly.',
              'completed_documents': sum(r['processing_status'] == 'processed' for r in results),
              'total_documents': len(expected), 'matched_fields': sum(c['match'] for c in comparisons),
              'compared_fields': len(comparisons), 'cases': results}
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print('Report:', report_path)


if __name__ == '__main__':
    main()
