#!/usr/bin/env python3
"""Adapters for the official lists. Stdlib only, plus `pdftohtml` (poppler) for the two PDFs.

Every adapter is fetch -> archive the bytes unchanged -> parse -> rows in the official CSV shape, and every parser is a pure
function of the archived bytes, so it is proved against the archive in raw with a golden test (test_adapter_*.py, golden/).

    adapter_bis.py   parse_scheme1 (isi_qco.csv), parse_scheme2_other (scheme_ii_other.csv), parse_scheme4 (scheme_iv.csv),
                     parse_scheme_x (scheme_x.csv), parse_upcoming (qco_upcoming.csv)
    adapter_pdf.py   parse_simplified (simplified_2024.csv), parse_mtcte (mtcte.csv)
    adapter_bee.py   parse_bee (bee.csv; mandatory and voluntary pages)
    adapters.py      what they share: Parsed, status_of, the table and PDF readers, PoliteFetcher

A parser returns Parsed(rows, source_rows, page_date, notes). `source_rows` is counted from the source itself by a rule that does not
share code with the row builder (the serial cells of the table, or the serial tokens of the PDF); a parser raises Failure when the two
differ, when a row has a shape it does not know, or when the layout it was proved against is gone. Rows are keyed on IS code + name,
never on the serial (C21: a rowspan row once vanished from a serial-keyed scraper).

Status. The page's own words decide, nothing else: a section titled "De-notified" is `de-notified`; a QCO text that says "Withdrawal of"
is `withdrawn`; a QCO text that says "Rescind" (the Gazette's imperative, as the page prints it) is `withdrawn` with the tag
` | Status: rescinded <date as printed>` (a fresh order that replaced a rescinded one is worded
"was rescinded by ... a fresh Notification" and stays active). The date is the one printed after the keyword, as written.

Politeness. `PoliteFetcher` reads robots.txt of a host once (a 404 or an HTML page means no published rules; a disallow is a refusal),
waits two seconds between requests to one host, and sends no cookies. cpcb.nic.in disallows everything, so the EPR lists stay manual.
"""


import collections


import html as htmllib


import os


import re


import subprocess


import tempfile


import time


import urllib.error
import urllib.parse


import urllib.request


import urllib.robotparser


COLS = ['product_name', 'is_codes', 'scheme', 'authority', 'group', 'source_url', 'retrieved_on', 'status', 'notes']


REPO_URL = 'https://github.com/yashodhank/india-import-compliance-data'
USER_AGENT = os.environ.get('ICD_USER_AGENT') or 'india-import-compliance-data/1.0 (+%s)' % REPO_URL


STATUS_TAG = ' | Status: '


CUT = 600  # the QCO text kept in notes (build_bis.py); the register reads the whole text from the archived page


MONTHS = {m: i + 1 for i, m in enumerate(['jan', 'feb', 'mar', 'apr', 'may', 'jun', 'jul', 'aug', 'sep', 'oct', 'nov', 'dec'])}


DATE_NAMED = re.compile(r'(\d{1,2})\s*(?:st|nd|rd|th)?[\s\-]*(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s*,?[\s\-]*(\d{4})', re.I)


DATE_NUM = re.compile(r'(?<!\d)(\d{1,2})\s*[./-]\s*(\d{1,2})\s*[./-]\s*(\d{4})(?!\d)')


SERIAL = re.compile(r'^\d+(?:\.\d+)*\s*\.?\s*(?:\(?[a-z]\)?)?\.?$')


class Failure(Exception):
    """The refresh stops and nothing is kept."""


class NoStructure(Failure):
    """A 200 body that lacks the structure the adapter expects (fewer tables than expected, no rows). Until proven otherwise this is a FETCH problem
    (a block page or a JavaScript shell served to a datacenter address), so the refresh re-fetches the source through the paid fallback before it
    gives up and keeps the source's last good data as stale. A body that has the tables but the wrong columns is a plain Failure."""


class Parsed(collections.namedtuple('Parsed', 'rows source_rows page_date notes')):
    pass


def clean(s):
    return re.sub(r'\s+', ' ', s or '').strip()


def printed_dates(text):
    """Every date written in the text: (start, end, iso), in order, as the Gazette writes them (day first)."""
    found = []
    for m in DATE_NAMED.finditer(text):
        found.append((m.start(), m.end(), int(m.group(3)), MONTHS[m.group(2).lower()[:3]], int(m.group(1))))
    for m in DATE_NUM.finditer(text):
        found.append((m.start(), m.end(), int(m.group(3)), int(m.group(2)), int(m.group(1))))
    out = []
    for s, e, y, mo, d in sorted(found):
        if out and s < out[-1][1]:
            continue
        if 1 <= mo <= 12 and 1 <= d <= 31 and 1900 <= y <= 2100:
            out.append((s, e, '%04d-%02d-%02d' % (y, mo, d)))
    return out


