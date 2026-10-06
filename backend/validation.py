"""Conservative deterministic normalization, arithmetic and duplicate candidates."""

from datetime import date, datetime
from decimal import Decimal, InvalidOperation
import re
import unicodedata

MONEY_FIELDS = ('net_amount', 'tax_amount', 'total_amount', 'discount_amount', 'shipping_amount')
CURRENCY_PRECISION = {'EUR': 2, 'USD': 2, 'GBP': 2, 'CHF': 2, 'CAD': 2, 'AUD': 2, 'JPY': 0, 'KWD': 3}


def identity(value):
    return re.sub(r'\s+', ' ', unicodedata.normalize('NFKC', value or '').casefold()).strip()


def address_identity(value):
    return re.sub(r'\s+', ' ', re.sub(r'[^\w\s]', ' ', identity(value))).strip()


def money(raw):
    if raw is None or not str(raw).strip():
        return None
    value = re.sub(r'(?i)\b(?:EUR|USD|GBP|CHF|CAD|AUD|JPY|KWD)\b|[€$£¥\s]', '', str(raw))
    if value.startswith('(') and value.endswith(')'):
        value = '-' + value[1:-1]
    if not re.fullmatch(r'-?\d+(?:[.,]\d+)*', value):
        raise ValueError('Invalid amount')
    if '.' in value and ',' in value:
        decimal_sep = '.' if value.rfind('.') > value.rfind(',') else ','
        grouping = ',' if decimal_sep == '.' else '.'
        integer, fraction = value.rsplit(decimal_sep, 1)
        if not re.fullmatch(r'-?\d{1,3}(?:' + re.escape(grouping) + r'\d{3})+', integer):
            raise ValueError('Invalid grouping')
        value = integer.replace(grouping, '') + '.' + fraction
    elif ',' in value or '.' in value:
        sep = ',' if ',' in value else '.'
        pieces = value.split(sep)
        if len(pieces) != 2 or len(pieces[-1]) == 3:
            raise ValueError('Ambiguous amount separator')
        value = value.replace(',', '.')
    try:
        return Decimal(value)
    except InvalidOperation as exc:
        raise ValueError('Invalid amount') from exc


def parse_date(raw):
    if not raw:
        return None
    value = str(raw).strip()
    for fmt in ('%Y-%m-%d', '%d.%m.%Y', '%d-%b-%Y', '%d %b %Y', '%d %B %Y'):
        try:
            return datetime.strptime(value, fmt).date().isoformat()
        except ValueError:
            pass
    match = re.fullmatch(r'(\d{1,2})/(\d{1,2})/(\d{4})', value)
    if match:
        first, second, year = map(int, match.groups())
        if first > 12:
            return date(year, second, first).isoformat()
        if second > 12:
            return date(year, first, second).isoformat()
    raise ValueError('Invalid or ambiguous date')


def validate(raw):
    fields = dict(raw)
    issues = []
    def issue(code, field, message):
        issues.append({'code': code, 'field': field, 'message': message})

    for key in ('supplier_name', 'invoice_number', 'invoice_date', 'due_date', 'currency', 'total_amount'):
        if not raw.get(key):
            issue('MISSING_FIELD', key, f'{key} is not available from the document.')
    for key in ('invoice_date', 'due_date'):
        try:
            fields[key] = parse_date(raw.get(key))
        except ValueError:
            fields[key] = None
            issue('DATE_AMBIGUOUS_OR_INVALID', key, 'Date cannot be normalized without an assumption.')
    if fields.get('invoice_date') and fields.get('due_date') and fields['due_date'] < fields['invoice_date']:
        issue('DUE_BEFORE_INVOICE', 'due_date', 'Due date is earlier than invoice date.')

    currency = str(raw.get('currency') or '').strip().upper()
    currency = {'€': 'EUR', '£': 'GBP'}.get(currency, currency)
    if currency not in CURRENCY_PRECISION:
        fields['currency'] = None
        issue('CURRENCY_UNRESOLVED', 'currency', 'Currency is ambiguous or unsupported; no default is applied.')
    else:
        fields['currency'] = currency
    values = {}
    for key in MONEY_FIELDS:
        try:
            values[key] = money(raw.get(key))
            fields[key] = format(values[key], 'f') if values[key] is not None else None
            if values[key] is not None and values[key] < 0:
                issue('NEGATIVE_AMOUNT_REVIEW', key, 'Negative amounts require document-type review.')
        except ValueError:
            values[key], fields[key] = None, None
            issue('AMOUNT_AMBIGUOUS_OR_INVALID', key, 'Amount cannot be normalized safely.')
    check = {'total_equation': 'not_evaluated', 'tolerance': None, 'computed_total': None, 'difference': None}
    adjustments = any(values.get(k) not in (None, Decimal(0)) for k in ('discount_amount', 'shipping_amount'))
    complete = fields.get('currency') and all(values.get(k) is not None for k in ('net_amount', 'tax_amount', 'total_amount'))
    if not complete:
        issue('TOTAL_CHECK_INCOMPLETE', 'total_amount', 'Net, tax, total and supported currency are needed to check arithmetic.')
    if raw.get('has_adjustments') is not False or adjustments:
        issue('TOTAL_EQUATION_REVIEW', 'total_amount', 'Discounts, shipping or other adjustments require an explicit totals equation.')
    elif complete:
        tolerance = Decimal(1).scaleb(-CURRENCY_PRECISION[currency])
        computed = values['net_amount'] + values['tax_amount']
        difference = values['total_amount'] - computed
        check.update(total_equation='net_plus_tax', tolerance=str(tolerance), computed_total=str(computed), difference=str(difference))
        if abs(difference) > tolerance:
            issue('TOTAL_MISMATCH', 'total_amount', f'Printed total differs from net plus tax by {difference} {currency}.')
    return fields, issues, check


def duplicate_candidates(fields, others):
    number = re.sub(r'\s+', '', identity(fields.get('invoice_number')))
    tax_id = identity(fields.get('supplier_tax_id'))
    name, address = identity(fields.get('supplier_name')), address_identity(fields.get('supplier_address'))
    if not number or not (tax_id or (name and address)):
        return 'not_evaluable', []
    matches = []
    for invoice_id, other in others:
        if re.sub(r'\s+', '', identity(other.get('invoice_number'))) != number:
            continue
        same_tax = tax_id and tax_id == identity(other.get('supplier_tax_id'))
        same_party = name and address and name == identity(other.get('supplier_name')) and address == address_identity(other.get('supplier_address'))
        if not same_tax and not same_party:
            continue
        matches.append({'invoice_id': invoice_id, 'basis': 'supplier_tax_id_and_invoice_number' if same_tax else 'supplier_name_address_and_invoice_number',
                        'currency_matches': bool(fields.get('currency')) and fields.get('currency') == other.get('currency'),
                        'total_matches': fields.get('total_amount') is not None and other.get('total_amount') is not None and Decimal(fields['total_amount']) == Decimal(other['total_amount'])})
    return ('candidate' if matches else 'no_candidates'), matches
