#!/usr/bin/env python3
"""IS-standards metadata from BIS "Know Your Standards" (BIS Connect, public, no login). Stdlib only.

Metadata only: number, part, title, year, status, supersession, amendments list, reaffirmation year, classification. The text of a
standard is BIS copyright and is never fetched; no PDF, amendment file or Gazette download is followed.

    python -m pipeline.adapter_kys                  fetch what is missing (never fetched first, then the oldest), write data/is-standards/
    python -m pipeline.adapter_kys --max-refs 400   at most 400 references this run (default 400); the next run resumes
    python -m pipeline.adapter_kys --limit 5 --dry-run

The reference list is built here: every IS number named in data/bis/*.csv and data/qco/register.csv, as (base, part). The year is
dropped, so the LATEST edition on the portal is matched (all editions seen are not kept; see DATA-QUALITY.md).

Routes (anonymous session cookie plus the CSRF token the portal hands out on the details page):
    GET  knowyourstandards/indian_standards/isdetails           session + CSRF token
    POST knowyourstandards/Elasticsearch/getsearchAjax          fuzzy search; the exact number+part hit is chosen locally
    POST knowyourstandards/Indian_standards/isdetails/           details HTML
    POST knowyourstandards/Indian_standards/getamendments        amendments list
    POST knowyourstandards/Indian_standards/searchIS             result list: the only place that carries withdrawn / superseded
Never called: bisconnect/qco_file_details (gated for an anonymous session; answers 303).

Politeness: robots.txt first (404/HTML = no published rules; a disallow stops the run), 2 s between requests counted from the end of the
previous response, a user agent that names this repository. A 403 or 429 STOPS the run (exit 3): what was fetched is written, and the
next run resumes from the CSVs. Resumable by construction: a reference present in standards.csv or unmatched.csv is not fetched again
until it is older than --stale-days (default 120).
"""
import argparse
import base64
import csv
import hashlib
import html
import http.cookiejar
import io
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser
from datetime import date, datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.normpath(os.path.join(HERE, '..'))
HOST = 'https://www.services.bis.gov.in'
BC = HOST + '/php/BIS_2.0/bisconnect'
KYS = BC + '/knowyourstandards'
REPO_URL = 'https://github.com/yashodhank/india-import-compliance-data'
USER_AGENT = os.environ.get('ICD_USER_AGENT') or 'india-import-compliance-data/1.0 (+%s)' % REPO_URL
DELAY = 2.0
RAW_MAX = 2 * 1024 * 1024
OUT_DIR = 'data/is-standards'
RAW_DIR = 'raw/is-standards'
SOURCE_URL = KYS + '/indian_standards/isdetails'
INPUTS = ['data/bis/isi_qco.csv', 'data/bis/crs.csv', 'data/bis/scheme_ii_other.csv', 'data/bis/scheme_iv.csv', 'data/bis/scheme_x.csv',
          'data/bis/qco_upcoming.csv', 'data/bis/option2.csv', 'data/qco/register.csv']

COLS = ['is_no', 'is_base', 'part', 'title', 'year', 'status', 'superseded_by', 'supersedes', 'amendments', 'reaffirmed_year',
        'qco_status_label', 'classification', 'committee', 'list_flags', 'match_note', 'pk_is_id', 'source_url', 'fetched_at', 'sha256_detail']
UNMATCHED_COLS = ['is_no', 'is_base', 'part', 'reason', 'candidate_1', 'candidate_2', 'candidate_3', 'fetched_at']
STATUSES = ('current', 'withdrawn', 'superseded', 'unknown')
ROMAN = {'I': 1, 'II': 2, 'III': 3, 'IV': 4, 'V': 5, 'VI': 6, 'VII': 7, 'VIII': 8, 'IX': 9, 'X': 10}


class Failure(Exception):
    pass


class Blocked(Failure):
    """HTTP 403 or 429 (or a robots.txt disallow): stop, keep what was fetched, resume next run."""