def row(url, today, **kw):
    r = {c: '' for c in COLS}
    r.update(source_url=url, retrieved_on=today, status='active')
    r.update(kw)
    return r


def html_tables(body):
    """Every <table> of a page as a list of rows; a row is a list of (text, [hrefs]). Same reading as tbl.py."""
    h = body.decode('utf-8', errors='replace') if isinstance(body, bytes) else body
    out = []
    for t in re.findall(r'<table.*?</table>', h, flags=re.S):
        rows = []
        for tr in re.findall(r'<tr.*?</tr>', t, flags=re.S):
            cells = []
            for td in re.findall(r'<t[dh][^>]*>(.*?)</t[dh]>', tr, flags=re.S):
                links = re.findall(r'href="([^"]+)"', td)
                cells.append((clean(htmllib.unescape(re.sub(r'<[^>]+>', ' ', td))), links))
            rows.append(cells)
        out.append(rows)
    return out


class GridRow(list):
    """One <tr> laid out on the table's columns: a list of (text, [hrefs]) per logical column. A cell that a rowspan from an earlier row
    covers is filled in from the row that owns it (`covered[i]` is True), so a row that holds only its own product still has its serial, IS
    code and notification. `own` is how many <td> the <tr> itself holds."""

    own = 0
    covered = ()


def html_grid(body):
    """Every <table> of a page as a list of GridRow, rowspans and colspans honoured. A colspan cell is one logical cell."""
    h = body.decode('utf-8', errors='replace') if isinstance(body, bytes) else body
    out = []
    for t in re.findall(r'<table.*?</table>', h, flags=re.S):
        rows, active = [], {}
        for tr in re.findall(r'<tr.*?</tr>', t, flags=re.S):
            own = [(m.group(1), m.group(2)) for m in re.finditer(r'<t[dh]([^>]*)>(.*?)</t[dh]>', tr, flags=re.S)]
            row_, cov, col, k = GridRow(), [], 0, 0
            used = []
            while k < len(own) or col in active:
                if col in active:
                    row_.append(active[col][1])
                    cov.append(True)
                    used.append(col)
                    col += 1
                    continue
                attrs, inner = own[k]
                k += 1
                links = re.findall(r'href="([^"]+)"', inner)
                cell = (clean(htmllib.unescape(re.sub(r'<[^>]+>', ' ', inner))), links)
                rs = re.search(r'rowspan\s*=\s*"?(\d+)', attrs)
                cs = re.search(r'colspan\s*=\s*"?(\d+)', attrs)
                row_.append(cell)
                cov.append(False)
                if rs and int(rs.group(1)) > 1:
                    active[col] = [int(rs.group(1)) - 1, cell]  # rows still to cover after this one
                col += int(cs.group(1)) if cs else 1
            for c in used:
                active[c][0] -= 1
                if active[c][0] <= 0:
                    del active[c]
            row_.own, row_.covered = len(own), tuple(cov)
            rows.append(row_)
        out.append(rows)
    return out


def page_date(body):
    """The page's own 'Last Updated on <Month D, YYYY>' as an ISO date; '' when the page prints none."""
    h = body.decode('utf-8', errors='replace') if isinstance(body, bytes) else body
    m = re.search(r'Last Updated on\s+([A-Za-z]+)\s+(\d{1,2}),\s*(\d{4})', h)
    if not m or m.group(1)[:3].lower() not in MONTHS:
        return ''
    return '%04d-%02d-%02d' % (int(m.group(3)), MONTHS[m.group(1)[:3].lower()], int(m.group(2)))


def serial_rows(table):
    """Data rows of a table: below the header, three cells or more, something written beyond the first cell. A row with no serial but a
    product counts (the Scheme-I page has 72), a section title (one or two cells) and a blank spacer do not. The count the parsers are held to."""
    return sum(1 for r in table[1:] if len(r) >= 3 and any(c[0] for c in r[1:]))


