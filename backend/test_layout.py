"""Geometry and routing checks; no model calls or fixture answers in production."""
import io
from pathlib import Path

from PIL import Image
from pypdf import PdfReader, PdfWriter, Transformation

from backend.document_text import read_pages, original_scan
import pdfplumber
from backend.pdf_layout import organize

ROOT = Path(__file__).resolve().parents[1]


def test_columns_are_separate_and_all_tokens_retained():
    tokens = [{'text': text, 'bbox': box} for text, box in [
        ('Seller', [10, 10, 35, 10]), ('Buyer', [200, 10, 35, 10]),
        ('Road', [10, 25, 30, 10]), ('Street', [200, 25, 35, 10]),
        ('City', [10, 40, 25, 10]), ('Town', [200, 40, 25, 10])]]
    result = organize(tokens)
    assert [b['text'] for b in result['blocks']] == ['Seller\nRoad\nCity', 'Buyer\nStreet\nTown']
    assert sorted(i for l in result['lines'] for i in l['token_ids']) == list(range(6))
    assert result['lines'][0]['row_id'] == result['lines'][1]['row_id']


def test_native_pdf_with_small_logo_does_not_call_ocr(tmp_path, monkeypatch):
    import backend.document_text as module
    reader = PdfReader(ROOT / 'test_data/first_round/text_pdf/01_invoice_A.pdf')
    logo = io.BytesIO()
    Image.new('RGB', (100, 100), 'red').save(logo, format='PDF')
    reader.pages[0].merge_transformed_page(PdfReader(logo).pages[0], Transformation().scale(.2).translate(550, 760))
    writer = PdfWriter(); writer.add_page(reader.pages[0])
    path = tmp_path / 'logo.pdf'; writer.write(path)
    monkeypatch.setattr(module, 'ocr_image', lambda _: (_ for _ in ()).throw(AssertionError('OCR not expected')))
    page = read_pages(path, 'application/pdf')[0]
    assert page['method'] == 'native_text'
    assert page['image_strategy'] == 'native_with_small_images'
    assert page['tokens'] and page['lines'] and page['blocks']
    assert page['coordinate_unit'] == 'pt'


def test_whole_page_scan_keeps_original_pixels(tmp_path, monkeypatch):
    import backend.document_text as module
    path = ROOT / 'test_data/first_round/ocr/invoice_ocr (11).pdf'
    expected = list(PdfReader(path).pages[0].images)[0].image
    saved = tmp_path / 'original.png'
    with pdfplumber.open(path) as pdf:
        assert original_scan(PdfReader(path).pages[0], pdf.pages[0], saved)
    with Image.open(saved) as original:
        assert original.size == expected.size
        assert original.convert('RGB').tobytes() == expected.convert('RGB').tobytes()
    def ocr(image_path):
        with Image.open(image_path) as actual:
            assert actual.size == (expected.width * 2, expected.height * 2)
        return 'Recognized', 90, [{'text': 'Recognized', 'bbox': [10, 10, 50, 10], 'confidence': 90}]
    monkeypatch.setattr(module, 'ocr_image', ocr)
    page = read_pages(path, 'application/pdf')[0]
    assert page['image_strategy'] == 'embedded_original'
    assert page['image_pdf_bbox'] and page['pdf_page_size']
    assert page['source_image_size'] == list(expected.size)
    assert page['ocr_scale'] == 2


def test_rotated_scan_uses_render_fallback(tmp_path, monkeypatch):
    import backend.document_text as module
    source = PdfReader(ROOT / 'test_data/first_round/ocr/invoice_ocr (11).pdf')
    source.pages[0].rotate(90)
    writer = PdfWriter(); writer.add_page(source.pages[0])
    path = tmp_path / 'rotated.pdf'; writer.write(path)
    calls = []
    def render(args):
        calls.append(args)
        Image.new('RGB', (120, 200), 'white').save(args[-1] + '.png')
        return b''
    monkeypatch.setattr(module, 'run_tool', render)
    monkeypatch.setattr(module, 'ocr_image', lambda _: ('text', 90, [{'text': 'text', 'bbox': [1, 1, 10, 10]}]))
    page = read_pages(path, 'application/pdf')[0]
    assert page['image_strategy'] == 'rendered_composite'
    assert calls[0][0] == 'pdftoppm'
