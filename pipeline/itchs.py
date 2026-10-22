"""ITC(HS) 2022 Schedule 1 (Import Policy) from the DGFT web app: fetch adapter and parser. Stdlib only.

Each chapter is one JSON document (`getChapterDetails`). `itcCodeClassifications` holds the 4, 6 and 8-digit lines; `notes[]` holds the
chapter policy conditions and related notes. Parsing is a pure function of the archived bytes. Counts are asserted per chapter.
"""
import csv
import datetime
import hashlib
import html as htmllib
import http.cookiejar
import io
import json
import re
import time
import urllib.parse
import urllib.request

from pipeline.adapters import REPO_URL, USER_AGENT, Failure, PoliteFetcher

PERMISSION_REF = 'DGFTCOMS-2026-24H4345L'
PAGE_URL = 'https://www.dgft.gov.in/CP/?opt=itchs-import-export'
LISTING_URL = 'https://www.dgft.gov.in/CP/webHP?requestType=ApplicationRH&screenId=90000802&actionVal=itchsDetails&itchType=import'
API_URL = 'https://www.dgft.gov.in/CP/webHP?requestType=ApplicationRH&screenId=90000802&actionVal=getChapterDetails'
EDITION = 'ITC(HS) 2022 Schedule 1 (Import Policy)'

ROW_COLS = ['hs_code', 'hs6', 'hs6_description', 'level', 'chapter', 'description', 'policy', 'condition_text', 'condition_ref', 'notification_no', 'notification_date', 'as_of']
NOTE_COLS = ['chapter', 'note_type', 'serial_no', 'section', 'text', 'notification_no', 'notification_date', 'as_of']
SECTION_NOTE_COLS = ['section', 'section_name', 'note_type', 'serial_no', 'text', 'notification_no', 'notification_date', 'as_of']
PROV_COLS = ['chapter', 'url', 'method', 'retrieved_at_utc', 'sha256', 'bytes', 'permission_ref', 'rows_in_json']


def text_of(s):
    """HTML stripped, entities decoded, whitespace collapsed; the words are the source's own."""
    if not s:
        return ''
    s = re.sub(r'<br\s*/?>|</p>|</li>|</tr>', ' ', s, flags=re.I)
    s = htmllib.unescape(re.sub(r'<[^>]+>', ' ', s))
    s = s.replace('Â ', ' ').replace(' ', ' ').replace('​', '')  # a doubly-encoded no-break space ("A-circumflex") is whitespace
    return re.sub(r'\s+', ' ', s).strip()


def iso_or_raw(s):
    """dd/mm/yyyy and yyyy-mm-dd[ hh:mm:ss] become yyyy-mm-dd; anything else (two dates, free text) is kept as printed."""
    s = (s or '').strip()
    m = re.fullmatch(r'(\d{1,2})[/.](\d{1,2})[/.](\d{4})', s)
    if m:
        d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        try:
            return datetime.date(y, mo, d).isoformat()
        except ValueError:
            return s
    m = re.fullmatch(r'(\d{4}-\d{2}-\d{2})(?:[ T]\d{2}:\d{2}:\d{2}(?:\.\d+)?)?', s)
    return m.group(1) if m else s


COND_REF = re.compile(r'[Pp]olicy\s+[Cc]ondition(?:s)?\s*(?:[Nn]o\.?\s*)?[(]?\s*0*(\d{1,2})\s*[)]?')


def condition_refs(text):
    return ';'.join(dict.fromkeys(m.group(1) for m in COND_REF.finditer(text)))


def load_hs6(path):
    """-> {hs6: description} from the WCO-nomenclature table in data/hs6 (6-digit lines only)."""
    import csv
    with open(path, newline='', encoding='utf-8') as fh:
        return {r['hs6']: r['description'] for r in csv.DictReader(fh) if len(r['hs6']) == 6}


