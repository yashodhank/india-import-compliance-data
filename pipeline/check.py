"""Consistency check of the published data: `python -m pipeline.check` (exit 1 and one line per problem; CI runs it beside the tests).

Covers what the unit tests do not: every CSV against its Table Schema, row counts against provenance and the documented claims, provenance against the
bytes on disk (both directions), referential integrity of measures / register / products / events / IS standards, status vocabularies, ISO dates not in
the future, S.O. reference shape, and the corrections made on 2026-10-22 (Animal Feeds section, Foot Wear active, IS 1660 in Scheme-I not upcoming).
"""
import csv
import datetime
import glob
import hashlib
import json
import os
import re
import sys

REPO = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
sys.path.insert(0, os.path.join(REPO, 'tests'))

LIST_STATUS = {  # the status words each list may carry
    'data/bis/isi_qco.csv': {'active', 'withdrawn', 'de-notified'},
    'data/bis/qco_upcoming.csv': {'upcoming'},
    'data/bis/option2.csv': {'active', 'withdrawn', 'de-notified'},
    'data/bis/crs.csv': {'active', 'withdrawn', 'de-notified'},
    'data/bis/scheme_ii_other.csv': {'active', 'withdrawn', 'de-notified'},
    'data/bis/scheme_iv.csv': {'active', 'withdrawn', 'de-notified'},
    'data/bis/scheme_x.csv': {'active', 'withdrawn', 'de-notified'},
    'data/tec/mtcte.csv': {'active', 'withdrawn', 'de-notified'},
    'data/bee/mandatory.csv': {'active', 'discontinued'},
    'data/bee/voluntary.csv': {'active', 'discontinued'},
}
DATE_COLUMNS = {'retrieved_on', 'as_of', 'fetched_at', 'retrieved_at_utc', 'page_date', 'order_date'}  # the day a thing happened or was read, never a future one
SO_WELL_FORMED = re.compile(r'^S\.O\. ?\d{1,5}\(E\)$')


def rows(rel):
    with open(os.path.join(REPO, rel), newline='', encoding='utf-8') as fh:
        return list(csv.DictReader(fh))


def sha(rel):
    with open(os.path.join(REPO, rel), 'rb') as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def csv_files():
    return sorted(os.path.relpath(p, REPO) for p in glob.glob(os.path.join(REPO, 'data', '**', '*.csv'), recursive=True))


def iso(v):
    try:
        return datetime.date.fromisoformat(v[:10]) if v else None
    except ValueError:
        return False


def check_schemas(err):
    from schemacheck import load_schema, validate
    index = json.load(open(os.path.join(REPO, 'schemas', 'index.json'), encoding='utf-8'))['files']
    for rel in csv_files():
        if rel not in index:
            err('%s: no schema in schemas/index.json' % rel)
            continue
        for e in validate(os.path.join(REPO, rel), load_schema(index[rel])):
            err('%s: %s' % (rel, e))


def check_duplicates(err):
    for rel in csv_files():
        if rel.startswith('data/itchs/'):
            continue  # the DGFT export itself lists a few lines twice (e.g. 86090010); the build report proves rows parsed == items in the export
        seen, dup = set(), 0
        for r in rows(rel):
            k = tuple(r.values())
            dup += k in seen
            seen.add(k)
        if dup:
            err('%s: %d duplicate rows' % (rel, dup))


def check_status_and_dates(err, today):
    for rel, ok in LIST_STATUS.items():
        for n, r in enumerate(rows(rel), start=2):
            if r['status'] not in ok:
                err('%s:%d status %r not in %s' % (rel, n, r['status'], sorted(ok)))
    for rel in csv_files():
        rs = rows(rel)
        if not rs:
            continue
        for col in set(rs[0]) & DATE_COLUMNS:
            for n, r in enumerate(rs, start=2):
                d = iso(r[col])
                if d is False:
                    err('%s:%d %s=%r is not an ISO date' % (rel, n, col, r[col]))
                elif d and d > today:
                    err('%s:%d %s=%s is in the future' % (rel, n, col, r[col]))
    for n, r in enumerate(rows('data/qco/events.csv'), start=2):
        d = iso(r['date'])
        if d is False:
            err('data/qco/events.csv:%d date %r is not ISO' % (n, r['date']))
        elif d and d > today + datetime.timedelta(days=5 * 366):  # a date in an order's text may be an enforcement date ahead; five years out is a misread
            err('data/qco/events.csv:%d event dated %s is implausibly far ahead' % (n, r['date']))
    for n, r in enumerate(rows('data/measures/measures.csv'), start=2):
        for col in ('valid_from', 'valid_to'):
            if iso(r[col]) is False:
                err('measures.csv:%d %s=%r is not an ISO date' % (n, col, r[col]))
        if r['status'] == 'in_force' and iso(r['valid_from']) and iso(r['valid_from']) > today:
            err('measures.csv:%d in force but valid_from %s is in the future' % (n, r['valid_from']))


