"""PDF adapters: the BIS Option-2 (simplified procedure) list and the TEC MTCTE product list (pipeline/adapters.py has the contract)."""
import re

from pipeline.adapters import Failure, Parsed, clean, count_check, pdf_items, pdf_rows, row


def parse_simplified(body, url, today):
    items = pdf_items(body)
    head = ' '.join(i[4] for i in items if i[0] <= 3)
    if 'Sr. No.' not in head or 'IS Number' not in head or 'Product/Title' not in head:
        raise Failure('simplified: the table header is not in the PDF (layout changed?)')
    out, serials = [], []
    IS_COL_END = 255  # the product column starts right of this
    dropped = []
    for pg, sl, its in pdf_rows(items, 115, dropped):
        if re.fullmatch(r'Page \d+( of \d+)?', its[-1][4] if its else ''):
            its = its[:-1]
        is_parts, name_parts = [], []
        for _, top, left, width, text in its:
            in_is = left + width / 2 < IS_COL_END
            if not in_is and left < IS_COL_END and re.match(r'^IS\b', text):
                # one text item holds both cells ("IS 9537 (Part 3)   Conduits ..."): the code is cut at the first run of spaces
                m = re.match(r'^(IS\b.*?\))\s{2,}(\S.*)$', text) or re.match(r'^(IS\b[^a-z]*?)\s{2,}(\S.*)$', text)
                if m:
                    is_parts.append(m.group(1)); name_parts.append(m.group(2)); continue
            (is_parts if in_is else name_parts).append(text)
        serials.append(int(sl))
        out.append(row(url, today, product_name=clean(' '.join(name_parts)), is_codes=clean(' '.join(is_parts)),
                       scheme='BIS Simplified process (Option-2) list 2024', authority='BIS',
                       group='Option-2 (erstwhile simplified procedure) mandatory', notes='List serial %s' % sl))
    if serials != sorted(set(serials)):
        raise Failure('simplified: serials are not strictly increasing (a row was read twice or out of order)')
    bad = [r['notes'] for r in out if not r['product_name'] or not r['is_codes']]
    if bad:
        raise Failure('simplified: %d rows lack an IS number or a product (%s ...)' % (len(bad), bad[0]))
    gaps = sorted(set(range(1, max(serials) + 1)) - set(serials))
    count_check('simplified', len(out), len(serials))
    return Parsed(out, len(serials), '', {'serial_gaps_in_the_source': gaps, 'highest_serial': max(serials), 'footnotes_not_rows': dropped})


MTCTE_HEADER = {'S.N.', 'Essential Requirement/', 'Product Name', 'Product Variant Name', 'MTCTE Phase', 'Mandatory date of', 'certification of product under', 'MTCTE'}


MTCTE_EDGES = [114, 314, 517, 620]  # serial | essential requirement | variant | phase | date (the column rules printed in the PDF header)


def parse_mtcte(body, url, today):
    items = pdf_items(body)
    head = ' '.join(i[4] for i in items if i[0] == 1 and i[1] < 160)
    for w in ('S.N.', 'Essential Requirement', 'Product Variant Name', 'MTCTE Phase', 'Mandatory date of'):
        if w not in head:
            raise Failure('mtcte: header cell %r is not on page 1 (layout changed?)' % w)
    out, serials = [], []
    for pg, sl, its in pdf_rows(items, 112, header_words=MTCTE_HEADER, column_of=lambda i: sum(1 for e in MTCTE_EDGES[1:] if i[2] + i[3] / 2 >= e), chain_gap=16):
        cells = [[], [], [], []]
        for _, top, left, width, text in its:
            if re.fullmatch(r'Page \d+ of \d+', text):
                continue
            parts = re.split(r'\s{2,}', text)
            if len(parts) > 1 and any(left < e < left + width - 10 for e in MTCTE_EDGES):  # one item holding neighbouring cells ("Mobile Radio Trunking System  MRTS Base Station"): one part per cell, left to right
                first = sum(1 for e in MTCTE_EDGES[1:] if left + 6 >= e)
                for k, part in enumerate(parts):
                    cells[min(first + k, 3)].append(part)
            else:
                cells[sum(1 for e in MTCTE_EDGES[1:] if left + width / 2 >= e)].append(text)
        er, variant, phase, date = (clean(' '.join(c)) for c in cells)
        if not (er and variant and phase and date):
            raise Failure('mtcte: serial %s has an empty cell (er=%r variant=%r phase=%r date=%r)' % (sl, er, variant, phase, date))
        serials.append(int(sl))
        out.append(row(url, today, product_name=variant, scheme='TEC MTCTE', authority='TEC (DoT)', group=er,
                       notes='Essential Requirement/Product: %s | %s | Mandatory certification date: %s | IS code N/A (TEC ER/ITSAR, not BIS)' % (er, phase, date)))
    if serials != sorted(set(serials)):
        raise Failure('mtcte: serials are not strictly increasing')
    count_check('mtcte', len(out), len(serials))
    return Parsed(out, len(serials), '', {'highest_serial': max(serials)})
