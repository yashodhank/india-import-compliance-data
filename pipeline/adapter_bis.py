"""BIS HTML-table adapters: Scheme-I, Scheme-II (non-MeitY tables), Scheme-IV, Scheme-X and the upcoming-QCO list (pipeline/adapters.py has the contract).

Every table is read on its columns with rowspans honoured (adapters.html_grid): a row that holds only its product still has the serial, IS code and
notification the row above spans over it. The expected row count is the table's own `<tr>` count less the header, the blank spacers and the section
titles; a `<tr>` that is none of these and does not fill the table's columns is a failure, never a skipped row."""
import re

from pipeline.adapters import CUT, Failure, NoStructure, Parsed, clean, count_check, html_grid, page_date, row, status_of


def grid_tables(body, shapes, what):
    """The page's tables, each checked against the header cells the parser was proved against."""
    ts = html_grid(body)
    if len(ts) < len(shapes):
        raise NoStructure('%s: %d tables on the page, %d expected (layout changed?)' % (what, len(ts), len(shapes)))
    for i, head in enumerate(shapes):
        got = [c[0].lower() for c in ts[i][0]] if ts[i] else []
        if not all(any(w in g for g in got) for w in head):
            raise Failure('%s: table %d header is %r, expected cells like %r (layout changed?)' % (what, i, got, head))
    return ts


def blank(r):
    return not any(c[0] for c in r)


def data_rows(t, width, what, sections=False, spacer=blank, widths=None):
    """(rows, expected): the data rows of a table below its header, and the count taken from the `<tr>`s by elimination (all minus header,
    spacers and, where the table has them, section titles). A row that is not one of those and is not `width` columns wide is a failure."""
    body = t[1:]
    spacers = [r for r in body if spacer(r)]
    secs = [r for r in body if sections and not spacer(r) and r.own <= 2 and not any(r.covered) and (len(r) == 1 or not r[1][0])]
    data = [r for r in body if not spacer(r) and not any(r is x for x in secs)]
    for r in data:
        if len(r) not in (widths or (width,)):
            raise Failure('%s: a row of %d columns (%d of its own) has a shape the parser does not know: %r' % (what, len(r), r.own, r[0][0][:40]))
    return data, len(body) - len(spacers) - len(secs), secs


def table_copies(ts):
    """The Scheme-I page carries its table three times, and BIS edits them at different moments: on 2026-10-22 one copy (the second) held three new
    rows (IS 1664, IS 5470, IS 920, the Animal Feeds QCO of 12 Oct 2026) that the other two did not yet have. The copies also word their notification
    cell and some product names differently, so switching the copy a row is read from would churn the whole file. The rule, chosen deliberately:
      1. The row SET comes from the copy with the most rows, provided every other copy's IS-number sequence is an in-order subsequence of it (the
         others are only behind on edits). Anything else (a code the longest copy lacks, or another order) is a real contradiction: Failure.
      2. A row's TEXT comes from the first copy whenever the first copy has that row (the copy the dataset was always built from); only the rows
         the first copy lacks are read from the longest copy.
    Returns (index of the copy that sets the rows, {id(row of that copy): row to read instead}, {id(row to read): corrected name}, number of rows
    the longest copy has over the shortest). The name is corrected where the first copy's is the other two's with a stray serial digit in front
    ("6Stainless Steel ..."); any other name disagreement is counted in the parse notes, not guessed at."""
    copies = [[r for r in t[1:] if len(r) == 4 and r[1][0] and r[2][0]] for t in ts[:3]]
    if len(copies) < 3:
        return 0, {}, {}, 0, 0
    base = max(range(3), key=lambda i: (len(copies[i]), -i))  # the longest; the first of equals
    keys = [r[1][0] for r in copies[base]]
    at = [None] * 3  # at[i][n] = copy i's row for the base copy's n-th row
    for i, c in enumerate(copies):
        pos, m = 0, {}
        for r in c:
            while pos < len(keys) and keys[pos] != r[1][0]:
                pos += 1
            if pos == len(keys):
                raise Failure('scheme_1: the page\'s three copies of the table list different IS numbers (layout changed?)')
            m[pos] = r
            pos += 1
        at[i] = m
    use, names, differs = {}, {}, 0
    for n, brow in enumerate(copies[base]):
        src = 0 if n in at[0] else base
        a = at[src][n]
        if a is not brow:
            use[id(brow)] = a
        others = [at[i][n] for i in range(3) if i != src and n in at[i]]
        if any(a[2][0] != o[2][0] for o in others):
            differs += 1
            if len(others) == 2 and others[0][2][0] == others[1][2][0] and re.fullmatch(r'\d+' + re.escape(others[0][2][0]), a[2][0]):  # the stray serial digit
                names[id(a)] = others[0][2][0]
    return base, use, names, differs, len(copies[base]) - min(len(c) for c in copies)


