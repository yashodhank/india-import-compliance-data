#!/usr/bin/env python3
"""Change detector: has any source page changed since the last look?

    python3 -m pipeline.monitor [--state state/monitor.json] [--root .] [--report monitor-report.json]

Each source is fetched by the cheapest route (direct, free; the paid fallback only when the origin refuses), its body is normalised
(whitespace runs, scripts, styles, comments, CSRF/nonce tokens, cache-busting query values and the copyright year are removed) and the
sha256 of the result is compared with the one in the state file. Exit 0 always on a clean look; the report says which ids changed.
A source that cannot be fetched keeps its previous hash (an unreachable page is not a change). The first look only records.
"""
import argparse
import datetime
import hashlib
import json
import os
import re
import sys

from pipeline import fallback as FB
from pipeline import sources as S

DEFAULT_ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

VOLATILE = [
    (r'(?is)<script\b.*?</script>', ' '),
    (r'(?is)<style\b.*?</style>', ' '),
    (r'(?s)<!--.*?-->', ' '),
    (r'(?i)<meta[^>]+(csrf|xsrf|nonce|token)[^>]*>', ' '),
    (r'(?i)<input[^>]+name=["\']?[^"\' >]*(csrf|xsrf|token|nonce|viewstate|eventvalidation)[^>]*>', ' '),
    (r'(?i)\b(nonce|csrf[-_]?token|jsessionid|PHPSESSID)=["\']?[\w.%-]+', ' '),
    (r'(?i)([?&;](ver|v|_|t|ts|cb|rnd))=[\w.-]+', ''),
    (r'(?i)(copyright|&copy;|\xa9)[\s&;a-z0-9]*?(19|20)\d\d', 'copyright'),
]


def normalise(body):
    """Bytes -> bytes. HTML loses its volatile fragments; anything that is not text (a PDF) is hashed as it is."""
    if body[:5] == b'%PDF-':
        return body
    t = body.decode('utf-8', 'replace')
    for pat, rep in VOLATILE:
        t = re.sub(pat, rep, t)
    return re.sub(r'\s+', ' ', t).strip().encode('utf-8')


def digest(body):
    return hashlib.sha256(normalise(body)).hexdigest()


def look(fetch, urls, state, today):
    """-> (new_state, changed ids, failed ids)."""
    new, changed, failed = {}, [], []
    for sid, url in urls:
        old = state.get(sid) or {}
        try:
            h = digest(fetch(url))
        except FB.Failure as e:
            failed.append('%s: %s' % (sid, str(e)[:120]))
            new[sid] = old
            continue
        if old.get('sha256') and old['sha256'] != h:
            changed.append(sid)
        new[sid] = {'url': url, 'sha256': h, 'checked_on': today, 'changed_on': today if (old.get('sha256') and old['sha256'] != h) else old.get('changed_on', '')}
    return new, changed, failed


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--root', default=DEFAULT_ROOT)
    ap.add_argument('--state', default='state/monitor.json')
    ap.add_argument('--report')
    a = ap.parse_args(argv)
    path = os.path.join(a.root, a.state)
    state = json.load(open(path, encoding='utf-8')) if os.path.isfile(path) else {}
    fetcher = FB.FallbackFetcher()
    today = datetime.date.today().isoformat()
    new, changed, failed = look(fetcher, S.source_urls(), state, today)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as fh:
        fh.write(json.dumps(new, indent=1, sort_keys=True) + '\n')
    report = {'changed': changed, 'failed': failed, 'first_look': not state, 'fallback': fetcher.stats()}
    if a.report:
        with open(a.report, 'w', encoding='utf-8') as fh:
            fh.write(json.dumps(report, indent=1) + '\n')
    print(json.dumps(report, indent=1))
    return 0


if __name__ == '__main__':
    sys.exit(main())