def check_provenance(err):
    for prov in sorted(glob.glob(os.path.join(REPO, 'data', '**', 'PROVENANCE.csv'), recursive=True)):
        prel = os.path.relpath(prov, REPO)
        d = os.path.dirname(prel)
        ps = rows(prel)
        if 'chapter' in (ps[0] if ps else {}):  # ITC(HS): one raw JSON export per chapter
            have = set()
            for p in ps:
                have.add('ch%s.csv' % p['chapter'])
                got = glob.glob(os.path.join(REPO, 'raw', 'dgft-itchs-2022', '*', 'ch%s.json' % p['chapter']))
                if p['sha256'] not in [hashlib.sha256(open(g, 'rb').read()).hexdigest() for g in got]:
                    err('%s: chapter %s has no archived raw export with sha256 %s' % (prel, p['chapter'], p['sha256'][:12]))
            on_disk = {os.path.basename(f) for f in glob.glob(os.path.join(REPO, d, 'ch[0-9]*.csv'))}
            if on_disk != have:
                err('%s: chapter files and provenance rows differ: %s' % (prel, sorted(on_disk ^ have)[:5]))
            continue
        listed = set()
        for p in ps:
            listed.add(p['file'])
            rel = d + '/' + p['file']
            if not os.path.exists(os.path.join(REPO, rel)):
                err('%s: %s does not exist' % (prel, rel))
                continue
            if sha(rel) != p['sha256']:
                err('%s: %s sha256 differs from the recorded one' % (prel, p['file']))
            n = len(rows(rel))
            if int(p['rows']) != n:
                err('%s: %s has %d rows, provenance says %s' % (prel, p['file'], n, p['rows']))
            if p['rows'] != p['source_rows']:
                err('%s: %s parsed %s rows but the source has %s' % (prel, p['file'], p['rows'], p['source_rows']))
            if p['raw_committed'] == 'yes':
                raw = p['raw_file']
                full = os.path.join(REPO, raw)
                if not os.path.exists(full):
                    err('%s: raw file %s does not exist' % (prel, raw))
                elif os.path.isfile(full):
                    if sha(raw) != p['raw_sha256']:
                        err('%s: raw file %s sha256 differs from the recorded one' % (prel, raw))
                    if p['raw_bytes'] and os.path.getsize(full) != int(p['raw_bytes']):
                        err('%s: raw file %s size differs from the recorded one' % (prel, raw))
        on_disk = {os.path.basename(f) for f in glob.glob(os.path.join(REPO, d, '*.csv'))} - {'PROVENANCE.csv'}
        extra = on_disk - listed - ({'events.csv', 'products.csv', 'gazette-pdf-hashes.csv'} if d == 'data/qco' else set())  # built together with register.csv, which is the one recorded
        if extra:
            err('%s: %s on disk but not in provenance' % (prel, sorted(extra)))


def check_measures(err):
    m = rows('data/measures/measures.csv')
    reg = {r['slug'] for r in rows('data/qco/register.csv')}
    hs8 = {r['hs_code'] for r in rows('data/itchs/2022/all.csv') if r['level'] == '8'}
    std = rows('data/is-standards/standards.csv')
    is_no = {r['is_no'] for r in std}
    bases = {r['is_base'] for r in std}
    for n, r in enumerate(m, start=2):
        if r['hs8'] not in hs8:
            err('measures.csv:%d hs8 %s is not an 8-digit ITC(HS) code' % (n, r['hs8']))
        if r['hs6'] != r['hs8'][:6]:
            err('measures.csv:%d hs6 %s is not the prefix of %s' % (n, r['hs6'], r['hs8']))
        if r['qco_slug'] and r['qco_slug'] not in reg:
            err('measures.csv:%d qco_slug %s is not in the register' % (n, r['qco_slug']))
        for sf in r['source_file'].split(';'):
            if not os.path.exists(os.path.join(REPO, sf.strip())):
                err('measures.csv:%d source_file %s does not exist' % (n, sf))
        if r['is_status'] and r['is_status'] not in ('current', 'unknown', 'withdrawn', 'superseded'):
            err('measures.csv:%d is_status %r is outside the vocabulary' % (n, r['is_status']))
        if r['is_superseded_by'] and not re.search(r'\d+', r['is_superseded_by']):
            err('measures.csv:%d is_superseded_by %r names no standard' % (n, r['is_superseded_by']))
        for tok in re.findall(r'S\.O\.[^;,|(]*\(E\)', r['legal_ref']):
            if not SO_WELL_FORMED.match(tok.strip()):
                err('measures.csv:%d malformed S.O. reference %r' % (n, tok))
    for r in std:
        sb = r['superseded_by']
        if sb and not (sb in is_no or (re.match(r'IS\s*(\d+)', sb) and re.match(r'IS\s*(\d+)', sb).group(1) in bases)):
            err('standards.csv: %s is superseded_by %r, which is not in the table' % (r['is_no'], sb))
    for r in rows('data/qco/events.csv'):
        if r['slug'] not in reg:
            err('events.csv: slug %s is not in the register' % r['slug'])
    for r in rows('data/qco/products.csv'):
        if r['slug'] not in reg:
            err('products.csv: slug %s is not in the register' % r['slug'])
    for r in rows('data/hs-links/steel-qco-hs-columns.csv'):
        if r['qco_slug'] not in reg:
            err('steel-qco-hs-columns.csv: slug %s is not in the register' % r['qco_slug'])
        if not SO_WELL_FORMED.match(r['so_number']):
            err('steel-qco-hs-columns.csv: malformed S.O. reference %r' % r['so_number'])