# ---- the reference list -------------------------------------------------------------------------------------------------------------

IS_RE = re.compile(r'\bIS(?:/(?:IEC|ISO))?\s*:?\s*(\d{2,6})(?!\d)')
PART_RE = re.compile(r'^\s*[:,\-]?\s*\(?\s*(?:Part|Pt)\.?[\s\-]*(\d+|[IVX]+)\b', re.I)
HYPHEN_RE = re.compile(r'^-(\d+)(?:-\d+)?(?!\d)')


def canon(base, part=''):
    return 'IS %s%s' % (base, (' (Part %s)' % part) if part else '')


def refs_in_text(text):
    """-> [(base, part or '')] in order of first appearance. 'IS 302 (Part 1) : 2024', 'IS 13252(Part 1)', 'IS 302-2-26' (part 2)."""
    out = []
    t = text or ''
    for m in IS_RE.finditer(t):
        tail = t[m.end():m.end() + 24]
        pm = PART_RE.match(tail)
        part = pm.group(1) if pm else ''
        if not pm:
            hm = HYPHEN_RE.match(tail)
            part = hm.group(1) if hm else ''
        if part and not part.isdigit():
            part = str(ROMAN.get(part.upper(), part))
        out.append((m.group(1), part))
    return list(dict.fromkeys(out))


def parse_ref(ref):
    """'IS 302 (Part 1' / 'IS: 9438' / 'IS 8510 (PartIII)' -> (base, part) or None."""
    r = refs_in_text(ref.replace(':', ' ') if re.match(r'\s*IS\s*:', ref) else ref)
    return r[0] if r else None


def split_is_no(is_no):
    m = re.match(r'^IS (\d+)(?: \(Part (\d+)\))?$', is_no)
    return (m.group(1), m.group(2) or '') if m else None


def repo_refs(root=REPO):
    """Every IS number (base, part) named in the BIS lists and the QCO register, sorted by base then part."""
    seen = set()
    for rel in INPUTS:
        p = os.path.join(root, rel)
        if not os.path.isfile(p):
            continue
        with open(p, encoding='utf-8', newline='') as fh:
            for r in csv.DictReader(fh):
                seen.update(refs_in_text(r.get('is_codes', '')))
    return sorted(seen, key=lambda x: (int(x[0]), int(x[1] or 0)))


# ---- parsing ------------------------------------------------------------------------------------------------------------------------

def now():
    return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def fix_mojibake(s):
    if 'â€' in s or 'Ã' in s:
        try:
            return s.encode('cp1252').decode('utf8')
        except Exception:
            return s
    return s


def clean(s):
    s = re.sub(r'<br\s*/?>', ' ; ', s)
    s = re.sub(r'<[^>]+>', ' ', s)
    s = html.unescape(s).replace('\xa0', ' ')
    return fix_mojibake(re.sub(r'\s+', ' ', s).strip(' ;'))


def pick(cands, num, part):
    ok = [c for c in cands if c.get('vc_doc_num') == num and (c.get('is_part') or '').strip() == part and not (c.get('is_sec') or '').strip()]
    if not ok:
        return None, []
    pri = [c for c in ok if (c.get('is_prefix') or '').strip() == 'IS'] or ok

    def key(c):
        y = int(c['is_year']) if str(c.get('is_year', '')).isdigit() else 0
        return (y, 'Amendment' not in c['name'], int(c['id']) if str(c['id']).isdigit() else 0)
    pri.sort(key=key, reverse=True)
    return pri[0], ok


def top3(cands, num, part):
    def score(c):
        return -((10 if c.get('vc_doc_num') == num else 0) + (5 if (c.get('is_part') or '').strip() == part else 0))
    return sorted(cands, key=score)[:3]