def need_tables(body, shapes, what):
    ts = html_tables(body)
    if len(ts) < len(shapes):
        raise NoStructure('%s: %d tables on the page, %d expected (layout changed?)' % (what, len(ts), len(shapes)))
    for i, head in enumerate(shapes):
        got = [c[0].lower() for c in ts[i][0]] if ts[i] else []
        if not all(any(w in g for g in got) for w in head):
            raise Failure('%s: table %d header is %r, expected cells like %r (layout changed?)' % (what, i, got, head))
    return ts


def count_check(what, parsed, expected):
    if parsed != expected:
        raise Failure('%s: parsed %d rows but the source table has %d (a row has a shape the parser does not know)' % (what, parsed, expected))


_RESCIND = re.compile(r'\bwithdrawal of\b|\brescind(?:s|ed)?\b', re.I)
_ORDER = re.compile(r'Order,?\s*20\d\d\b[^.]{0,80}?S\.?\s?O\.?\s*(?:No\.?)?\s*\d+', re.I)
_FRESH = re.compile(r'\ba\s+fresh\s+(?:Notification|Order)\b', re.I)


def status_of(section, text):
    """(status, tag) from the page's own words. tag is ' | Status: ...' with the date as printed, or ''.

    The row's chronologically LAST event decides. Events: a rescission or withdrawal (with the date printed after it), and an order (an Order, 20yy with its S.O. number,
    or "a fresh Notification/Order") that is not itself the order being rescinded. Events are ordered by their printed date; the same day, or a missing date,
    keeps the order of the text (the Gazette list is chronological). Rescinded then replaced is live (Footwear: 3 June 2022, amended to 2026); replaced then
    rescinded is withdrawn; "fresh" in the product's own wording is no event."""
    t = text or ''
    if 'de-notified' in (section or '').lower():
        return 'de-notified', ''
    events = []  # (position, kind, iso date or '', printed date text)
    covered = []  # text ranges that belong to a rescission clause: the order named there is the one being rescinded
    for m in _RESCIND.finditer(t):
        d = printed_dates(t[m.end():])
        end = m.end() + (d[0][1] if d else 0)
        events.append((m.start(), 'rescind', d[0][2] if d else '', t[m.end():][d[0][0]:d[0][1]].strip() if d else ''))
        covered.append((m.start(), end))
    for m in list(_ORDER.finditer(t)) + list(_FRESH.finditer(t)):
        if any(a <= m.start() < b for a, b in covered):
            continue
        d = printed_dates(t[m.end():m.end() + 160])
        events.append((m.start(), 'order', d[0][2] if d else '', ''))
    rescinds = [e for e in events if e[1] == 'rescind']
    if not rescinds:
        return 'active', ''
    # A "fresh" notice only replaces when it follows a rescission; one in the product's own wording before any rescission is ignored.
    first = min(e[0] for e in rescinds)
    events = [e for e in events if e[1] == 'rescind' or e[0] > first]

    def key(e):
        return (e[2] or '', e[0]) if all(x[2] for x in events) else (0, e[0])

    last = sorted(events, key=key)[-1]
    if last[1] == 'order':
        return 'active', ''
    word = 'withdrawn' if t[last[0]:].lower().startswith('withdrawal') else 'rescinded'
    return 'withdrawn', STATUS_TAG + word + (' ' + last[3] if last[3] else (' (no date printed)' if word == 'rescinded' else ''))


def pdf_items(body):
    """[(page, top, left, width, text)] of a PDF. Raises Failure when pdftohtml is missing or the file has no text."""
    with tempfile.TemporaryDirectory(prefix='sm-pdf-') as d:
        src = os.path.join(d, 'in.pdf')
        with open(src, 'wb') as fh:
            fh.write(body)
        try:
            p = subprocess.run(['pdftohtml', '-xml', '-i', '-stdout', '-q', src], capture_output=True, timeout=180)
        except FileNotFoundError:
            raise Failure('pdftohtml (poppler-utils) is not installed')
        if p.returncode != 0:
            raise Failure('pdftohtml failed (exit %d): %s' % (p.returncode, p.stderr.decode('utf-8', 'replace')[-300:]))
    xml = p.stdout.decode('utf-8', 'replace')
    items, page = [], 0
    for m in re.finditer(r'<page number="(\d+)"|<text top="(\d+)" left="(\d+)" width="(\d+)"[^>]*>(.*?)</text>', xml, flags=re.S):
        if m.group(1):
            page = int(m.group(1))
            continue
        text = htmllib.unescape(re.sub(r'<[^>]+>', '', m.group(5))).replace('\u202d', '').replace('\u202c', '').strip()  # inner spaces kept: two in a row can mean two cells
        if text:
            items.append((page, int(m.group(2)), int(m.group(3)), int(m.group(4)), text))
    if not items:
        raise Failure('the PDF has no text layer')
    return items