def add_hs6_descriptions(rows, hs6):
    """Fill hs6_description in place; -> sorted hs6 codes that are not in the table (India-specific splits and chapters 98/99)."""
    missing = set()
    for r in rows:
        if r['hs6']:
            d = hs6.get(r['hs6'])
            if d is None:
                missing.add(r['hs6'])
            r['hs6_description'] = d or ''
    return sorted(missing)


def level_of(code):
    return len(code)


def parse_chapter(body, ch, as_of):
    """-> (rows, notes, section_notes, stats). Raises Failure when the document is not a chapter export or a count disagrees."""
    try:
        d = json.loads(body)
    except ValueError as e:
        raise Failure('itchs ch%s: not JSON (%s)' % (ch, e))
    if not isinstance(d, dict) or d.get('responseCode') != 200 or 'itcCodeClassifications' not in d:
        raise Failure('itchs ch%s: not a getChapterDetails response (layout changed?)' % ch)
    if str(d.get('chapterNo', '')).zfill(2) != ch:
        raise Failure('itchs ch%s: the document says chapter %r' % (ch, d.get('chapterNo')))
    items = d['itcCodeClassifications']
    rows, seen, dups = [], set(), []
    for x in items:
        code = str(x.get('itcCode', '')).strip()
        if not re.fullmatch(r'\d{4}(\d{2}(\d{2})?)?', code):
            raise Failure('itchs ch%s: an item has the code %r, not 4, 6 or 8 digits' % (ch, code))
        if code in seen:
            dups.append(code)  # the export itself lists the code twice; both lines are kept and reported
        seen.add(code)
        cond = text_of(x.get('impCondition'))
        rows.append({
            'hs_code': code, 'hs6': code[:6] if len(code) >= 6 else '', 'hs6_description': '', 'level': level_of(code), 'chapter': ch, 'description': text_of(x.get('itcDescription')),
            'policy': (x.get('impPolicy') or '').strip(), 'condition_text': cond, 'condition_ref': condition_refs(cond),
            'notification_no': (x.get('notificationNo') or '').strip(), 'notification_date': iso_or_raw(x.get('notificationDate')), 'as_of': as_of})
    notes, snotes, sseen = [], [], set()
    n_notes = 0
    for n in d.get('notes') or []:
        for e in n.get('noteDetails') or []:
            n_notes += 1
            notes.append({'chapter': ch, 'note_type': (e.get('notetype') or '').strip(), 'serial_no': str(e.get('noteSerialNo') or '').strip(),
                          'section': (e.get('noteSection') or '').strip(), 'text': text_of(e.get('notes')),
                          'notification_no': (e.get('notificationNo') or '').strip(), 'notification_date': iso_or_raw(e.get('notificationDate')), 'as_of': as_of})
        for e in n.get('noteSectionDetails') or []:
            key = ((e.get('section') or '').strip(), (e.get('notetype') or '').strip(), str(e.get('noteSerialNo') or '').strip(), text_of(e.get('notes')))
            if key in sseen:
                continue
            sseen.add(key)
            snotes.append({'section': key[0], 'section_name': text_of(d.get('sectionName')), 'note_type': key[1], 'serial_no': key[2], 'text': key[3],
                           'notification_no': (e.get('notificationNo') or '').strip(), 'notification_date': iso_or_raw(e.get('notificationDate')), 'as_of': as_of})
    n8 = sum(1 for r in rows if r['level'] == 8)
    # the assertions: every item of the export became a row, every note a note row
    if len(rows) != len(items):
        raise Failure('itchs ch%s: parsed %d rows from %d items' % (ch, len(rows), len(items)))
    if len(notes) != n_notes:
        raise Failure('itchs ch%s: parsed %d notes from %d' % (ch, len(notes), n_notes))
    stats = {'chapter': ch, 'items_in_export': len(items), 'rows_parsed': len(rows), 'rows_8digit': n8,
             'rows_6digit': sum(1 for r in rows if r['level'] == 6), 'rows_4digit': sum(1 for r in rows if r['level'] == 4),
             'duplicate_codes_in_export': dups, 'notes_in_export': n_notes, 'notes_parsed': len(notes), 'chapter_title': text_of(d.get('chapterDesc')), 'section': (d.get('section') or '')}
    return rows, notes, snotes, stats