def parse_details(page):
    out = {}
    i = page.find('Basic Details')
    j = page.find('Summary', i)
    region = page[i:j] if i >= 0 and j > i else page
    for seg in re.split(r'(?=<label[^>]*\bqs\b)', region):
        m = re.match(r'<label[^>]*\bqs\b[^>]*>\s*([^<]*?)\s*/?\s*<label', seg)
        v = re.search(r'class="[^"]*\brly\b[^"]*"[^>]*>(.*?)</label>\s*(?:</div>|<)', seg, re.S)
        if m and v:
            out[m.group(1).strip().rstrip('/').strip()] = clean(v.group(1))
    a = re.search(r'<a[^>]*data-is_number="([^"]*)"[^>]*data-pk_is_id="(\d+)"[^>]*class="qco_file_details"[^>]*>(.*?)</a>', page, re.S)
    if a:
        out['_qco_label'] = clean(a.group(3))
    k = page.find("id='classificationTr'")
    if k >= 0:
        blk = clean(page[k:k + 6000])
        cl = {}
        stop = (r'(?=(?:Group|Sub Group|Sub Sub Group|Aspect|Certification|Relevant Ministries|Sustainable development Goals|Short Commom|'
                r'ITC-HS Code|Degree of Equivalence|Identical/Equivalent|Email Ids|ICS)\b|$)')
        for lab in ('Group', 'Sub Group', 'Sub Sub Group', 'Aspect', 'Certification', 'Relevant Ministries', "Short Commom Man's Title", 'ITC-HS Code',
                    'Degree of Equivalence', 'ICS', 'ICS Code'):
            mm = re.search(re.escape(lab) + r'\s*:\s*(.*?)\s*' + stop, blk)
            if mm:
                cl[lab] = mm.group(1).strip()
        out['_classification'] = cl
    return out


def status_from_list_row(row):
    """The result LIST row decides: withdrawn flag or '(Withdrawn)' text, 'Superceded by ...' text. -> (status, superseded_by)."""
    blob = row['is_no'] + ' ' + row['title']
    sb = re.search(r'Super[sc]e?ded\s+by\s+([^)]*)\)?', blob, re.I)
    by = sb.group(1).strip() if sb else ''
    if (row.get('w') or '').upper() == 'W' or re.search(r'withdrawn', blob, re.I):
        return 'withdrawn', by
    if sb:
        return 'superseded', by
    return 'current', ''


# ---- transport ----------------------------------------------------------------------------------------------------------------------

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


class Client:
    """One anonymous session. `transport(method, url, data, headers) -> (status, body, location)` is injectable for tests."""

    def __init__(self, transport=None, delay=DELAY, sleep=time.sleep, clock=time.time):
        self.jar = http.cookiejar.CookieJar()
        self.op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar), NoRedirect)
        self.transport = transport or self._http
        self.delay, self.sleep, self.clock = delay, sleep, clock
        self.csrf, self.last, self.requests = None, 0.0, 0

    def _http(self, method, url, data, headers):
        body = urllib.parse.urlencode(data).encode() if data is not None else None
        req = urllib.request.Request(url, data=body, headers=headers, method=method)
        try:
            r = self.op.open(req, timeout=60)
            return r.status, r.read(), ''
        except urllib.error.HTTPError as e:
            return e.code, e.read(), e.headers.get('Location', '')

    def req(self, method, url, data=None, headers=None):
        wait = self.delay - (self.clock() - self.last)
        if wait > 0:
            self.sleep(wait)
        h = {'User-Agent': USER_AGENT, 'Accept': '*/*'}
        h.update(headers or {})
        st, body, loc = self.transport(method, url, data, h)
        self.last = self.clock()
        self.requests += 1
        if st in (403, 429):
            raise Blocked('%s %s -> HTTP %s' % (method, url, st))
        return st, body, loc

    def robots(self):
        st, body, _ = self.req('GET', HOST + '/robots.txt')
        txt = body.decode('utf-8', 'replace')
        if st == 200 and '<html' not in txt[:300].lower():
            rp = urllib.robotparser.RobotFileParser()
            rp.parse(txt.splitlines())
            if not rp.can_fetch(USER_AGENT, KYS + '/') or not rp.can_fetch('*', KYS + '/'):
                raise Blocked('robots.txt disallows %s' % KYS)
        elif st not in (404, 410, 200):
            raise Failure('robots.txt answered HTTP %s; refusing the host' % st)

    def bootstrap(self):
        st, c, _ = self.req('GET', KYS + '/indian_standards/isdetails')
        if st != 200:
            raise Failure('bootstrap answered HTTP %s' % st)
        m = re.search(r'name="csrf_test_name" value="([0-9a-f]{32})"', c.decode('utf-8', 'replace'))
        if not m:
            raise Failure('CSRF token not found on the details page; the layout changed')
        self.csrf = m.group(1)

    def post(self, url, data, ajax=True):
        """POST with the CSRF token; a bounce (3xx) means the session lapsed: one fresh session, one retry."""
        for attempt in (0, 1):
            if not self.csrf:
                self.bootstrap()
            d = {'csrf_test_name': self.csrf}
            d.update(data)
            hdr = {'Referer': KYS + '/indian_standards/isdetails', 'Origin': HOST}
            if ajax:
                hdr['X-Requested-With'] = 'XMLHttpRequest'
            st, c, loc = self.req('POST', url, d, hdr)
            if st in (301, 302, 303, 307) and attempt == 0:
                self.jar.clear()
                self.csrf = None
                continue
            return st, c, loc
        return st, c, loc


