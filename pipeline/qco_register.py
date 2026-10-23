"""Derive the QCO register from the published BIS lists. Stdlib only. Idempotent.

Reads  data/bis/{isi_qco,qco_upcoming,crs}.csv and the archived Scheme-I page (whole QCO text)
Returns register, events and products rows (see qco_outputs); gazette_pdf_sha256 comes from data/qco/gazette-pdf-hashes.csv

Rules (no invented facts):
- The Scheme-I notes are stored cut at 600 characters. Where the archived Scheme-I page (raw/bis-scheme1) holds the whole text for the
  row (keyed on IS code + product name) and starts with the cut text, the whole text is used and the record is not truncated. A record whose text
  still reaches the cut is flagged `history_truncated` and its last, cut fragment is not turned into an event.
- A register record is one QCO line of the BIS Scheme-I list (rows that carry the same QCO text are one record), one row of the
  upcoming list, or the CRS list as a whole.
- An event is a stretch of the source QCO text that ends in a date written in the source. Its date is that date, its text is the
  stretch itself, its source is the first official row that carries it. Text with no date after it becomes an event with an empty date.
- An event kind is read from words in its own text only: rescind/withdraw, extension, superseded, exemption, amend/corrigendum.
  The first event of a record is its notification unless its own text says otherwise.
- State is the list's own status for the record (active = in force, upcoming = notified, withdrawn, de-notified). `extended` and
  `rescinded` are flags set only when an event of that kind exists. Nothing is computed from today's date.
- ministry is copied from the source only (upcoming list, CRS list). The Scheme-I list does not state one: it stays empty.
"""
import collections
import csv
import html
import io
import re
import unicodedata

MONTHS = {m: i + 1 for i, m in enumerate(['jan', 'feb', 'mar', 'apr', 'may', 'jun', 'jul', 'aug', 'sep', 'oct', 'nov', 'dec'])}
DATE_NAMED = re.compile(r'(\d{1,2})\s*(?:st|nd|rd|th)?[\s\-]*(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?,?[\s\-]*(\d{4})', re.I)
DATE_NUM = re.compile(r'(?<!\d)(\d{1,2})\s*[./-]\s*(\d{1,2})\s*[./-]\s*(\d{4})(?!\d)')

REGISTER_COLS = ['slug', 'list', 'list_serial', 'title', 'ministry', 'sector', 'state', 'extended', 'rescinded', 'is_codes',
                 'history_truncated', 'product_count', 'first_date', 'latest_date', 'source_file', 'source_url', 'retrieved_on', 'source_rows', 'pdf_urls', 'gazette_pdf_sha256']
EVENT_COLS = ['slug', 'seq', 'date', 'kind', 'text', 'source_file', 'source_row', 'source_url', 'retrieved_on']
PRODUCT_COLS = ['slug', 'product_name', 'is_codes', 'status', 'sector', 'enforcement_date', 'source_file', 'source_row']


def rd(data, name):
    return list(csv.DictReader(io.StringIO(data[name].decode('utf-8'), newline='')))


