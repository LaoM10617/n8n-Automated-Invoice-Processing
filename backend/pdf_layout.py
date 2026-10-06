"""Invoice geometry adapted from SITECO's pdf_layout.py whitespace/SourceSpan design.

Coordinates are top-left x/y/width/height in page points or image pixels.
No brochure headings, RAG chunks, supplier names or fixed crop coordinates are used.
"""

from statistics import median


def bounds(tokens):
    x = min(t['bbox'][0] for t in tokens)
    y = min(t['bbox'][1] for t in tokens)
    return [x, y, max(t['bbox'][0] + t['bbox'][2] for t in tokens) - x,
            max(t['bbox'][1] + t['bbox'][3] for t in tokens) - y]


def organize(tokens):
    """Keep physical rows and split large horizontal gaps before building blocks."""
    if not tokens:
        return {'text': '', 'lines': [], 'blocks': [], 'layout_uncertain': False}
    height = median(t['bbox'][3] for t in tokens)
    rows = []
    for index in sorted(range(len(tokens)), key=lambda i: (tokens[i]['bbox'][1], tokens[i]['bbox'][0])):
        box = tokens[index]['bbox']
        center = box[1] + box[3] / 2
        row = next((r for r in reversed(rows) if abs(r['center'] - center) <= .45 * height), None)
        if row is None:
            row = {'center': center, 'ids': []}
            rows.append(row)
        row['ids'].append(index)
    lines, blocks = [], []
    for row_index, row in enumerate(rows):
        ids = sorted(row['ids'], key=lambda i: tokens[i]['bbox'][0])
        segments = [[]]
        for index in ids:
            if segments[-1]:
                previous = tokens[segments[-1][-1]]['bbox']
                if tokens[index]['bbox'][0] - previous[0] - previous[2] > 2.5 * height:
                    segments.append([])
            segments[-1].append(index)
        for segment in segments:
            box = bounds([tokens[i] for i in segment])
            line = {'id': len(lines), 'row_id': row_index, 'bbox': box,
                    'token_ids': segment, 'text': ' '.join(tokens[i]['text'] for i in segment)}
            lines.append(line)
            # Match only nearby aligned fragments; never join the other column.
            candidates = []
            for block in blocks:
                last = lines[block['line_ids'][-1]]
                prior = last['bbox']
                gap = box[1] - prior[1] - prior[3]
                if last['row_id'] < row_index and -.2 * height <= gap <= 1.6 * height and abs(box[0] - prior[0]) <= 1.5 * height:
                    candidates.append(block)
            block = min(candidates, key=lambda b: abs(box[0] - lines[b['line_ids'][-1]]['bbox'][0])) if candidates else None
            if block is None:
                block = {'id': len(blocks), 'line_ids': [], 'kind': 'text_region'}
                blocks.append(block)
            block['line_ids'].append(line['id'])
            line['block_id'] = block['id']
            for index in segment:
                tokens[index].update(line_id=line['id'], row_id=row_index, block_id=block['id'])
    for block in blocks:
        selected = [lines[i] for i in block['line_ids']]
        block['bbox'] = bounds(selected)
        block['text'] = '\n'.join(line['text'] for line in selected)
    ordered = sorted(blocks, key=lambda b: (b['bbox'][1], b['bbox'][0]))
    # Row IDs preserve table associations even when readable text is column ordered.
    return {'text': '\n\n'.join(b['text'] for b in ordered), 'lines': lines, 'blocks': blocks,
            'layout_uncertain': any(sum(l['row_id'] == i for l in lines) >= 3 for i in range(len(rows)))}