def b64(s):
    return base64.b64encode(s.encode()).decode()


def status_list(cl, base, wanted):
    """-> {pk: {'w','is_no','title'}} from the result list for 'IS <base>' (paged until every wanted pk is seen)."""
    url = KYS + '/Indian_standards/searchIS?seachby=%s&txt_search=%s' % (b64('isnumber'), b64('IS %s' % base))
    rows, start, total, step = {}, 0, None, 500
    while (total is None or start < total) and not set(wanted) <= set(rows):
        st, c, _ = cl.post(url, {'draw': '1', 'start': str(start), 'length': str(step)})
        try:
            j = json.loads(c.decode('utf-8', 'replace'))
            total = int(j.get('iTotalDisplayRecords') or j.get('iTotalRecords') or 0)
        except Exception:
            raise Failure('status list for IS %s answered HTTP %s and no JSON' % (base, st))
        for r in j.get('aaData', []):
            mm = re.search(r'choosenIS\((\d+)\)', r.get('Action', ''))
            if mm:
                rows[mm.group(1)] = {'w': r.get('withdrawn_status') or '', 'is_no': clean(r.get('is_no', '')), 'title': clean(r.get('is_title', ''))}
        if not j.get('aaData'):
            break
        start += step
    return rows


def fetch_ref(cl, base, part, search_cache, status_cache):
    """-> (kind, record, html bytes or None). kind is 'matched' or 'unmatched'."""
    text = 'IS %s%s' % (base, (' Part ' + part) if part else '')
    if text not in search_cache:
        st, c, _ = cl.post(KYS + '/Elasticsearch/getsearchAjax', {'search': text, 'type': '1', 'wh': '0'})
        try:
            cands = json.loads(c.decode('utf-8', 'replace')) if st == 200 else None
        except ValueError:
            cands = None
        if not isinstance(cands, list):
            raise Failure('search for %r answered HTTP %s and no JSON list' % (text, st))
        search_cache[text] = [x for x in cands if isinstance(x, dict) and 'vc_doc_num' in x]
    cands = search_cache[text]
    is_no = canon(base, part)
    best, ok = pick(cands, base, part)
    stamp = now()
    if not best:
        cs = ['%s | %s | pk=%s' % (x.get('name'), x.get('is_no'), x.get('id')) for x in top3(cands, base, part)]
        return 'unmatched', {'is_no': is_no, 'is_base': base, 'part': part, 'fetched_at': stamp,
                             'reason': 'no exact number+part match (%d fuzzy candidates)' % len(cands),
                             'candidate_1': (cs + ['', '', ''])[0], 'candidate_2': (cs + ['', '', ''])[1], 'candidate_3': (cs + ['', '', ''])[2]}, None
    pk = str(best['id'])
    st, c, _ = cl.post(KYS + '/Indian_standards/isdetails/', {'pk_is_id': pk, 'search_type': '1', 'wh': '0', 'seachby': 'isnumber', 'txt_search': text},
                       ajax=False)
    if st != 200 or b'Basic Details' not in c:
        return 'unmatched', {'is_no': is_no, 'is_base': base, 'part': part, 'fetched_at': stamp, 'reason': 'details fetch failed, HTTP %s' % st,
                             'candidate_1': '%s | %s | pk=%s' % (best.get('name'), best.get('is_no'), pk), 'candidate_2': '', 'candidate_3': ''}, None
    d = parse_details(c.decode('utf-8', 'replace'))
    amd = []
    nam = d.get('Number of Amendments', '')
    if re.search(r'\d', nam) and not re.search(r'No amendment', nam, re.I) and nam.strip() != '0':
        st2, c2, _ = cl.post(KYS + '/Indian_standards/getamendments?pk_is_id=%s&con_date=&numb_amendments=%s' % (pk, re.sub(r'\D', '', nam)),
                             {'draw': '1', 'start': '0', 'length': '100'})
        try:
            for r in json.loads(c2.decode('utf-8', 'replace')).get('aaData', []):
                amd.append({'number': clean(r.get('AmendmentNumber', '')), 'year': r.get('AmendmentYear'), 'file': r.get('AmdFileName')})
        except Exception:
            raise Failure('amendments list for pk %s answered HTTP %s and no JSON' % (pk, st2))
    if base not in status_cache:
        wanted = {pk}
        status_cache[base] = status_list(cl, base, wanted)
    row = status_cache[base].get(pk)
    if row is None and pk not in status_cache[base]:  # a later ref of the same base may want another pk: page again once
        status_cache[base].update(status_list(cl, base, {pk}))
        row = status_cache[base].get(pk)
    if row:
        status, by = status_from_list_row(row)
        flags = row['is_no']
    else:
        status, by, flags = 'unknown', '', ''
    years = sorted({int(x['is_year']) for x in ok if str(x.get('is_year', '')).isdigit()})
    sup = d.get('Superseding IS', '')
    rea = d.get('Reaffirmation Year', '') or (best.get('reaffirm_year') if best.get('reaffirm_year') not in (None, '0', 0) else '')
    rec = {'is_no': is_no, 'is_base': base, 'part': part, 'title': d.get('IS Title') or best['name'], 'year': str(best.get('is_year', '') or ''),
           'status': status, 'superseded_by': by, 'supersedes': '' if sup == 'None' else sup,
           'amendments': json.dumps(amd, ensure_ascii=False), 'reaffirmed_year': str(rea or ''), 'qco_status_label': d.get('_qco_label', ''),
           'classification': json.dumps(d.get('_classification', {}), ensure_ascii=False), 'committee': d.get('Technical Committee', ''),
           'list_flags': flags, 'pk_is_id': pk,
           'match_note': 'latest edition of %d seen (years %s)%s' % (len(ok), ','.join(map(str, years)), '' if row else '; pk not in result list'),
           'source_url': SOURCE_URL, 'fetched_at': stamp, 'sha256_detail': hashlib.sha256(c).hexdigest()}
    return 'matched', rec, c


