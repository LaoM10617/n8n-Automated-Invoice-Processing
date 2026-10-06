"""Offline reader benchmark; never calls an LLM or loads API credentials."""
import json
from pathlib import Path
import time
from backend.document_text import read_pages

root = Path('/samples')
results = []
for path in sorted(root.rglob('*.pdf')):
    start = time.monotonic()
    pages = read_pages(path, 'application/pdf')
    results.append({'file': str(path.relative_to(root)), 'seconds': round(time.monotonic()-start, 3), 'pages': pages})
    print(str(path.relative_to(root)), [(p['method'], p['image_strategy']) for p in pages], flush=True)
Path('/results/local_layout_results.json').write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