def split_serial_items(items, serial_max_left):
    """One text item can hold the serial and the next cell ("137   IS 16098 (Part 1)"): cut it in two, at the first run of spaces."""
    out = []
    for pg, top, left, width, text in items:
        m = re.match(r'^(\d{1,4})\s{2,}(\S.*)$', text) if left < serial_max_left else None
        if m:
            out.append((pg, top, left, 20, m.group(1)))
            out.append((pg, top, serial_max_left + 1, width, m.group(2)))
        else:
            out.append((pg, top, left, width, text))
    return out


PDF_HEADER_WORDS = {'Sr. No.', 'IS Number', 'Product/Title'}


def serial_tokens(items, serial_max_left, wide):
    """How many serial numbers the PDF prints, counted over a wider band than the one the row builder reads (`wide` > `serial_max_left`), so a
    serial that has slipped out of the first column is in this count and not in the rows, and the two disagree."""
    return sum(1 for it in split_serial_items(items, serial_max_left) if it[2] < wide and re.fullmatch(r'\d{1,4}', it[4]))


def pdf_rows(items, serial_max_left, dropped=None, header_words=PDF_HEADER_WORDS, column_of=None, chain_gap=0):
    """Group items into table rows. A serial is a number in the first column; every other item belongs to the serial nearest to it on the page
    (the cells are centred on the row, so a wrapped cell has lines above and below the serial's own line)."""
    dropped = [] if dropped is None else dropped
    by_page = collections.defaultdict(list)
    for it in split_serial_items(items, serial_max_left):
        by_page[it[0]].append(it)
    rows, pending = [], []
    first_page = min((pg for pg in by_page if any(it[2] < serial_max_left and re.fullmatch(r'\d{1,4}', it[4]) for it in by_page[pg])), default=0)
    for pg in sorted(by_page):
        its = by_page[pg]
        serials = [it for it in its if it[2] < serial_max_left and re.fullmatch(r'\d{1,4}', it[4])]
        if not serials:
            continue
        mine = collections.defaultdict(list)
        ordered_first_top = min(x[1] for x in serials)
        chain_serial = {}
        if column_of and chain_gap:
            # Lines of one cell are closer together than rows are: chain them per column, and give the whole chain to the serial nearest its middle
            # (a serial printed at the top of a tall row would otherwise claim only the lines level with it).
            percol = collections.defaultdict(list)
            for it in its:
                if it not in serials and it[4] not in header_words:
                    percol[column_of(it)].append(it)
            for col_items in percol.values():
                col_items.sort(key=lambda i: i[1])
                chain = []
                for it in col_items + [None]:
                    if chain and (it is None or it[1] - chain[-1][1] > chain_gap):
                        mid = sum(c[1] for c in chain) / len(chain)
                        target = min(serials, key=lambda s: abs(s[1] - mid))
                        for c in chain:
                            chain_serial[id(c)] = target
                        chain = []
                    if it is not None:
                        chain.append(it)
        for it in its:
            if it in serials:
                continue
            nearest = chain_serial.get(id(it)) or min(serials, key=lambda s: abs(s[1] - it[1]))
            if it[4] in header_words or (pg == first_page and it[1] < ordered_first_top - 25):
                continue
            if abs(nearest[1] - it[1]) > 50 or (it[4].startswith('(*)') and it[3] > 300):
                dropped.append(it[4])  # a footnote under the table, not a cell
                continue
            mine[(nearest[1], nearest[4])].append(it)
        ordered = sorted(serials, key=lambda s: s[1])
        built = []
        for s in ordered:
            built.append([pg, s[4], list(mine[(s[1], s[4])]), s[1]])
        # A cell can run over a page break. Lines sit symmetrically about the serial, so a first row with more distinct lines above its serial than
        # below has its extra top lines from the previous page's last row, and a last row with more below than above hands its extra bottom lines on.
        def lines(tops):
            """Distinct text lines: tops within 4 px are one line (cells in one row are not aligned to the pixel)."""
            out = []
            for t in sorted(tops):
                if not out or t - out[-1] > 4:
                    out.append(t)
            return out

        def split(row_, side):
            above = side == 'above'
            mine_ = lines(i[1] for i in row_[2] if (i[1] < row_[3] - 3 if above else i[1] > row_[3] + 3))
            other = lines(i[1] for i in row_[2] if (i[1] > row_[3] + 3 if above else i[1] < row_[3] - 3))
            mine_ = sorted(mine_, reverse=above)  # nearest the serial first
            keep = len(other)
            far = mine_[keep:]
            moved = [i for i in row_[2] if any(abs(i[1] - t) <= 4 for t in far) and (i[1] < row_[3] - 3 if above else i[1] > row_[3] + 3)]
            row_[2] = [i for i in row_[2] if i not in moved]
            return moved
        if rows and built:
            moved = split(built[0], 'above')
            if moved:
                rows[-1][2].extend(moved)
        if pending and built:
            built[0][2] = pending + built[0][2]
            pending = []
        if built:
            pending = split(built[-1], 'below') if pg != max(by_page) else []
        rows.extend(built)
    for r in rows:
        r[2] = sorted(r[2], key=lambda i: (i[0], i[1], i[2]))
    return [(r[0], r[1], r[2]) for r in rows]