# ---- files --------------------------------------------------------------------------------------------------------------------------

def csv_bytes(cols, rows):
    buf = io.StringIO(newline='')
    w = csv.DictWriter(buf, fieldnames=cols, lineterminator='\n', extrasaction='ignore')
    w.writeheader()
    for r in rows:
        w.writerow({c: r.get(c, '') for c in cols})
    return buf.getvalue().encode('utf-8')


def read_table(root, rel):
    p = os.path.join(root, rel)
    if not os.path.isfile(p):
        return []
    with open(p, encoding='utf-8', newline='') as fh:
        return list(csv.DictReader(fh))


def sort_key(r):
    return (int(r['is_base']), int(r['part'] or 0))


def write_atomic(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path + '.tmp', 'wb') as fh:
        fh.write(data)
    os.replace(path + '.tmp', path)


def archive_html(root, today, pk, body):
    """-> (relative path or '', note). Under 2 MB the bytes are archived verbatim; over, hash only."""
    if len(body) >= RAW_MAX:
        return '', 'over 2 MB: hash only'
    rel = '%s/%s/%s.html' % (RAW_DIR, today, pk)
    write_atomic(os.path.join(root, rel), body)
    return rel, ''


def write_sums(root, today):
    d = os.path.join(root, RAW_DIR, today)
    if not os.path.isdir(d):
        return '', 0, 0
    lines, total, n = [], 0, 0
    for fn in sorted(f for f in os.listdir(d) if f.endswith('.html')):
        b = open(os.path.join(d, fn), 'rb').read()
        lines.append('%s  %s' % (hashlib.sha256(b).hexdigest(), fn))
        total += len(b)
        n += 1
    data = ('\n'.join(lines) + '\n').encode()
    write_atomic(os.path.join(d, 'SHA256SUMS.txt'), data)
    return hashlib.sha256(data).hexdigest(), total, n