def parse_scheme1(body, url, today):
    ts = grid_tables(body, [['sr no', 'is no', 'product']], 'scheme_1')
    base, use, names, disagreements, only_in_base = table_copies(ts)
    t = ts[base]
    out, sec, notif, links = [], '', '', []
    scheme = 'BIS ISI-mandatory QCO (Scheme-I)'
    spacer = lambda r: blank(r) or (len(r) >= 3 and not r[1][0] and not r[2][0])  # noqa: E731 (a blank-looking row between sections)
    data, expected, secs = data_rows(t, 4, 'scheme_1', sections=True, spacer=spacer)
    is_sec = {id(r) for r in secs}
    for r in t[1:]:
        if spacer(r):
            continue
        if id(r) in is_sec:
            sec, notif, links = clean(r[0][0]), '', []
            continue
        r = use.get(id(r), r)  # the first copy's text for a row it has
        if not r[1][0] or not r[2][0]:
            raise Failure('scheme_1: row %r has no IS number or no product' % r[0][0][:40])
        if r[3][0]:
            notif, links = r[3][0], r[3][1]
        status, tag = status_of(sec, notif)
        out.append(row(url, today, product_name=names.get(id(r), r[2][0]), is_codes=r[1][0], scheme=scheme,
                       authority='BIS (via QCO of administering ministry)', group=sec, status=status,
                       notes='QCO: ' + notif[:CUT] + (' | QCO PDF: ' + '; '.join(links[:3]) if links else '') + tag))
    keys = [(r['is_codes'], r['product_name']) for r in out]
    if len(set(keys)) != len(keys):
        raise Failure('scheme_1: two rows share one IS code + product name')
    count_check('scheme_1', len(out), expected)
    return Parsed(out, expected, page_date(body), {'section_titles': len(secs), 'name_differs_between_the_pages_tables': disagreements, 'rows_only_in_the_longest_table_copy': only_in_base})


S2_TABLES = [  # table index on the page -> (authority, group). Table 0 is the MeitY CRS list, taken from crsbis.in.
    (1, 'MNRE / BIS', 'MNRE Solar PV'),
    (2, 'Dept of Chemicals / BIS', 'Chemicals QCO under Scheme-II'),
    (3, 'Ministry of Textiles / BIS', 'Cotton Bales QCO under Scheme-II'),
]


def parse_scheme2_other(body, url, today):
    ts = grid_tables(body, [['sl. no', 'is no']] * 4, 'scheme_ii')
    if len(ts) != 4:
        raise Failure('scheme_ii: %d tables on the page, 4 expected (a new table needs a decision: layout changed?)' % len(ts))
    out, total = [], 0
    for i, authority, group in S2_TABLES:
        notif = ''
        data, expected, _ = data_rows(ts[i], 5, 'scheme_ii table %d' % i)
        total += expected
        for r in data:
            notif = r[4][0] or notif
            status, tag = status_of('', notif)
            out.append(row(url, today, product_name=r[3][0], is_codes=r[1][0],
                           scheme='BIS Scheme-II registration (non-MeitY: solar / chemicals / textiles)', authority=authority, group=group,
                           status=status, notes='Standard title: ' + r[2][0] + ' | Notification: ' + notif[:500] + tag))
    count_check('scheme_ii', len(out), total)
    return Parsed(out, total, page_date(body), {})


