"""BEE star-label adapter: the mandatory and voluntary appliance pages (pipeline/adapters.py has the contract)."""
import re

from pipeline.adapters import Failure, Parsed, STATUS_TAG, clean, count_check, need_tables, row


def parse_bee(m_body, v_body, m_url, v_url, today):
    out = []
    tm = need_tables(m_body, [['sr.no', 'equipments name']], 'bee_mandatory')[0]
    tv = need_tables(v_body, [['sr. no', 'equipments name', 'schedules']], 'bee_voluntary')[0]
    archived, prev, blank_seen = False, 0, False
    # expected counts come from the <tr>s by elimination: every row below the header that is not wholly blank
    expected_m = sum(1 for r in tm[1:] if any(c[0] for c in r))
    expected_v = sum(1 for r in tv[1:] if any(c[0] for c in r))
    for r in tm[1:]:
        if not any(c[0] for c in r):
            blank_seen = True  # maybe the gap before the discontinued appliances: it is one only if the numbering starts over after it
            continue
        if len(r) < 2 or not re.fullmatch(r'\d+', r[0][0]):
            raise Failure('bee_mandatory: a row with first cell %r has a shape the parser does not know' % (r[0][0] if r else ''))
        serial = int(r[0][0])
        if blank_seen and serial <= prev:
            archived = True
        blank_seen, prev = False, serial
        name = clean(r[1][0])
        m = re.search(r'\(([^()]*(?:discontinued|w\.e\.f)[^()]*)\)\s*$', name, re.I)  # only a date note is cut from the name; "(Variable Speed)" is part of it
        paren = m.group(1) if m else ''
        base = clean(name[:m.start()]) if m else name
        discontinued = archived or bool(re.search(r'discontinued', paren, re.I))
        notes = 'Sr %s on BEE portal; IS code not shown on portal list (standards are in BEE schedules/notifications)' % clean(r[0][0])
        if paren and not discontinued:
            notes += ' | As printed: ' + paren
        if discontinued:
            notes += STATUS_TAG + 'discontinued' + (' (as printed: ' + paren + ')' if paren else ' (listed after the live appliances)')
        out.append(row(m_url, today, product_name=base, scheme='BEE star-label (mandatory)', authority='BEE (Ministry of Power)',
                       group='Mandatory Appliance' + (' - archive/discontinued' if discontinued else ''),
                       status='discontinued' if discontinued else 'active', notes=notes))
    for r in tv[1:]:
        if not any(c[0] for c in r):
            continue
        if len(r) < 3 or not re.fullmatch(r'\d+', r[0][0]):
            raise Failure('bee_voluntary: a row with first cell %r has a shape the parser does not know' % (r[0][0] if r else ''))
        out.append(row(v_url, today, product_name=clean(r[1][0]), scheme='BEE star-label (voluntary)', authority='BEE (Ministry of Power)',
                       group='Voluntary Appliance', notes='Sr %s | %s | IS code not shown on portal list' % (clean(r[0][0]), clean(r[2][0]))))
    count_check('bee', len(out), expected_m + expected_v)
    return Parsed(out, expected_m + expected_v, '', {'mandatory': expected_m, 'voluntary': expected_v})