PROV_COLS = ['file', 'source_url', 'retrieved_on', 'sha256', 'rows', 'source_rows', 'page_date', 'parser', 'raw_file', 'raw_sha256', 'raw_bytes',
             'raw_committed', 'fetch_method', 'fetch_tier', 'fetch_cost_usd']


def write_outputs(root, matched, unmatched, today, want_n, raw_note):
    """standards.csv, unmatched.csv, PROVENANCE.csv. `source_rows` is the number of references this table was asked about."""
    m = sorted(matched.values(), key=sort_key)
    u = sorted(unmatched.values(), key=sort_key)
    mb, ub = csv_bytes(COLS, m), csv_bytes(UNMATCHED_COLS, u)
    write_atomic(os.path.join(root, OUT_DIR, 'standards.csv'), mb)
    write_atomic(os.path.join(root, OUT_DIR, 'unmatched.csv'), ub)
    sums_hash, raw_bytes, raw_n = write_sums(root, today)
    rawdir = '%s/%s/' % (RAW_DIR, today)
    dates = sorted({r['fetched_at'][:10] for r in m + u if r.get('fetched_at')}) or [today]
    prov = []
    for fn, data, rows in (('standards.csv', mb, len(m)), ('unmatched.csv', ub, len(u))):
        prov.append({'file': fn, 'source_url': SOURCE_URL, 'retrieved_on': dates[-1], 'sha256': hashlib.sha256(data).hexdigest(), 'rows': rows,
                     'source_rows': rows, 'page_date': '', 'parser': 'pipeline.adapter_kys',
                     'raw_file': (rawdir if fn == 'standards.csv' and raw_n else ''), 'raw_sha256': sums_hash if fn == 'standards.csv' else '',
                     'raw_bytes': raw_bytes if fn == 'standards.csv' else '', 'raw_committed': ('yes' if raw_n and fn == 'standards.csv' else 'no'),
                     'fetch_method': 'direct', 'fetch_tier': '', 'fetch_cost_usd': ''})
    write_atomic(os.path.join(root, OUT_DIR, 'PROVENANCE.csv'), csv_bytes(PROV_COLS, prov))
    by_status = {k: sum(1 for r in m if r['status'] == k) for k in STATUSES}
    rep = {'references_named_in_this_repository': want_n, 'matched': len(m), 'unmatched': len(u), 'pending_not_yet_fetched': want_n - len(m) - len(u),
           'matched_by_status': by_status,
           'unmatched_search_returned_no_candidates': sum(1 for r in u if '(0 fuzzy' in r['reason']),
           'unmatched_number_found_but_not_this_part': sum(1 for r in u if '(0 fuzzy' not in r['reason']),
           'matched_with_amendments': sum(1 for r in m if json.loads(r['amendments'] or '[]')),
           'matched_with_reaffirmation_year': sum(1 for r in m if r['reaffirmed_year']),
           'matched_with_qco_label': sum(1 for r in m if r['qco_status_label']),
           'matched_with_ics': sum(1 for r in m if json.loads(r['classification'] or '{}').get('ICS')),
           'fetched_from': min([r['fetched_at'][:10] for r in m + u] or ['']), 'fetched_to': max([r['fetched_at'][:10] for r in m + u] or ['']),
           'raw_pages_archived': raw_n, 'raw_bytes': raw_bytes,
           'not_obtainable_from_the_public_page': ['ICS code (the details page shows none)', 'the QCO document list (qco_file_details answers 303 to an anonymous session)',
                                                   'older editions: references carry no year, so the latest edition is matched and an older one is not detected',
                                                   'the text of any standard (BIS copyright; never fetched)']}
    write_atomic(os.path.join(root, OUT_DIR, 'BUILD-REPORT.json'), (json.dumps(rep, indent=1, ensure_ascii=False) + '\n').encode('utf-8'))
    return rep