def parse_scheme4(body, url, today):
    t = grid_tables(body, [['sr no', 'product', 'essential']], 'scheme_4')[0]
    data, expected, _ = data_rows(t, 4, 'scheme_4')
    out = []
    for r in data:
        status, tag = status_of('', r[3][0])
        out.append(row(url, today, product_name=r[1][0], is_codes=r[2][0],
                       scheme='BIS Scheme-IV (Essential-requirement / input material)', authority='BIS', group='Scheme-IV', status=status,
                       notes='Essential requirement: ' + r[2][0] + ' | QCO: ' + r[3][0][:400] + tag))
    count_check('scheme_4', len(out), expected)
    return Parsed(out, expected, page_date(body), {})


def parse_scheme_x(body, url, today):
    ts = grid_tables(body, [['sr no', 'indian standards'], ['sr no', 'description']], 'scheme_x')
    out, notif = [], ''
    d0, e0, _ = data_rows(ts[0], 6, 'scheme_x electrical', widths=(5, 6))  # a row without a notification cell keeps the one above
    for r in d0:
        notif = (r[5][0] if len(r) == 6 else '') or notif
        status, tag = status_of('', notif)
        out.append(row(url, today, product_name=r[3][0], is_codes=r[1][0],
                       scheme='BIS Scheme-X (Electrical equipment type testing)', authority='Ministry of Heavy Industries / BIS',
                       group='Electrical Equipment (Quality Control) Order 2020', status=status,
                       notes='Sr ' + r[0][0] + ' | Title: ' + r[2][0] + ' | Specific requirement: ' + r[4][0][:300] + ' | ' + notif[:300] + tag))
    d1, e1, _ = data_rows(ts[1], 3, 'scheme_x machinery')
    std = ''
    for r in d1:
        std = r[2][0] or std
        out.append(row(url, today, product_name=r[1][0], is_codes=std,
                       scheme='BIS Scheme-X (Machinery & Electrical Equipment Safety)', authority='Ministry of Heavy Industries / BIS',
                       group='Machinery and Electrical Equipment Safety (Omnibus Technical Regulation) Order', notes='Sr ' + r[0][0]))
    count_check('scheme_x', len(out), e0 + e1)
    return Parsed(out, e0 + e1, page_date(body), {'electrical': len(d0), 'machinery': len(d1)})


def parse_upcoming(body, url, today):
    t = grid_tables(body, [['sr. no', 'ministry', 'product', 'indian standard', 'enforcement']], 'qco_upcoming')[0]
    out, parent = [], None
    scheme = 'BIS QCO upcoming (notified, not yet enforced)'
    data = [r for r in t[1:] if not blank(r)]
    for r in data:
        if len(r) == 1 and parent:  # a bare sub-appliance row (no spans): it belongs to the serial above
            r = type(r)([parent[0], parent[1], r[0], parent[3], parent[4]])
            r.own, r.covered = 1, (True, True, False, True, True)
        if len(r) != 5:
            raise Failure('qco_upcoming: a row of %d columns has a shape the parser does not know' % len(r))
        if r.covered[0] and parent:  # sub-appliance: serial, ministry, standard and date are spanned from the parent row
            out.append(row(url, today, product_name=r[2][0], is_codes=parent[3][0], scheme=scheme,
                           authority=parent[1][0] + ' / BIS',
                           group='Upcoming QCOs - household appliance sub-list (item %s)' % parent[0][0], status='upcoming',
                           notes='Sub-appliance listed under serial %s; applicable IS 302 Part 2 section per appliance NOT given on page | Enforcement date: %s'
                           % (parent[0][0], parent[4][0])))
        else:
            parent = r
            out.append(row(url, today, product_name=r[2][0], is_codes=r[3][0], scheme=scheme,
                           authority=r[1][0] + ' / BIS', group='Upcoming QCOs', status='upcoming',
                           notes='List serial %s | Enforcement date: %s' % (r[0][0], r[4][0])))
    count_check('qco_upcoming', len(out), len(data))
    return Parsed(out, len(data), page_date(body), {})
