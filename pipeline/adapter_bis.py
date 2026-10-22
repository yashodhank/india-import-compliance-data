"""BIS HTML-table adapters: Scheme-I, Scheme-II (non-MeitY tables), Scheme-IV, Scheme-X and the upcoming-QCO list (pipeline/adapters.py has the contract)."""
import re

from pipeline.adapters import CUT, SERIAL, Failure, Parsed, clean, count_check, need_tables, page_date, row, serial_rows, status_of


def parse_scheme1(body, url, today):
    ts = need_tables(body, [['sr no', 'is no', 'product']], 'scheme_1')
    t = ts[0]
    out, sec, notif, links = [], '', '', []
    scheme = 'BIS ISI-mandatory QCO (Scheme-I)'
    for r in t:
        if r and r[0][0] == 'Sr No.':
            continue
        if len(r) <= 2:
            sec, notif, links = clean(r[0][0]) if r else '', '', []
            continue
        if not r[1][0].strip():
            continue  # a blank spacer row
        if len(r) >= 4 and r[3][0].strip():
            notif, links = clean(r[3][0]), r[3][1]
        status, tag = status_of(sec, notif)
        out.append(row(url, today, product_name=clean(r[2][0]), is_codes=clean(r[1][0]), scheme=scheme,
                       authority='BIS (via QCO of administering ministry)', group=sec, status=status,
                       notes='QCO: ' + notif[:CUT] + (' | QCO PDF: ' + '; '.join(links[:3]) if links else '') + tag))
    keys = [(r['is_codes'], r['product_name']) for r in out]
    if len(set(keys)) != len(keys):
        raise Failure('scheme_1: two rows share one IS code + product name')
    count_check('scheme_1', len(out), serial_rows(t))
    return Parsed(out, serial_rows(t), page_date(body), {})


S2_TABLES = [  # table index on the page -> (authority, group). Table 0 is the MeitY CRS list, taken from crsbis.in.
    (1, 'MNRE / BIS', 'MNRE Solar PV'),
    (2, 'Dept of Chemicals / BIS', 'Chemicals QCO under Scheme-II'),
    (3, 'Ministry of Textiles / BIS', 'Cotton Bales QCO under Scheme-II'),
]


def parse_scheme2_other(body, url, today):
    ts = need_tables(body, [['sl. no', 'is no'], ['sl. no', 'is no'], ['sl. no', 'is no'], ['sl. no', 'is no']], 'scheme_ii')
    if len(ts) != 4:
        raise Failure('scheme_ii: %d tables on the page, 4 expected (a new table needs a decision: layout changed?)' % len(ts))
    out, expected = [], 0
    for i, authority, group in S2_TABLES:
        notif = ''
        expected += serial_rows(ts[i])
        for r in ts[i][1:]:
            if len(r) >= 5 and r[4][0].strip():
                notif = clean(r[4][0])
            if len(r) < 4:
                continue
            status, tag = status_of('', notif)
            out.append(row(url, today, product_name=clean(r[3][0]), is_codes=clean(r[1][0]),
                           scheme='BIS Scheme-II registration (non-MeitY: solar / chemicals / textiles)', authority=authority, group=group,
                           status=status, notes='Standard title: ' + clean(r[2][0]) + ' | Notification: ' + notif[:500] + tag))
    count_check('scheme_ii', len(out), expected)
    return Parsed(out, expected, page_date(body), {})


def parse_scheme4(body, url, today):
    ts = need_tables(body, [['sr no', 'product', 'essential']], 'scheme_4')
    out = []
    for r in ts[0][1:]:
        if len(r) < 4:
            continue
        notif = clean(r[3][0])
        status, tag = status_of('', notif)
        out.append(row(url, today, product_name=clean(r[1][0]), is_codes=clean(r[2][0]),
                       scheme='BIS Scheme-IV (Essential-requirement / input material)', authority='BIS', group='Scheme-IV', status=status,
                       notes='Essential requirement: ' + clean(r[2][0]) + ' | QCO: ' + notif[:400] + tag))
    count_check('scheme_4', len(out), serial_rows(ts[0]))
    return Parsed(out, serial_rows(ts[0]), page_date(body), {})


def parse_scheme_x(body, url, today):
    ts = need_tables(body, [['sr no', 'indian standards'], ['sr no', 'description']], 'scheme_x')
    out, notif = [], ''
    for r in ts[0][1:]:
        if len(r) >= 6 and r[5][0].strip():
            notif = clean(r[5][0])
        if len(r) < 4:
            continue
        status, tag = status_of('', notif)
        out.append(row(url, today, product_name=clean(r[3][0]), is_codes=clean(r[1][0]),
                       scheme='BIS Scheme-X (Electrical equipment type testing)', authority='Ministry of Heavy Industries / BIS',
                       group='Electrical Equipment (Quality Control) Order 2020', status=status,
                       notes='Sr ' + clean(r[0][0]) + ' | Title: ' + clean(r[2][0]) + (' | Specific requirement: ' + clean(r[4][0])[:300] if len(r) > 4 else '')
                       + ' | ' + notif[:300] + tag))
    n_first = len(out)
    std = ''
    for r in ts[1][1:]:
        if len(r) < 2:
            continue
        if len(r) >= 3:
            std = clean(r[2][0])
        out.append(row(url, today, product_name=clean(r[1][0]), is_codes=std,
                       scheme='BIS Scheme-X (Machinery & Electrical Equipment Safety)', authority='Ministry of Heavy Industries / BIS',
                       group='Machinery and Electrical Equipment Safety (Omnibus Technical Regulation) Order', notes='Sr ' + clean(r[0][0])))
    expected = sum(serial_rows(t) for t in ts[:2])
    if len(ts[1]) > 1 and serial_rows(ts[1]) != len(ts[1]) - 1:  # the machinery table has no 3-cell minimum on continuation rows
        expected = serial_rows(ts[0]) + sum(1 for r in ts[1][1:] if r and SERIAL.match(r[0][0]))
    count_check('scheme_x', len(out), expected)
    return Parsed(out, expected, page_date(body), {'electrical': n_first, 'machinery': len(out) - n_first})


def parse_upcoming(body, url, today):
    ts = need_tables(body, [['sr. no', 'ministry', 'product', 'indian standard', 'enforcement']], 'qco_upcoming')
    t = ts[0]
    out, parent = [], None
    scheme = 'BIS QCO upcoming (notified, not yet enforced)'
    data = [r for r in t[1:] if r]
    for r in data:
        if len(r) == 5:
            parent = r
            out.append(row(url, today, product_name=clean(r[2][0]), is_codes=clean(r[3][0]), scheme=scheme,
                           authority=clean(r[1][0]) + ' / BIS', group='Upcoming QCOs', status='upcoming',
                           notes='List serial %s | Enforcement date: %s' % (clean(r[0][0]), clean(r[4][0]))))
        elif len(r) == 1 and parent:
            out.append(row(url, today, product_name=clean(r[0][0]), is_codes=clean(parent[3][0]), scheme=scheme,
                           authority=clean(parent[1][0]) + ' / BIS',
                           group='Upcoming QCOs - household appliance sub-list (item %s)' % clean(parent[0][0]), status='upcoming',
                           notes='Sub-appliance listed under serial %s; applicable IS 302 Part 2 section per appliance NOT given on page | Enforcement date: %s'
                           % (clean(parent[0][0]), clean(parent[4][0]))))
        else:
            raise Failure('qco_upcoming: a row with %d cells has a shape the parser does not know' % len(r))
    count_check('qco_upcoming', len(out), len(data))
    return Parsed(out, len(data), page_date(body), {})