def seed(root, src_dir, today, log=print):
    """One-off: load the output of the original harvest (standards.csv, UNMATCHED.csv, raw/) without any network request. Only references that
    this repository names are kept; every kept raw page is verified against its recorded hash before it is copied."""
    wanted = set(repo_refs(root))
    matched, unmatched, dropped, bad_hash = {}, {}, 0, 0
    with open(os.path.join(src_dir, 'standards.csv'), encoding='utf-8', newline='') as fh:
        for r in csv.DictReader(fh):
            p = parse_ref(r['is_ref_as_ours'])
            if not p or p not in wanted:
                dropped += 1
                continue
            k = canon(*p)
            body = open(os.path.join(src_dir, 'raw', r['pk_is_id'] + '.html'), 'rb').read()
            if hashlib.sha256(body).hexdigest() != r['sha256_of_detail_html']:
                bad_hash += 1
                continue
            matched[k] = {'is_no': k, 'is_base': p[0], 'part': p[1], 'title': r['title'], 'year': r['year'], 'status': r['status'],
                          'superseded_by': r['superseded_by'], 'supersedes': r['supersedes'], 'amendments': r['amendments'],
                          'reaffirmed_year': r['reaffirmed'], 'qco_status_label': r['qco_status'], 'classification': r['classification'],
                          'committee': r['committee'], 'list_flags': r['list_flags'], 'match_note': r['match_note'], 'pk_is_id': r['pk_is_id'],
                          'source_url': SOURCE_URL, 'fetched_at': r['fetched_at'], 'sha256_detail': r['sha256_of_detail_html']}
            if len(body) < RAW_MAX:
                archive_html(root, r['fetched_at'][:10], r['pk_is_id'], body)
    with open(os.path.join(src_dir, 'UNMATCHED.csv'), encoding='utf-8', newline='') as fh:
        for r in csv.DictReader(fh):
            p = parse_ref(r['is_ref_as_ours'])
            if not p or p not in wanted:
                dropped += 1
                continue
            k = canon(*p)
            if k in matched:
                continue
            unmatched[k] = {'is_no': k, 'is_base': p[0], 'part': p[1], 'reason': r['reason'], 'candidate_1': r['cand1'], 'candidate_2': r['cand2'],
                            'candidate_3': r['cand3'], 'fetched_at': '2026-10-22T00:00:00Z'}
    day = max([v['fetched_at'][:10] for v in matched.values()] or [today])
    s = write_outputs(root, matched, unmatched, day, len(wanted), '')
    s.update(dropped_not_in_repo=dropped, bad_hash=bad_hash, pending=len(wanted) - len(matched) - len(unmatched))
    return s


