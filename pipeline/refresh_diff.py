#!/usr/bin/env python3
"""A human-readable account of what a refresh changed in each official list. Stdlib only.

For every list: rows added, rows removed, status changes and date changes, keyed on IS code + product name (never the serial; the same key a
second time in one list is told apart by its order). A date is any date the row's notes print, so a new amendment, a moved enforcement date and
a rescission date all show as a date change. Nothing here decides anything; it only reports.
"""
import re
import sys
import os

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import pipeline.adapters as A  # noqa: E402

SAMPLE = 20


def _norm(s):
    return re.sub(r'\W', '', s or '').lower()


SERIAL = re.compile(r'(?:\bSr|List serial|\bSl)\s+([\w.()/-]+)')


def _base(r):
    return (_norm(r.get('scheme')), _norm(r.get('is_codes')), _norm(r.get('product_name')))


def _keyed(rows, shared):
    """Rows by (scheme, IS code, name). A key that more than one row shares (the same standard listed at several serials) is widened with the
    row's own serial from its notes, so deleting the middle one of three is reported as that row and not as a change to its neighbour; what
    is still shared after that is told apart by order."""
    seen, out = {}, {}
    for r in rows:
        k = _base(r)
        if k in shared:
            m = SERIAL.search(r.get('notes') or '')
            k = k + (m.group(1) if m else '',)
        n = seen.get(k, 0)
        seen[k] = n + 1
        out[k + (n,)] = r
    return out


def _dates(notes):
    return ' ; '.join(d[2] for d in A.printed_dates(notes or ''))


def _label(r):
    return '%s (%s)' % (r.get('product_name', '')[:80], r.get('is_codes', '')[:40]) if r.get('is_codes') else r.get('product_name', '')[:80]


def list_diff(before, after):
    counts = {}
    for side in (before, after):
        c = {}
        for r in side:
            c[_base(r)] = c.get(_base(r), 0) + 1
        for k, n in c.items():
            counts[k] = max(counts.get(k, 0), n)
    shared = {k for k, n in counts.items() if n > 1}  # shared by several rows on either side of the refresh
    b, a = _keyed(before, shared), _keyed(after, shared)

    def lab(r):
        m = SERIAL.search(r.get('notes') or '') if _base(r) in shared else None
        return _label(r) + (' [serial %s]' % m.group(1) if m else '')
    added = [lab(a[k]) for k in a if k not in b]
    removed = [lab(b[k]) for k in b if k not in a]
    status, dates, other = [], [], 0
    for k in a:
        if k not in b:
            continue
        x, y = b[k], a[k]
        if x.get('status') != y.get('status'):
            status.append({'row': lab(y), 'from': x.get('status', ''), 'to': y.get('status', '')})
        elif _dates(x.get('notes')) != _dates(y.get('notes')):
            dates.append({'row': lab(y), 'from': _dates(x.get('notes')), 'to': _dates(y.get('notes'))})
        elif any(x.get(c, '') != y.get(c, '') for c in ('product_name', 'is_codes', 'group', 'scheme', 'authority', 'notes')):
            other += 1
    return {
        'rows_before': len(before), 'rows_after': len(after),
        'added': len(added), 'removed': len(removed), 'status_changed': len(status), 'date_changed': len(dates), 'other_changed': other,
        'added_sample': added[:SAMPLE], 'removed_sample': removed[:SAMPLE], 'status_sample': status[:SAMPLE], 'date_sample': dates[:SAMPLE],
    }


def changed(d):
    return bool(d['added'] or d['removed'] or d['status_changed'] or d['date_changed'] or d['other_changed'])
