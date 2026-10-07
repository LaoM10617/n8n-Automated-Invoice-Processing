"""Provision a local-only header credential without printing or writing a JSON secret."""
import json
from pathlib import Path
import secrets
import subprocess

root = Path(__file__).resolve().parents[1]
env_path = root / '.env'
content = env_path.read_text(encoding='utf-8') if env_path.exists() else ''
token = next((line.split('=', 1)[1].strip() for line in content.splitlines() if line.startswith('AP_REVIEW_EVENT_TOKEN=')), '')
if not token:
    token = secrets.token_urlsafe(32)
    lines = [line for line in content.splitlines() if not line.startswith('AP_REVIEW_EVENT_TOKEN=')]
    env_path.write_text('\n'.join(lines) + '\nAP_REVIEW_EVENT_TOKEN=' + token + '\n', encoding='utf-8')
credentials = [{'id': 'APReviewEventLocalV1', 'name': 'AP review event local header',
                'type': 'httpHeaderAuth', 'data': {'name': 'X-AP-Event-Token', 'value': token}}]
# n8n imports from a private temporary file inside the container; always remove that file.
command = ['docker', 'compose', 'exec', '-T', 'n8n', 'sh', '-c',
           'umask 077; cat > /tmp/ap-review-event-credential.json; n8n import:credentials --input=/tmp/ap-review-event-credential.json; code=$?; rm -f /tmp/ap-review-event-credential.json; exit "$code"']
result = subprocess.run(command, cwd=root, input=json.dumps(credentials), text=True, capture_output=True)
if result.returncode:
    raise SystemExit('Local credential import failed. Inspect n8n configuration without printing credential data.')
print('Local header credential imported; token retained only in ignored .env and n8n credential storage.')