def scheme1_fulltext(page):
    """{(IS code, product name): {'qco_text': whole QCO text}} from the archived Scheme-I page, keyed as the list is (never on the serial)."""
    h = page.decode('utf-8', 'replace')
    m = re.search(r'<table.*?</table>', h, flags=re.S)
    if not m:
        return {}
    out, notif = {}, ''
    for tr in re.findall(r'<tr.*?</tr>', m.group(0), flags=re.S):
        c = [re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', ' ', td))).strip() for td in re.findall(r'<t[dh][^>]*>(.*?)</t[dh]>', tr, flags=re.S)]
        if (c and c[0] == 'Sr No.') or len(c) <= 2 or not c[1]:
            if len(c) <= 2:
                notif = ''
            continue
        if len(c) >= 4 and c[3]:
            notif = c[3]
        out[(c[1], c[2])] = {'qco_text': notif}
    return out


def find_dates(text):
    """Every date written in the text: (start, end, iso). Named months and d/m/y numerals; day-first, as the Gazette writes them."""
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


def kind_of(text, first):
    t = text.lower()
    if re.search(r'rescind|rescission|withdraw|de-notif', t):
        return 'rescinded'
    if 'extension' in t:
        return 'extended'
    if first:
        return 'notified'
    if 'supersed' in t:
        return 'superseded'
    if 'exemption' in t:
        return 'exemption'
    if re.search(r'amend|corrigend', t):
        return 'amended'
    return 'order'


def clean(s):
    s = re.sub(r'\s+', ' ', s).strip().lstrip(' ,;)')
    s = re.sub(r'^QCO:\s*', '', s)
    s = re.sub(r'^\d{1,3}\s*\.\s+', '', s)
    return s.strip(' ,;').lstrip(' ,;)')


# Until 2026-10-23 a Scheme-I QCO text was stored cut at 600 characters; older rows are completed from the archived page, and a longer history is cut mid-sentence.
CUT_AT = 600


def split_events(text, truncated=False):
    """Stretches of the QCO text that end in a date, then any undated tail."""
    events, prev = [], 0
    for s, e, iso in find_dates(text):
        seg = clean(text[prev:e])
        if seg:
            events.append((iso, seg))
        prev = e
    tail = clean(text[prev:])
    if not truncated and re.search(r'[A-Za-z]{4,}', tail) and len(tail) > 12:
        events.append(('', tail))
    return events


def title_of(text):
    t = clean(text)
    m = re.search(r'^(.*?\bOrder\b\s*,?\s*(?:\(?\s*)?\d{4})', t, re.I)
    if m and len(m.group(1)) <= 160:
        return m.group(1).strip(' ,(')
    m = re.search(r'^(.*?)(?=\s*[(,]?\s*(?:S\.?\s?O\.?|G\.?S\.?R\.?)\b)', t)
    if m and len(m.group(1)) >= 6:
        return m.group(1).strip(' ,(')
    return t[:110].strip(' ,(')


def slugify(s):
    s = unicodedata.normalize('NFKD', s).encode('ascii', 'ignore').decode()
    s = re.sub(r'[^a-z0-9]+', '-', s.lower()).strip('-')
    return s[:80].strip('-') or 'qco'


def serial_of(text):
    m = re.match(r'^\s*QCO:\s*(\d{1,3})\s*\.', text)
    return m.group(1) if m else ''


def uniq(seq):
    return list(dict.fromkeys(x for x in seq if x))


def build(data, scheme1_page, gazette):
    """data: {'isi_qco.csv': bytes, 'qco_upcoming.csv': bytes, 'crs.csv': bytes}; gazette: {pdf url: sha256}. -> (register, events, products)."""
    reg, ev, prod, used = [], [], [], set()

    def slug_for(base):
        s, n = base, 2
        while s in used or s in ('state-of-qcos', 'register'):
            s = '%s-%d' % (base, n)
            n += 1
        used.add(s)
        return s

    # ---- Scheme-I list: rows with the same QCO text are one record
    rows = rd(data, 'isi_qco.csv')
    full = scheme1_fulltext(scheme1_page)

    def body_of(r):
        b = r['notes'].split(' | QCO PDF:')[0].split(' | Status:')[0]  # ' | Status: ...' is the refresh adapter's own tag (adapters.status_of), not QCO text
        f = full.get((r['is_codes'], r['product_name']))
        if f and len(clean(b)) >= CUT_AT - 8 and len(f['qco_text']) > len(b) - 5:
            squash = lambda x: re.sub(r'\s+', ' ', x).strip()
            head = squash(re.sub(r'^\s*QCO:\s*', '', b))
            if squash(f['qco_text']).startswith(head[:CUT_AT - 20]):
                return 'QCO: ' + f['qco_text']
        return b

    groups = collections.OrderedDict()
    for i, r in enumerate(rows, start=2):  # csv line number, header is line 1
        key = re.sub(r'[^a-z0-9]+', '', clean(body_of(r)).lower())
        groups.setdefault(key, []).append((i, r))
    for key, members in groups.items():
        first_row = members[0][1]
        body = body_of(first_row)
        pdfs = uniq(u.strip() for u in (first_row['notes'].split(' | QCO PDF:')[1].split(' | Status:')[0] if ' | QCO PDF:' in first_row['notes'] else '').split(';'))
        title = title_of(body)
        slug = slug_for(slugify(title))
        statuses = collections.Counter(r['status'] for _, r in members)
        state = {'active': 'in_force', 'withdrawn': 'withdrawn', 'de-notified': 'de_notified'}[statuses.most_common(1)[0][0]]
        # only a text this file holds cut (notes written before 2026-10-23 stopped at 600 characters) AND the archived page cannot complete is flagged
        truncated = (full.get((first_row['is_codes'], first_row['product_name'])) is None
                     and len(clean(body)) == len(clean(first_row['notes'].split(' | QCO PDF:')[0].split(' | Status:')[0])) and len(clean(body)) >= CUT_AT - 8)
        events = split_events(body, truncated)
        evs = []
        for n, (iso, seg) in enumerate(events):
            evs.append({'slug': slug, 'seq': n + 1, 'date': iso, 'kind': kind_of(seg, n == 0), 'text': seg[:600],
                        'source_file': 'isi_qco.csv', 'source_row': members[0][0], 'source_url': first_row['source_url'],
                        'retrieved_on': first_row['retrieved_on']})
        ev.extend(evs)
        dates = sorted(e['date'] for e in evs if e['date'])
        reg.append({
            'slug': slug, 'list': 'isi_qco', 'list_serial': serial_of(body) or next((serial_of(r['notes']) for _, r in members if serial_of(r['notes'])), ''),
            'title': title, 'ministry': '', 'sector': ' ; '.join(uniq(r['group'] for _, r in members)), 'state': state,
            'extended': 'true' if any(e['kind'] == 'extended' for e in evs) else 'false',
            'rescinded': 'true' if any(e['kind'] == 'rescinded' for e in evs) else 'false',
            'is_codes': ' ; '.join(uniq(c.strip() for _, r in members for c in r['is_codes'].split(';'))),
            'history_truncated': 'true' if truncated else 'false',
            'product_count': len(members), 'first_date': dates[0] if dates else '', 'latest_date': dates[-1] if dates else '',
            'source_file': 'isi_qco.csv', 'source_url': first_row['source_url'], 'retrieved_on': first_row['retrieved_on'],
            'source_rows': '%d-%d' % (members[0][0], members[-1][0]) if len(members) > 1 else str(members[0][0]),
            'pdf_urls': ' ; '.join(pdfs), 'gazette_pdf_sha256': ' ; '.join(gazette.get(u, '') for u in pdfs)})
        for i, r in members:
            prod.append({'slug': slug, 'product_name': r['product_name'], 'is_codes': r['is_codes'], 'status': r['status'],
                         'sector': r['group'], 'enforcement_date': '', 'source_file': 'isi_qco.csv', 'source_row': i})

    # ---- Upcoming list: one record per row, its own enforcement date
    for i, r in enumerate(rd(data, 'qco_upcoming.csv'), start=2):
        m = re.search(r'Enforcement date:\s*(.+?)\s*(?:\||$)', r['notes'])
        dates = find_dates(m.group(1)) if m else []
        iso = dates[0][2] if dates else ''
        slug = slug_for(slugify(r['product_name']))
        ministry = re.sub(r'\s*/\s*BIS\s*$', '', r['authority']).strip()
        text = ('Enforcement date: ' + m.group(1).strip()) if m else r['notes']
        ev.append({'slug': slug, 'seq': 1, 'date': iso, 'kind': 'enforcement', 'text': text, 'source_file': 'qco_upcoming.csv', 'source_row': i,
                   'source_url': r['source_url'], 'retrieved_on': r['retrieved_on']})
        reg.append({'slug': slug, 'list': 'qco_upcoming', 'list_serial': (re.search(r'List serial (\d+)', r['notes']) or [None, ''])[1],
                    'title': r['product_name'], 'ministry': ministry, 'sector': '', 'state': 'notified', 'extended': 'false', 'rescinded': 'false',
                    'is_codes': r['is_codes'], 'history_truncated': 'false', 'product_count': 1, 'first_date': iso, 'latest_date': iso, 'source_file': 'qco_upcoming.csv',
                    'source_url': r['source_url'], 'retrieved_on': r['retrieved_on'], 'source_rows': str(i), 'pdf_urls': '', 'gazette_pdf_sha256': ''})
        prod.append({'slug': slug, 'product_name': r['product_name'], 'is_codes': r['is_codes'], 'status': r['status'], 'sector': '',
                     'enforcement_date': iso, 'source_file': 'qco_upcoming.csv', 'source_row': i})

    # ---- CRS list: one record, one event per distinct implementation date
    crs = rd(data, 'crs.csv')
    slug = slug_for('compulsory-registration-scheme-crs')
    by_date = collections.OrderedDict()
    for i, r in enumerate(crs, start=2):
        by_date.setdefault(r['enforcement_date'], []).append(i)
        prod.append({'slug': slug, 'product_name': r['product_name'], 'is_codes': r['is_codes'], 'status': r['status'], 'sector': '',
                     'enforcement_date': r['enforcement_date'], 'source_file': 'crs.csv', 'source_row': i})
    for n, (iso, lines) in enumerate(sorted(by_date.items(), key=lambda kv: (kv[0] == '', kv[0])), start=1):
        ev.append({'slug': slug, 'seq': n, 'date': iso, 'kind': 'enforcement',
                   'text': 'Date of implementation of QCO for %d product%s on the CRS list' % (len(lines), '' if len(lines) == 1 else 's'),
                   'source_file': 'crs.csv', 'source_row': lines[0], 'source_url': crs[0]['source_url'], 'retrieved_on': crs[0]['retrieved_on']})
    ds = sorted(d for d in by_date if d)
    reg.append({'slug': slug, 'list': 'crs', 'list_serial': '', 'title': 'Compulsory Registration Scheme (CRS) product list',
                'ministry': re.sub(r'\s*/\s*BIS.*$', '', crs[0]['authority']).strip(), 'sector': crs[0]['group'], 'state': 'in_force',
                'extended': 'false', 'rescinded': 'false', 'is_codes': '', 'history_truncated': 'false', 'product_count': len(crs), 'first_date': ds[0] if ds else '',
                'latest_date': ds[-1] if ds else '', 'source_file': 'crs.csv', 'source_url': crs[0]['source_url'], 'retrieved_on': crs[0]['retrieved_on'],
                'source_rows': '2-%d' % (len(crs) + 1), 'pdf_urls': '', 'gazette_pdf_sha256': ''})

    reg.sort(key=lambda r: r['slug'])
    ev.sort(key=lambda e: (e['slug'], int(e['seq'])))
    prod.sort(key=lambda p: (p['slug'], p['source_file'], int(p['source_row'])))
    return reg, ev, prod


def to_csv(cols, rows):
    buf = io.StringIO(newline='')
    w = csv.DictWriter(buf, fieldnames=cols, lineterminator='\n')
    w.writeheader()
    w.writerows(rows)
    return buf.getvalue().encode('utf-8')
