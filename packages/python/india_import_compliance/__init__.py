"""Offline lookup of India import policy and compliance measures per ITC(HS) 2022 code. Not legal advice."""
import csv
import os
import re

__all__ = ['lookup', 'measures', 'search', '__version__']

try:
    from importlib.metadata import PackageNotFoundError, version as _version
    __version__ = _version('india-import-compliance')
except Exception:  # not installed (run from a checkout)
    __version__ = '0+unknown'

_DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
_cache = {}


def _load(name):
    if name not in _cache:
        with open(os.path.join(_DATA, name), encoding='utf-8', newline='') as fh:
            _cache[name] = list(csv.DictReader(fh))
    return _cache[name]


def _norm(hs):
    d = re.sub(r'\D', '', str(hs))
    return d if len(d) in (4, 6, 8) else ''


def lookup(hs):
    """The ITC(HS) 2022 line for a 4, 6 or 8 digit code as a dict, or None."""
    d = _norm(hs)
    if not d:
        return None
    for r in _load('all.csv'):
        if r['hs_code'] == d:
            return dict(r)
    return None


def measures(hs):
    """Every measure for an 8-digit code, or for all codes under a 4 or 6 digit prefix. [] when none."""
    d = _norm(hs)
    if not d:
        return []
    return [dict(m) for m in _load('measures.csv') if m['hs8'].startswith(d)]


def search(text, limit=20):
    """8-digit lines whose code or description (including the six-digit heading text) contains every word of `text`."""
    words = [w for w in re.split(r'\W+', str(text).lower()) if w]
    if not words:
        return []
    hits = []
    for r in _load('all.csv'):
        if r['level'] != '8':
            continue
        hay = ' '.join((r['hs_code'], r['hs6_description'], r['description'])).lower()
        if all(w in hay for w in words):
            hits.append((0 if all(w in r['hs6_description'].lower() for w in words) else 1, len(r['description']), r))
    hits.sort(key=lambda t: (t[0], t[1], t[2]['hs_code']))
    return [dict(r) for _, _, r in hits[:limit]]
