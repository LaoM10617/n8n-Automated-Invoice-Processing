"""Generate traceable MIME fixtures and test local SMTP independently of processing.

External delivery is deliberately a separate operator step; this tool sends only
to loopback Mailpit. Generated EML files can be used by an authorized mail client.
"""
import argparse
from email import policy
from email.message import EmailMessage
from email.parser import BytesParser
from email.utils import formatdate
import hashlib
import json
from pathlib import Path
import re
import smtplib
import sqlite3
import time

import httpx

ROOT = Path(__file__).resolve().parents[1]


def cases():
    text = ROOT / 'test_data/first_round/text_pdf'
    ocr = ROOT / 'test_data/first_round/ocr'
    a = text / '04_invoice_A_business_duplicate.pdf'
    return [
        ('single', [a]),
        ('multi', [a, ocr / 'invoice_ocr (11).pdf']),
        ('same-file-new-mail', [a]),
        ('no-attachments', []),
        ('unsupported', ['notes.txt']),
        ('invalid-pdf', ['broken.pdf']),
        ('mixed', ['broken.pdf', a, 'notes.txt']),
        ('business-duplicate', [text / '01_invoice_A.pdf']),
        ('amount-mismatch', [text / '05_invoice_C_amount_mismatch.pdf']),
    ]