class PoliteFetcher:
    """GET with robots.txt honoured and two seconds between the end of one request and the start of the next to the same host.
    `sleep`, `opener`, `urlopen` and `clock` are injectable for tests.

    robots.txt: any 4xx (RFC 9309: "unavailable"), or a 200 that is an HTML page, means no published rules. A 5xx or a transport error
    means we cannot tell what is allowed, so nothing is fetched from that host. Only the `*` record is read (this fetcher has no product token)."""

    def __init__(self, delay=2.0, sleep=time.sleep, opener=None, clock=time.monotonic, timeout=60, urlopen=urllib.request.urlopen):
        self.delay, self.sleep, self.clock, self.timeout, self.urlopen = delay, sleep, clock, timeout, urlopen
        self.opener = opener or self._open
        self.robots, self.last = {}, {}

    def _open(self, url):
        req = urllib.request.Request(url, headers={'User-Agent': USER_AGENT, 'Accept': '*/*'})
        with self.urlopen(req, timeout=self.timeout) as resp:  # noqa: S310 (https URLs from our own manifest)
            return resp.status, resp.headers.get('Content-Type', ''), resp.read(16 * 1024 * 1024)

    def _get(self, url):
        """One request, spaced from the previous one to the same host, and stamped when its answer has arrived."""
        host = urllib.parse.urlsplit(url).netloc
        gap = self.clock() - self.last.get(host, -1e9)
        if gap < self.delay:
            self.sleep(self.delay - gap)
        try:
            return self.opener(url)
        finally:
            self.last[host] = self.clock()

    def _rules(self, url):
        u = urllib.parse.urlsplit(url)
        host = u.scheme + '://' + u.netloc
        if host not in self.robots:
            rp = urllib.robotparser.RobotFileParser()
            lines = []
            try:
                status, ctype, body = self._get(host + '/robots.txt')
            except urllib.error.HTTPError as e:
                if not 400 <= e.code <= 499:
                    raise Failure('robots.txt of %s answered HTTP %s: nothing is fetched from it' % (u.netloc, e.code))
                status, ctype, body = e.code, '', b''  # RFC 9309 2.3.1.3: a 4xx means the file is unavailable, so there are no rules (not a refusal)
            except Exception as e:  # noqa: BLE001
                raise Failure('robots.txt of %s could not be read (%s): nothing is fetched from it' % (u.netloc, e))
            text = body.decode('utf-8', 'replace')
            if status == 200 and 'html' not in ctype.lower() and not re.search(r'<\s*(html|body)\b', text[:500], re.I):
                lines = text.splitlines()
            elif status != 200 and not 400 <= status <= 499:
                raise Failure('robots.txt of %s answered HTTP %s: nothing is fetched from it' % (u.netloc, status))
            rp.parse(lines)
            self.robots[host] = rp
        return self.robots[host]

    def __call__(self, url, tries=3):
        if not self._rules(url).can_fetch('*', url):
            raise Failure('robots.txt disallows %s' % url)
        last = None
        for _ in range(tries):  # a transport error is retried; an answer, good or bad, is final
            try:
                status, _, body = self._get(url)
            except Failure:
                raise
            except urllib.error.HTTPError as e:
                raise Failure('HTTP %s from %s' % (e.code, url))
            except Exception as e:  # noqa: BLE001 (any transport fault is a failed fetch)
                last = e
                continue
            if status != 200:
                raise Failure('HTTP %s from %s' % (status, url))
            if not body.strip():
                raise Failure('empty body from %s' % url)
            return body
        raise Failure('fetch failed for %s: %s' % (url, last))