def load_state(root):
    matched = {r['is_no']: r for r in read_table(root, OUT_DIR + '/standards.csv')}
    unmatched = {r['is_no']: r for r in read_table(root, OUT_DIR + '/unmatched.csv')}
    return matched, unmatched


def plan(wanted, matched, unmatched, today, stale_days):
    """Never-fetched references first (in number order), then the stale ones, oldest first."""
    fresh_after = date.fromisoformat(today).toordinal() - stale_days
    new, old = [], []
    for base, part in wanted:
        k = canon(base, part)
        rec = matched.get(k) or unmatched.get(k)
        if rec is None:
            new.append((base, part))
        else:
            d = (rec.get('fetched_at') or '')[:10]
            if not d or date.fromisoformat(d).toordinal() < fresh_after:
                old.append((d, base, part))
    return new + [(b, p) for _, b, p in sorted(old)]


def run(root=REPO, today=None, refs=None, max_refs=400, stale_days=120, transport=None, dry_run=False, client=None, save_every=25, log=print):
    """-> summary dict. Raises Blocked / Failure after writing what was fetched."""
    today = today or date.today().isoformat()
    wanted = refs if refs is not None else repo_refs(root)
    matched, unmatched = load_state(root)
    todo = plan(wanted, matched, unmatched, today, stale_days)[:max_refs]
    cl = client or Client(transport)
    summary = {'wanted': len(wanted), 'todo': len(todo), 'fetched': 0, 'matched': 0, 'unmatched': 0, 'stopped': ''}
    if not todo:
        return summary
    search_cache, status_cache = {}, {}

    def save():
        if not dry_run:
            write_outputs(root, matched, unmatched, today, len(wanted), '')

    try:
        cl.robots()
        for n, (base, part) in enumerate(todo, 1):
            kind, rec, body = fetch_ref(cl, base, part, search_cache, status_cache)
            k = rec['is_no']
            old = matched.get(k)
            matched.pop(k, None)
            unmatched.pop(k, None)
            if kind == 'matched':
                matched[k] = rec
                summary['matched'] += 1
                changed = old is None or any(old.get(c) != rec[c] for c in ('title', 'year', 'status', 'superseded_by', 'amendments', 'reaffirmed_year'))
                if body is not None and changed and not dry_run:
                    archive_html(root, today, rec['pk_is_id'], body)
            else:
                unmatched[k] = rec
                summary['unmatched'] += 1
            summary['fetched'] += 1
            if n % save_every == 0:
                save()
                log('%d/%d' % (n, len(todo)))
    except (Blocked, Failure) as e:
        summary['stopped'] = str(e)
        save()
        raise
    save()
    return summary


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--root', default=REPO)
    ap.add_argument('--max-refs', type=int, default=400)
    ap.add_argument('--stale-days', type=int, default=120)
    ap.add_argument('--limit', type=int, default=0, help='only the first N references of the list (testing)')
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--seed-from', help='load a finished harvest directory (standards.csv, UNMATCHED.csv, raw/); no network')
    a = ap.parse_args(argv)
    if a.seed_from:
        print(json.dumps(seed(a.root, a.seed_from, date.today().isoformat())))
        return 0
    refs = repo_refs(a.root)
    if a.limit:
        refs = refs[:a.limit]
    try:
        s = run(a.root, refs=refs, max_refs=a.max_refs, stale_days=a.stale_days, dry_run=a.dry_run)
    except Blocked as e:
        print('stopped, resume next run: %s' % e, file=sys.stderr)
        return 3
    except Failure as e:
        print('failed: %s' % e, file=sys.stderr)
        return 1
    print(json.dumps(s))
    return 0


if __name__ == '__main__':
    sys.exit(main())