def generate(batch, limit, profile='scenarios'):
    folder = ROOT / 'data/email_batches' / batch
    folder.mkdir(parents=True, exist_ok=False)
    manifest = {'batch_id': batch, 'synthetic': True, 'transport': 'not_sent', 'messages': []}
    selected = cases()[:limit] if profile == 'scenarios' else [(f'throughput-{i:03}', cases()[0][1]) for i in range(limit)]
    for case, attachments in selected:
        msg = EmailMessage()
        msg['From'] = 'invoice-fixtures@example.invalid'
        msg['To'] = 'ap-inbox@example.invalid'
        msg['Subject'] = f'[AP-DEMO][{batch}][{case}]'
        msg['Message-ID'] = f'<{batch}.{case}@ap-demo.invalid>'
        msg['Date'] = formatdate(localtime=False, usegmt=True)
        msg.set_content('Synthetic AP integration fixture. Keep all source messages for reconciliation.')
        records = []
        for index, attachment in enumerate(attachments):
            data = attachment.read_bytes() if isinstance(attachment, Path) else b'Intentional invalid attachment for testing.'
            filename = attachment.name if isinstance(attachment, Path) else attachment
            mime = 'application/pdf' if filename.endswith('.pdf') else 'text/plain'
            main, sub = mime.split('/')
            msg.add_attachment(data, maintype=main, subtype=sub, filename=filename)
            records.append({'attachment_id': f'attachment_{index}', 'filename': filename,
                            'sha256': hashlib.sha256(data).hexdigest(),
                            'expected': 'rejected' if filename == 'broken.pdf' else 'skipped' if mime == 'text/plain' else 'review_ready'})
        filename = case + '.eml'
        (folder / filename).write_bytes(msg.as_bytes(policy=policy.SMTP))
        manifest['messages'].append({'case_id': case, 'eml': filename, 'smtp_message_id': msg['Message-ID'],
                                     'provider_message_id': None, 'attachments': records, 'send_status': 'not_sent'})
    (folder / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    return folder


def send_local(folder):
    path = folder / 'manifest.json'
    manifest = json.loads(path.read_text(encoding='utf-8'))
    started = time.monotonic()
    with smtplib.SMTP('127.0.0.1', 1025, timeout=15) as smtp:
        for message in manifest['messages']:
            if message['send_status'] == 'accepted':
                continue
            smtp.sendmail('invoice-fixtures@example.invalid', ['ap-inbox@example.invalid'], (folder / message['eml']).read_bytes())
            message['send_status'] = 'accepted'
            path.write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    manifest['transport'] = 'local_mailpit_smtp'
    manifest['send_seconds'] = round(time.monotonic() - started, 3)
    path.write_text(json.dumps(manifest, indent=2), encoding='utf-8')


def process_local(folder):
    path = folder / 'manifest.json'
    manifest = json.loads(path.read_text(encoding='utf-8'))
    if manifest['transport'] != 'local_mailpit_smtp' or any(m['send_status'] != 'accepted' for m in manifest['messages']):
        raise RuntimeError('Finish send-local before process-local; sending and processing must not run concurrently.')
    started = time.monotonic()
    with sqlite3.connect(f'file:{ROOT / "data/ap/invoices.sqlite3"}?mode=ro', uri=True) as db:
        attempts_before = db.execute('SELECT COUNT(*) FROM processing_attempts').fetchone()[0]
    outcomes = []
    with httpx.Client(timeout=240) as client:
        messages = client.get('http://127.0.0.1:8025/api/v1/messages', params={'limit':1000}).json()['messages']
        for message in manifest['messages']:
            matches = [m for m in messages if m['MessageID'].strip('<>') == message['smtp_message_id'].strip('<>')]
            if len(matches) != 1:
                raise RuntimeError(f"Expected one retained message for {message['case_id']}; found {len(matches)}")
            message['provider_message_id'] = matches[0]['ID']
            response = client.get('http://127.0.0.1:8025/api/v1/message/' + matches[0]['ID'] + '/raw')
            response.raise_for_status()
            mime = BytesParser(policy=policy.default).parsebytes(response.content)
            parts = list(mime.iter_attachments())
            for index, part in enumerate(parts or [None]):
                supported = part is not None and part.get_content_type() in ('application/pdf','image/jpeg','image/png')
                data = {'source_namespace':'mailpit:ap-test-inbox','source_id':matches[0]['ID'],
                        'attachment_id':f'attachment_{index}' if part else 'none', 'batch_id':manifest['batch_id'],
                        'case_id':message['case_id'],'supported':str(supported).lower(),
                        'skip_reason':'UNSUPPORTED_ATTACHMENT' if part else 'NO_ATTACHMENTS'}
                files = {'data':(part.get_filename(),part.get_payload(decode=True),part.get_content_type())} if part else None
                result = client.post('http://127.0.0.1:5678/webhook/ap-local-email-attachment', data=data, files=files)
                result.raise_for_status()
                outcome = result.json()
                if not outcome.get('status'):
                    raise RuntimeError('Workflow did not return a persisted attachment outcome.')
                outcomes.append(outcome)
                print(message['case_id'], data['attachment_id'], outcome['status'], flush=True)
                path.write_text(json.dumps(manifest, indent=2), encoding='utf-8')
        reconciliation = client.get('http://127.0.0.1:8000/api/ap/email-batches/' + manifest['batch_id']).json()
    reconciliation['processing_seconds'] = round(time.monotonic() - started, 3)
    with sqlite3.connect(f'file:{ROOT / "data/ap/invoices.sqlite3"}?mode=ro', uri=True) as db:
        reconciliation['processing_attempts_created'] = db.execute('SELECT COUNT(*) FROM processing_attempts').fetchone()[0] - attempts_before
    reconciliation['send_seconds'] = manifest.get('send_seconds')
    reconciliation['transport'] = 'local_mailpit_smtp_not_gmail'
    reconciliation['smtp_messages_sent'] = sum(m['send_status'] == 'accepted' for m in manifest['messages'])
    reconciliation['expected_valid_attachments'] = sum(a['expected'] == 'review_ready' for m in manifest['messages'] for a in m['attachments'])
    reconciliation['expected_rejected_attachments'] = sum(a['expected'] == 'rejected' for m in manifest['messages'] for a in m['attachments'])
    output = ROOT / 'logs&architechture' / (manifest['batch_id'] + '_verification.json')
    previous = json.loads(output.read_text(encoding='utf-8')) if output.exists() else {}
    reconciliation['previous_runs'] = previous.get('previous_runs', []) + ([{k:v for k,v in previous.items() if k != 'previous_runs'}] if previous else [])
    expected_skipped = sum(not m['attachments'] for m in manifest['messages']) + sum(a['expected'] == 'skipped' for m in manifest['messages'] for a in m['attachments'])
    reconciliation['counts_match'] = (reconciliation['receipts'] == reconciliation['expected_valid_attachments']
                                      and reconciliation['failed_items'] == reconciliation['expected_rejected_attachments']
                                      and reconciliation['skipped_items'] == expected_skipped
                                      and reconciliation['messages'] == len(manifest['messages']))
    output.write_text(json.dumps(reconciliation, indent=2), encoding='utf-8')
    if not reconciliation['counts_match']:
        raise RuntimeError('Batch reconciliation mismatch; inspect the saved report.')
    print('Reconciliation:', output)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['generate','send-local','process-local'])
    parser.add_argument('--batch', required=True)
    parser.add_argument('--limit', type=int, default=2, choices=range(1,101))
    parser.add_argument('--profile', choices=['scenarios','throughput'], default='scenarios')
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', args.batch):
        parser.error('Batch ID must contain only letters, digits, underscores and hyphens.')
    folder = ROOT / 'data/email_batches' / args.batch
    if args.action == 'generate':
        print(generate(args.batch, args.limit, args.profile))
    elif args.action == 'send-local':
        send_local(folder)
    else:
        process_local(folder)
