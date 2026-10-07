"""Create labeled native-Agent evaluation documents; expected values never enter the model prompt."""
import json
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from pypdf import PdfWriter
from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / 'data/native-b3-samples'


def main():
    DEST.mkdir(exist_ok=True)
    cases = []
    for kind, total, net, tax in [('text', '119.00', '100.00', '19.00'), ('scan', '11900.00', '10000.00', '1900.00'), ('missing', '238.00', '200.00', '38.00')]:
        fields = dict(supplier_name='Native Demo Supplies Ltd', supplier_address='12 Sample Street, Berlin 10115', supplier_tax_id='DE123456789', invoice_number='NATIVE-B3-20261007-'+kind.upper(), invoice_date='2026-10-07', due_date=None if kind=='missing' else '2026-10-21', currency='EUR', net_amount=net, tax_amount=tax, total_amount=total, discount_amount=None, shipping_amount=None, has_adjustments=False)
        lines=['SYNTHETIC DEMO INVOICE - NOT PAYABLE', 'Supplier: '+fields['supplier_name'], 'Address: '+fields['supplier_address'], 'VAT ID: '+fields['supplier_tax_id'], 'Invoice number: '+fields['invoice_number'], 'Invoice date: '+fields['invoice_date']]
        if fields['due_date']: lines.append('Due date: '+fields['due_date'])
        lines += ['Currency: EUR', 'Consulting services', 'Net amount: '+net, 'VAT amount: '+tax, 'Grand total: '+total, 'End of invoice']
        path=DEST/(kind+'.pdf')
        if kind=='scan':
            image=Image.new('RGB',(1654,2339),'white')
            draw=ImageDraw.Draw(image)
            font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',38)
            for i,line in enumerate(lines): draw.text((100,130+i*95),line,font=font,fill='black')
            image.save(DEST/'scan.png')
            image.save(path,'PDF',resolution=200)
        else:
            writer=PdfWriter(); page=writer.add_blank_page(width=595,height=842)
            font=DictionaryObject({NameObject('/Type'):NameObject('/Font'),NameObject('/Subtype'):NameObject('/Type1'),NameObject('/BaseFont'):NameObject('/Helvetica')})
            page[NameObject('/Resources')]=DictionaryObject({NameObject('/Font'):DictionaryObject({NameObject('/F1'):writer._add_object(font)})})
            stream=DecodedStreamObject()
            stream.set_data(('BT /F1 12 Tf 45 780 Td 28 TL '+ ' T* '.join('('+line.replace('(','\\(').replace(')','\\)')+') Tj' for line in lines)+' ET').encode('ascii'))
            page[NameObject('/Contents')]=writer._add_object(stream)
            writer.write(path)
        cases.append({'case':kind,'path':str(path.relative_to(ROOT)),'expected_fields':fields,'expected_route':'automatic' if kind=='text' else 'manual','expected_issue':'MISSING_FIELD' if kind=='missing' else None})
    (DEST/'invalid.pdf').write_bytes(b'This is a deliberately invalid attachment, not a PDF.')
    (DEST/'expected.json').write_text(json.dumps({'synthetic':True,'provider_request_budget':12,'cases':cases},indent=2)+'\n',encoding='utf-8')
    print('Created three labeled PDFs, expected fields and one invalid attachment.')


if __name__=='__main__': main()
