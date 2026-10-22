"""CRS (Compulsory Registration Scheme) adapter: the product table of the CRS portal.

Rows are keyed on IS code + product name, never on the serial (a serial-keyed scraper once dropped a rowspan row:
73 parsed against 74 on the official list). A 3-cell row after a numbered row is a rowspan continuation and inherits the serial.
"""
import re

from pipeline.adapters import Failure, NoStructure, Parsed, clean, count_check, html_tables, page_date, row

SCHEME = 'BIS CRS (Scheme-II registration)'
MONTHS = {m: i + 1 for i, m in enumerate(['jan', 'feb', 'mar', 'apr', 'may', 'jun', 'jul', 'aug', 'sep', 'oct', 'nov', 'dec'])}


def iso_date(text):
    m = re.search(r'(\d{1,2})\s+([A-Za-z]{3})[a-z]*\.?,?\s+(\d{4})', text or '')
    if not m or m.group(2).lower() not in MONTHS:
        return ''
    return '%04d-%02d-%02d' % (int(m.group(3)), MONTHS[m.group(2).lower()], int(m.group(1)))


def parse_crs(body, url, today):
    ts = html_tables(body)
    if not ts:
        raise NoStructure('crs: no table on the page (layout changed?)')
    t = ts[0]
    head = [c[0].lower() for c in t[0]] if t else []
    if not (any('product' in h for h in head) and any('is' in h for h in head)):
        raise Failure('crs: table header is %r (layout changed?)' % head)
    out, last_sl, seen, expected = [], '', set(), 0
    for r in t[1:]:
        c = [x[0] for x in r]
        if len(c) == 4 and c[0]:
            sl, name, is_, date = c
            last_sl, tag = sl, 'Sl ' + sl
        elif len(c) == 3 and last_sl:
            name, is_, date = c
            tag = 'Sl %s (unnumbered second row)' % last_sl
        else:
            continue
        expected += 1
        key = (re.sub(r'\W', '', is_).lower(), re.sub(r'\W', '', name).lower())
        if key in seen:
            raise Failure('crs: two rows share one IS code + product name (%s)' % name)
        seen.add(key)
        rr = row(url, today, product_name=name, is_codes=is_, scheme=SCHEME, authority='MeitY / BIS (CRS portal)',
                 group='CRS product list', notes='Date of implementation of QCO: %s | %s' % (date, tag))
        rr['enforcement_date'] = iso_date(date)
        out.append(rr)
    # the source's own count: every data row of the table has a product cell and an IS cell
    source_rows = sum(1 for r in t[1:] if len(r) in (3, 4) and all(x[0] for x in r[-3:-1]))
    count_check('crs', len(out), source_rows)
    return Parsed(out, source_rows, page_date(body), {})
