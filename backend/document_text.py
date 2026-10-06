"""Read saved originals only. No fixture annotations are accessible here."""

import csv
from contextlib import ExitStack
import io
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

from PIL import Image, ImageOps
from pypdf import PdfReader
import pdfplumber

from backend.pdf_layout import organize

QUALITY_VERSION = 'layout-quality-v3'


class ProcessingError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def usable_text(text):
    compact = ''.join(text.split())
    return (len(compact) >= 60 and len(re.findall(r'\b\w{2,}\b', text)) >= 12
            and sum(c.isalnum() for c in compact) / max(1, len(compact)) >= .6
            and '\ufffd' not in text and '\x00' not in text)


def run_tool(args):
    try:
        return subprocess.run(args, check=True, capture_output=True, timeout=90).stdout
    except FileNotFoundError as exc:
        raise ProcessingError('OCR_DEPENDENCY_MISSING', 'Required OCR or PDF rendering tool is unavailable.') from exc
    except subprocess.TimeoutExpired as exc:
        raise ProcessingError('OCR_TIMEOUT', 'OCR or PDF rendering exceeded 90 seconds.') from exc
    except subprocess.CalledProcessError as exc:
        raise ProcessingError('OCR_FAILED', 'OCR or PDF rendering failed.') from exc


def ocr_image(path):
    output = run_tool(['tesseract', str(path), 'stdout', '-l', 'eng+deu', '--psm', '3', 'tsv'])
    rows = csv.DictReader(io.StringIO(output.decode('utf-8')), delimiter='\t', quoting=csv.QUOTE_NONE)
    lines, confidences, tokens = {}, [], []
    for row in rows:
        word = (row.get('text') or '').strip()
        if not word or row['level'] != '5':
            continue
        key = (row['block_num'], row['par_num'], row['line_num'])
        lines.setdefault(key, []).append(word)
        confidence = float(row['conf'])
        confidences.append(confidence)
        tokens.append({'text': word, 'confidence': confidence, 'source_line': list(key),
                       'bbox': [int(row[k]) for k in ('left', 'top', 'width', 'height')]})
    text = '\n'.join(' '.join(words) for words in lines.values())
    return text, round(sum(confidences) / len(confidences), 2) if confidences else None, tokens


def read_pages(path: Path, media_type: str):
    if not path.is_file():
        raise ProcessingError('ORIGINAL_UNAVAILABLE', 'Stored original is unavailable.')
    pages = []
    with tempfile.TemporaryDirectory(prefix='ap-ocr-') as temporary, ExitStack() as stack:
        directory = Path(temporary)
        try:
            reader = PdfReader(path) if media_type == 'application/pdf' else None
            geometry = stack.enter_context(pdfplumber.open(path)) if reader else None
            count = len(reader.pages) if reader else 1
            for index in range(count):
                page = reader.pages[index] if reader else None
                geo = geometry.pages[index] if geometry else None
                native = page.extract_text(extraction_mode='layout') or '' if page is not None else ''
                # Only small isolated images may be ignored, not arbitrary image pages.
                small_images = geo is not None and sum(i['width'] * i['height'] for i in geo.images) <= .03 * geo.width * geo.height
                use_native = usable_text(native) and small_images and all(c.get('upright', True) for c in geo.chars) if geo else False
                if use_native:
                    words = geo.dedupe_chars().extract_words(x_tolerance=2, y_tolerance=3)
                    tokens = [{'text': w['text'], 'confidence': None,
                               'bbox': [w['x0'], w['top'], w['x1']-w['x0'], w['bottom']-w['top']]} for w in words]
                    layout = organize(tokens)
                    pages.append({'page': index + 1, 'method': 'native_text', **layout, 'raw_text': native,
                                  'quality_rule': QUALITY_VERSION, 'ocr_confidence': None, 'tokens': tokens,
                                  'width': geo.width, 'height': geo.height, 'coordinate_unit': 'pt',
                                  'image_strategy': 'native_with_small_images' if geo.images else 'native',
                                  'warnings': ['SMALL_IMAGES_NOT_OCR'] if geo.images else []})
                    continue
                image_path = directory / f'page-{index + 1}.png'
                strategy = 'uploaded_image'
                if reader and original_scan(page, geo, image_path):
                    strategy = 'embedded_original'
                elif reader:
                    run_tool(['pdftoppm', '-f', str(index + 1), '-l', str(index + 1),
                              '-scale-to', '2400', '-singlefile', '-png', str(path), str(image_path.with_suffix(''))])
                    strategy = 'rendered_composite'
                else:
                    with Image.open(path) as image:
                        ImageOps.exif_transpose(image).convert('RGB').save(image_path)
                with Image.open(image_path) as image:
                    source_size = list(image.size)
                    scale = 2 if max(image.size) < 1000 else 1
                    ocr_path = directory / f'ocr-{index + 1}.png'
                    if scale == 2:
                        image.resize((image.width * 2, image.height * 2), Image.Resampling.BICUBIC).save(ocr_path)
                    else:
                        ocr_path = image_path
                text, confidence, tokens = ocr_image(ocr_path)
                width, height = (v * scale for v in source_size)
                pages.append({'page': index + 1, 'method': 'tesseract', **organize(tokens), 'raw_text': text,
                              'quality_rule': QUALITY_VERSION, 'ocr_confidence': confidence,
                              'tokens': tokens, 'width': width, 'height': height, 'coordinate_unit': 'px',
                              'image_strategy': strategy, 'warnings': [],
                              'source_image_size': source_size, 'ocr_scale': scale,
                              'pdf_page_size': [geo.width, geo.height] if geo else None,
                              'image_pdf_bbox': [geo.images[0][k] for k in ('x0', 'top', 'x1', 'bottom')] if strategy == 'embedded_original' else None})
        except ProcessingError:
            raise
        except Exception as exc:
            raise ProcessingError('DOCUMENT_READ_FAILED', 'Unable to read the saved document.') from exc
    if not any(p['text'].strip() for p in pages):
        raise ProcessingError('NO_READABLE_TEXT', 'No readable text was recovered; manual intervention is required.')
    return pages


def original_scan(page, geo, destination):
    """Decode a single, unrotated, whole-page image without resizing it."""
    if (geo.chars or len(geo.images) != 1 or geo.lines or geo.rects or geo.curves
            or page.rotation or page.get('/Annots') or page.cropbox != page.mediabox):
        return False
    placement = geo.images[0]
    # A scan may have a blank page border; retain its placement for coordinate mapping.
    if (placement.get('imagemask') or placement['width'] * placement['height'] < .85 * geo.width * geo.height
            or placement['x0'] < 0 or placement['top'] < 0
            or placement['x1'] > geo.width + .01 or placement['bottom'] > geo.height + .01):
        return False
    transforms = []
    page.extract_text(visitor_operand_before=lambda op, args, cm, tm: transforms.append(list(cm)) if op == b'Do' else None)
    if len(transforms) != 1:
        return False
    a, b, c, d, _, _ = transforms[0]
    if a <= 0 or d <= 0 or abs(b) > .001 or abs(c) > .001:
        return False
    images = list(page.images)
    if len(images) != 1 or images[0].image is None:
        return False
    images[0].image.save(destination)
    return True


def ocr_available():
    return bool(shutil.which('tesseract') and shutil.which('pdftoppm'))