def csv_bytes(cols, rows):
    buf = io.StringIO(newline='')
    w = csv.DictWriter(buf, fieldnames=cols, lineterminator='\n', extrasaction='ignore')
    w.writeheader()
    for r in rows:
        w.writerow({c: r.get(c, '') for c in cols})
    return buf.getvalue().encode('utf-8')


def chapters_in_listing(html_bytes):
    chs = re.findall(r'class="itchsimport" data-chapterId="(\d+)"', html_bytes.decode('utf-8', 'replace'))
    if not chs:
        raise Failure('itchs: the chapter listing has no chapters (layout changed?)')
    return sorted(set(c.zfill(2) for c in chs))


class DgftSession:
    """Chapter-by-chapter POST, one request a second, robots.txt honoured, the user agent names this repository."""

    def __init__(self, delay=1.0, sleep=time.sleep, clock=time.monotonic, opener=None):
        self.delay, self.sleep, self.clock = delay, sleep, clock
        self.jar = http.cookiejar.CookieJar()
        self.opener = opener or urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar))
        self.last = -1e9
        self.robots = PoliteFetcher(delay=delay, sleep=sleep, clock=clock)

    def _wait(self):
        gap = self.clock() - self.last
        if gap < self.delay:
            self.sleep(self.delay - gap)
        self.last = self.clock()

    def _req(self, url, data=None, csrf=None):
        if not self.robots._rules(url).can_fetch(USER_AGENT, url):
            raise Failure('robots.txt disallows %s' % url)
        self._wait()
        headers = {'User-Agent': USER_AGENT}
        if data is not None:
            headers['Content-Type'] = 'application/x-www-form-urlencoded'
        req = urllib.request.Request(url, data=data, headers=headers)
        with self.opener.open(req, timeout=120) as resp:
            if resp.status != 200:
                raise Failure('HTTP %s from %s' % (resp.status, url))
            return resp.read()

    def listing(self):
        page = self._req(PAGE_URL)
        m = re.search(rb'<meta[^>]*name="_csrf"[^>]*content="([^"]+)"', page) or re.search(rb'<meta[^>]*content="([^"]+)"[^>]*name="_csrf"', page)
        if not m:
            raise Failure('itchs: no CSRF token on the listing page (layout changed?)')
        self.csrf = m.group(1).decode()
        if b'itchsimport' in page:
            return page
        # 2026-10-22: the page became a shell; its chapter table is loaded by the page's own itchsdetails('import') call, which is this GET.
        return self._req(LISTING_URL)

    def chapter(self, ch, tries=3):
        last = None
        for _ in range(tries):
            try:
                body = self._req(API_URL + '&_csrf=' + urllib.parse.quote(self.csrf), data=('itcCode=%s&expType=1' % ch).encode())
                json.loads(body)
                return body
            except Failure:
                raise
            except Exception as e:  # noqa: BLE001
                last = e
                self.sleep(30)
                try:
                    self.listing()
                except Exception:  # noqa: BLE001
                    pass
        raise Failure('itchs ch%s: fetch failed (%s)' % (ch, last))


def provenance_row(ch, body, ts, rows_in_json):
    return {'chapter': ch, 'url': API_URL, 'method': 'POST getChapterDetails itcCode=%s&expType=1' % ch, 'retrieved_at_utc': ts,
            'sha256': hashlib.sha256(body).hexdigest(), 'bytes': len(body), 'permission_ref': PERMISSION_REF, 'rows_in_json': rows_in_json}