def check_claims(err):
    """Counts the documents state must equal the files: the join size in the README, each list's row count in the newest CHANGELOG entry that names it."""
    m = rows('data/measures/measures.csv')
    readme = open(os.path.join(REPO, 'README.md'), encoding='utf-8').read()
    claim = re.search(r'is_superseded_by`[^.]*?\((\d+) rows\)', readme)
    if claim and int(claim.group(1)) != sum(1 for r in m if r['is_status']):
        err('README.md says the IS join covers %s rows; measures.csv has %d' % (claim.group(1), sum(1 for r in m if r['is_status'])))
    rep = json.load(open(os.path.join(REPO, 'data/measures/BUILD-REPORT.json'), encoding='utf-8'))
    if rep['rows'] != len(m):
        err('measures BUILD-REPORT says %s rows; measures.csv has %d' % (rep['rows'], len(m)))
    if rep['qco_records'] != len(rows('data/qco/register.csv')):
        err('measures BUILD-REPORT says %s QCO records; register.csv has %d' % (rep['qco_records'], len(rows('data/qco/register.csv'))))
    seen = set()
    for line in open(os.path.join(REPO, 'CHANGELOG.md'), encoding='utf-8'):
        c = re.match(r'- `(data/[^`]+\.csv)`: (\d+) -> (\d+) rows', line)
        if c and c.group(1) not in seen:
            seen.add(c.group(1))
            if os.path.exists(os.path.join(REPO, c.group(1))) and len(rows(c.group(1))) != int(c.group(3)):
                err('CHANGELOG.md: newest entry for %s says %s rows; the file has %d' % (c.group(1), c.group(3), len(rows(c.group(1)))))


def check_known_corrections(err):
    isi = rows('data/bis/isi_qco.csv')
    feeds = [r for r in isi if r['is_codes'] in ('IS 1664', 'IS 5470', 'IS 920')]
    if len(feeds) != 3 or {r['group'] for r in feeds} != {'Animal Feeds and Feed Ingredients'}:
        err('isi_qco.csv: the three Animal Feeds rows (IS 1664, IS 5470, IS 920) must sit in the section "Animal Feeds and Feed Ingredients", got %s' % sorted({r['group'] for r in feeds}))
    foot = [r for r in isi if re.search(r'foot ?wear', r['notes'], re.I)]
    if not foot or any(r['status'] != 'active' for r in foot):
        err('isi_qco.csv: Foot Wear rows must exist and all be active (last order decides): %s' % sorted({r['status'] for r in foot}))
    if not any(r['is_codes'].startswith('IS 1660') and r['status'] == 'active' for r in isi):
        err('isi_qco.csv: IS 1660 must be an active Scheme-I row')
    if any(re.search(r'\bIS 1660\b', r['is_codes']) for r in rows('data/bis/qco_upcoming.csv')):
        err('qco_upcoming.csv: IS 1660 is in force in Scheme-I and must not be listed as upcoming')


def run(today=None):
    today = today or datetime.date.today()
    errors = []
    err = errors.append
    for fn in (check_schemas, check_duplicates, check_provenance, check_measures, check_claims, check_known_corrections):
        fn(err)
    check_status_and_dates(err, today)
    return errors


def main():
    errors = run()
    for e in errors[:200]:
        print('CHECK FAILED: ' + e)
    if len(errors) > 200:
        print('... and %d more' % (len(errors) - 200))
    print('%d problem(s)' % len(errors) if errors else 'data check: ok')
    return 1 if errors else 0


if __name__ == '__main__':
    sys.exit(main())
