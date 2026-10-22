#!/usr/bin/env python3
"""Fetch (or read the archive), parse, assert, write. All or nothing. Stdlib only.

    python3 -m pipeline.refresh                  fetch every source politely, rebuild everything, write what changed
    python3 -m pipeline.refresh --offline        rebuild from the newest archived copy under raw/ (no network)
    python3 -m pipeline.refresh --dry-run        do everything but write
    python3 -m pipeline.refresh --report r.json --changelog-md entry.md

A fetch that fails, a parse that yields nothing, a parsed row count that differs from the source's own count, or a list that shrinks by more
than half stops the run: nothing is written and the exit code is 1. A list that says exactly what it said is left byte for byte as it is
(no new raw copy) until its last stamp is REVERIFY_DAYS old.
"""
import argparse
import csv
import datetime
import glob
import hashlib
import io
import json
import os
import re
import sys
import urllib.request

from pipeline import adapters as A
from pipeline import derived, itchs, qco_register
from pipeline import refresh_diff as rd
from pipeline import sources as S

Failure = A.Failure
SHRINK_LIMIT = 0.5
REVERIFY_DAYS = 28
RAW_MAX = 2 * 1024 * 1024
HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_ROOT = os.path.normpath(os.path.join(HERE, '..'))
PROV_COLS = ['file', 'source_url', 'retrieved_on', 'sha256', 'rows', 'source_rows', 'page_date', 'parser', 'raw_file', 'raw_sha256', 'raw_bytes', 'raw_committed']


def sha(b):
    return hashlib.sha256(b).hexdigest()


def csv_bytes(cols, rows):
    buf = io.StringIO(newline='')
    w = csv.DictWriter(buf, fieldnames=cols, lineterminator='\n', extrasaction='ignore')
    w.writeheader()
    for r in rows:
        w.writerow({c: r.get(c, '') for c in cols})
    return buf.getvalue().encode('utf-8')


def read_rows(root, rel):
    p = os.path.join(root, rel)
    if not os.path.isfile(p):
        return None
    with open(p, 'rb') as fh:
        return list(csv.DictReader(io.StringIO(fh.read().decode('utf-8'), newline='')))


def read_file(root, rel):
    p = os.path.join(root, rel)
    if not os.path.isfile(p):
        return None
    with open(p, 'rb') as fh:
        return fh.read()


class Stage:
    """Every file the run wants to write. Nothing touches the disk until `commit`."""

    def __init__(self, root):
        self.root, self.files = root, {}

    def put(self, rel, data):
        self.files[rel] = data

    def commit(self):
        n = 0
        for rel, data in sorted(self.files.items()):
            p = os.path.join(self.root, rel)
            if os.path.isfile(p) and open(p, 'rb').read() == data:
                continue
            os.makedirs(os.path.dirname(p), exist_ok=True)
            tmp = p + '.tmp'
            with open(tmp, 'wb') as fh:
                fh.write(data)
            os.replace(tmp, p)
            n += 1
        return n


def newest_raw(root, source_id):
    """(date, path) of the newest archived copy of a source, from raw/<id>/<date>/."""
    dirs = sorted(d for d in glob.glob(os.path.join(root, 'raw', source_id, '*')) if os.path.isdir(d))
    if not dirs:
        raise Failure('%s: no archived copy under raw/%s' % (source_id, source_id))
    d = dirs[-1]
    files = [f for f in sorted(os.listdir(d)) if not f.endswith('.ref.json')]
    if not files:
        raise Failure('%s: %s holds no file' % (source_id, d))
    return os.path.basename(d), os.path.join(d, files[0])


class Ctx:
    def __init__(self, root, today, offline, fetch, dry_run):
        self.root, self.today, self.offline, self.fetch, self.dry_run = root, today, offline, fetch, dry_run
        self.stage = Stage(root)
        self.prov = {}  # file -> provenance row, per data dir


def fetch_url(url, lang):
    return url + ('&' if '?' in url else '?') + 'lang=en' if lang else url


def same_rows(a, b):
    strip = lambda rows: [{k: v for k, v in r.items() if k != 'retrieved_on'} for r in rows]  # noqa: E731
    return strip(a) == strip(b)


def get_raw(ctx, source_id, url, lang, stem, ext):
    """-> (body, date, raw_rel, already_archived)."""
    if ctx.offline:
        date, path = newest_raw(ctx.root, source_id)
        with open(path, 'rb') as fh:
            return fh.read(), date, os.path.relpath(path, ctx.root), True
    body = ctx.fetch(fetch_url(url, lang))
    return body, ctx.today, 'raw/%s/%s/%s_%s.%s' % (source_id, ctx.today, stem, ctx.today, ext), False


def stage_raw(ctx, raw_rel, body, url):
    """Raw bytes are committed when under 2 MB; larger ones are listed with URL + hash only."""
    if len(body) < RAW_MAX:
        ctx.stage.put(raw_rel, body)
        return True
    ctx.stage.put(raw_rel + '.ref.json', json.dumps({'url': url, 'sha256': sha(body), 'bytes': len(body)}, indent=1).encode() + b'\n')
    return False


def prov_load(ctx, rel):
    rows = read_rows(ctx.root, rel) or []
    return {r['file']: r for r in rows}


def prov_write(ctx, rel, prov):
    ctx.stage.put(rel, csv_bytes(PROV_COLS, [prov[k] for k in sorted(prov)]))


def run_list(ctx, spec, summary, prov):
    out = spec['out']
    cols = A.COLS + spec.get('extra_cols', [])
    body, date, raw_rel, archived = get_raw(ctx, spec['id'], spec['url'], spec['lang'], spec['stem'], spec['ext'])
    try:
        parsed = spec['parse'](body, spec['url'], date)
    except A.Failure as e:
        raise Failure('%s: %s' % (out, e))
    except Exception as e:  # noqa: BLE001 (a parser that crashes on a changed layout is a failed run, never a half-written list)
        raise Failure('%s: the parser crashed (%s: %s)' % (out, type(e).__name__, e))
    if not parsed.rows:
        raise Failure('%s: the page parsed to zero rows (layout changed?)' % out)
    if parsed.source_rows != len(parsed.rows):
        raise Failure('%s: parsed %d rows, the source has %d' % (out, len(parsed.rows), parsed.source_rows))
    current = read_rows(ctx.root, out)
    new = [{c: r.get(c, '') for c in cols} for r in parsed.rows]
    if current is not None and len(new) < len(current) * SHRINK_LIMIT:
        raise Failure('%s: %d rows against %d before (more than %d%% below); keeping the last good file' % (out, len(new), len(current), int((1 - SHRINK_LIMIT) * 100)))
    unchanged = False
    if current is not None and same_rows(new, current) and not ctx.offline:
        age = (datetime.date.fromisoformat(ctx.today) - datetime.date.fromisoformat(max(r['retrieved_on'] for r in current))).days
        unchanged = age < REVERIFY_DAYS
    rows = current if unchanged else new
    summary['lists'][out] = dict(rd.list_diff(current or [], rows), page_date=parsed.page_date, source_rows=parsed.source_rows, unchanged=unchanged)
    if unchanged:
        return rows
    data = csv_bytes(cols, rows)
    ctx.stage.put(out, data)
    committed = True if archived else stage_raw(ctx, raw_rel, body, spec['url'])
    prov[os.path.basename(out)] = {
        'file': os.path.basename(out), 'source_url': spec['url'], 'retrieved_on': date, 'sha256': sha(data), 'rows': len(rows), 'source_rows': parsed.source_rows,
        'page_date': parsed.page_date, 'parser': '%s.%s' % (spec['parse'].__module__, spec['parse'].__name__), 'raw_file': raw_rel, 'raw_sha256': sha(body),
        'raw_bytes': len(body), 'raw_committed': 'yes' if committed else 'no (url and hash only)'}
    return rows


def run_bee(ctx, summary, prov):
    b = S.BEE
    m_body, m_date, m_rel, m_arch = get_raw(ctx, b['mandatory']['id'], b['mandatory']['url'], False, b['mandatory']['stem'], 'html')
    v_body, v_date, v_rel, v_arch = get_raw(ctx, b['voluntary']['id'], b['voluntary']['url'], False, b['voluntary']['stem'], 'html')
    date = max(m_date, v_date)
    try:
        parsed = b['parse'](m_body, v_body, b['mandatory']['url'], b['voluntary']['url'], date)
    except A.Failure as e:
        raise Failure('data/bee: %s' % e)
    except Exception as e:  # noqa: BLE001
        raise Failure('data/bee: the parser crashed (%s: %s)' % (type(e).__name__, e))
    if parsed.source_rows != len(parsed.rows) or not parsed.rows:
        raise Failure('data/bee: parsed %d rows, the source has %d' % (len(parsed.rows), parsed.source_rows))
    for key, out, body, rel, arch, d in (('mandatory', b['out_mandatory'], m_body, m_rel, m_arch, m_date), ('voluntary', b['out_voluntary'], v_body, v_rel, v_arch, v_date)):
        rows = [dict(r, retrieved_on=d) for r in parsed.rows if r['scheme'].endswith('(%s)' % key)]
        if not rows:
            raise Failure('%s: no rows' % out)
        current = read_rows(ctx.root, out)
        if current is not None and len(rows) < len(current) * SHRINK_LIMIT:
            raise Failure('%s: %d rows against %d before; keeping the last good file' % (out, len(rows), len(current)))
        unchanged = False
        if current is not None and same_rows(rows, current) and not ctx.offline:
            age = (datetime.date.fromisoformat(ctx.today) - datetime.date.fromisoformat(max(r['retrieved_on'] for r in current))).days
            unchanged = age < REVERIFY_DAYS
        use = current if unchanged else rows
        summary['lists'][out] = dict(rd.list_diff(current or [], use), page_date='', source_rows=len(rows), unchanged=unchanged)
        if unchanged:
            continue
        data = csv_bytes(A.COLS, use)
        ctx.stage.put(out, data)
        url = b[key]['url']
        committed = True if arch else stage_raw(ctx, rel, body, url)
        prov[os.path.basename(out)] = {'file': os.path.basename(out), 'source_url': url, 'retrieved_on': d, 'sha256': sha(data), 'rows': len(use), 'source_rows': len(use),
                                       'page_date': '', 'parser': 'pipeline.adapter_bee.parse_bee', 'raw_file': rel, 'raw_sha256': sha(body), 'raw_bytes': len(body),
                                       'raw_committed': 'yes' if committed else 'no (url and hash only)'}


# ---- ITC(HS) ----------------------------------------------------------------------------------------------------------

def run_itchs(ctx, summary):
    root, d = ctx.root, S.ITCHS_DIR
    old_prov = {r['chapter']: r for r in (read_rows(root, d + '/PROVENANCE.csv') or [])}
    bodies, prov_new = {}, {}
    if ctx.offline:
        # the acquisition record (raw PROVENANCE of the first archive, else data/itchs/2022/PROVENANCE.csv) says which chapters and which bytes
        for r in (read_rows(root, 'data/itchs/2022/PROVENANCE.csv') or []):
            prov_new[r['chapter']] = r
        if not prov_new:
            for pp in sorted(glob.glob(os.path.join(root, S.ITCHS_RAW, '*', 'PROVENANCE.csv'))):
                for r in csv.DictReader(open(pp, newline='', encoding='utf-8')):
                    prov_new[r['chapter']] = r
        if not prov_new:
            raise Failure('itchs: no acquisition record (PROVENANCE.csv) to rebuild from')
        raw_date = {}
        for ch, r in sorted(prov_new.items()):
            hit = None
            for f in sorted(glob.glob(os.path.join(root, S.ITCHS_RAW, '*', 'ch%s.json' % ch))):
                b = open(f, 'rb').read()
                if sha(b) == r['sha256']:
                    hit = (b, os.path.basename(os.path.dirname(f)))
            if hit is None:
                raise Failure('itchs ch%s: no archived copy matches the recorded sha256 %s' % (ch, r['sha256'][:12]))
            bodies[ch] = (hit[0], None)
            raw_date[ch] = hit[1]
        listing = None
        date = max(raw_date.values())
        expected = len(prov_new)
    else:
        ses = itchs.DgftSession()
        listing = ses.listing()
        chs = itchs.chapters_in_listing(listing)
        date = ctx.today
        for c in chs:
            b = ses.chapter(c)
            bodies[c] = (b, datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'))
        expected = len(chs)
    if len(bodies) != expected or len(bodies) < 90:
        raise Failure('itchs: %d chapters obtained, %d expected' % (len(bodies), expected))
    chapters, report_rows, changed_chapters, diff = {}, [], [], {'added': 0, 'removed': 0, 'changed': 0}
    for ch in sorted(bodies):
        body, ts = bodies[ch]
        old = read_rows(root, '%s/ch%s.csv' % (d, ch))
        old_json = read_file(root, '%s/ch%s.json' % (d, ch))
        use_asof, status = (raw_date[ch] if ctx.offline else date), 'new'
        if old and old_json and not ctx.offline:
            old_asof = old[0]['as_of'] if old else date
            rows0, notes0, _, st0 = itchs.parse_chapter(body, ch, old_asof)
            if chapter_json(ch, st0, rows0, notes0, old_asof) == old_json:
                use_asof, status = old_asof, 'unchanged'
            else:
                status = 'changed'
        elif old:
            status = 'rebuilt'
        rows, notes, snotes, st = itchs.parse_chapter(body, ch, use_asof)
        p = prov_new.get(ch) or (itchs.provenance_row(ch, body, ts, st['rows_8digit']) if ts else old_prov.get(ch))
        if p is None:
            raise Failure('itchs ch%s: no provenance row' % ch)
        if str(p['rows_in_json']) != str(st['rows_8digit']):
            raise Failure('itchs ch%s: provenance says %s 8-digit rows, parsed %d' % (ch, p['rows_in_json'], st['rows_8digit']))
        if p['sha256'] != sha(body):
            raise Failure('itchs ch%s: the archived bytes do not match the recorded sha256' % ch)
        if status in ('unchanged',):
            p = old_prov.get(ch, p)
        chapters[ch] = (rows, notes, snotes, st, use_asof, p)
        report_rows.append(dict(st, sha256=p['sha256']))
        if status != 'unchanged':
            changed_chapters.append(ch)
            if old:
                a, b2 = {r['hs_code']: r for r in old}, {r['hs_code']: r for r in rows}
                diff['added'] += len(set(b2) - set(a)); diff['removed'] += len(set(a) - set(b2))
                diff['changed'] += sum(1 for k in a if k in b2 and {x: y for x, y in a[k].items() if x != 'as_of'} != {x: str(y) for x, y in b2[k].items() if x != 'as_of'})
            if not ctx.offline:
                stage_raw(ctx, '%s/%s/ch%s.json' % (S.ITCHS_RAW, date, ch), body, itchs.API_URL)
    all_rows = [r for ch in sorted(chapters) for r in chapters[ch][0]]
    all_notes = [n for ch in sorted(chapters) for n in chapters[ch][1]]
    seen, section_notes = set(), []
    for ch in sorted(chapters):
        for n in chapters[ch][2]:
            k = (n['section'], n['note_type'], n['serial_no'], n['text'])
            if k not in seen:
                seen.add(k); section_notes.append(n)
    n8 = sum(1 for r in all_rows if int(r['level']) == 8)
    if n8 != sum(int(p[5]['rows_in_json']) for p in chapters.values()):
        raise Failure('itchs: total 8-digit rows %d differ from the sum of the per-chapter counts' % n8)
    for ch, (rows, notes, snotes, st, asof, p) in chapters.items():
        ctx.stage.put('%s/ch%s.csv' % (d, ch), itchs.csv_bytes(itchs.ROW_COLS, rows))
        ctx.stage.put('%s/ch%s.json' % (d, ch), chapter_json(ch, st, rows, notes, asof))
    ctx.stage.put(d + '/all.csv', itchs.csv_bytes(itchs.ROW_COLS, all_rows))
    ctx.stage.put(d + '/chapter-conditions.csv', itchs.csv_bytes(itchs.NOTE_COLS, all_notes))
    ctx.stage.put(d + '/section-notes.csv', itchs.csv_bytes(itchs.SECTION_NOTE_COLS, section_notes))
    ctx.stage.put(d + '/PROVENANCE.csv', csv_bytes(itchs.PROV_COLS, [chapters[c][5] for c in sorted(chapters)]))
    if listing is not None:
        ctx.stage.put('%s/%s/listing.html' % (S.ITCHS_RAW, date), listing)
    report = {'edition': itchs.EDITION, 'permission_ref': itchs.PERMISSION_REF, 'chapters': len(chapters), 'rows_total': len(all_rows),
              'rows_8digit': n8, 'rows_6digit': sum(1 for r in all_rows if int(r['level']) == 6), 'rows_4digit': sum(1 for r in all_rows if int(r['level']) == 4),
              'chapter_condition_rows': len(all_notes), 'section_note_rows': len(section_notes),
              'duplicate_codes_in_export': sorted(c for r in report_rows for c in r['duplicate_codes_in_export']),
              'assertions': ['rows parsed == items in each chapter export', 'notes parsed == notes in each chapter export',
                             '8-digit rows parsed == rows_in_json recorded at acquisition (per chapter)', 'sha256 of each archived chapter == PROVENANCE',
                             'sum of per-chapter 8-digit rows == 8-digit rows in all.csv'], 'all_passed': True,
              'per_chapter': [{k: v for k, v in r.items() if k != 'duplicate_codes_in_export'} for r in report_rows]}
    ctx.stage.put(d + '/BUILD-REPORT.json', (json.dumps(report, indent=1, ensure_ascii=False) + '\n').encode())
    summary['itchs'] = {'chapters': len(chapters), 'rows_total': len(all_rows), 'rows_8digit': n8, 'chapters_changed': sorted(changed_chapters) if not ctx.offline else [], **diff}
    return all_rows


def chapter_json(ch, st, rows, notes, as_of):
    doc = {'edition': itchs.EDITION, 'chapter': ch, 'chapter_title': st['chapter_title'], 'section': st['section'], 'as_of': as_of,
           'source': itchs.API_URL, 'permission_ref': itchs.PERMISSION_REF, 'rows': [dict(r, level=int(r['level'])) for r in rows], 'chapter_conditions': notes}
    return (json.dumps(doc, indent=1, ensure_ascii=False) + '\n').encode()


# ---- QCO register -----------------------------------------------------------------------------------------------------

GAZ_COLS = ['source_url', 'sha256', 'retrieved_on', 'status']


def run_qco(ctx, summary):
    root = ctx.root
    files = {}
    for f in ('isi_qco.csv', 'qco_upcoming.csv', 'crs.csv'):
        b = ctx.stage.files.get('data/bis/' + f) or read_file(root, 'data/bis/' + f)
        if b is None:
            raise Failure('qco register: data/bis/%s is missing' % f)
        files[f] = b
    date, page = newest_raw(root, 'bis-scheme1')[1], None
    with open(date, 'rb') as fh:
        page = fh.read()
    gaz = {r['source_url']: r for r in (read_rows(root, S.QCO_DIR + '/gazette-pdf-hashes.csv') or [])}
    reg, ev, prod = qco_register.build(files, page, {u: r['sha256'] for u, r in gaz.items() if r['sha256']})
    urls = sorted({u.strip() for r in reg for u in r['pdf_urls'].split(';') if u.strip()})
    if not ctx.offline:  # new gazette URLs are hashed (never stored): fetched politely, a failure is recorded, not fatal
        for u in urls:
            if u in gaz and gaz[u]['status'] == 'ok':
                continue
            try:
                b = ctx.fetch(u)
                gaz[u] = {'source_url': u, 'sha256': sha(b), 'retrieved_on': ctx.today, 'status': 'ok'}
            except Failure as e:
                gaz[u] = {'source_url': u, 'sha256': '', 'retrieved_on': ctx.today, 'status': 'unavailable: %s' % str(e)[:80]}
        reg, ev, prod = qco_register.build(files, page, {u: r['sha256'] for u, r in gaz.items() if r['sha256']})
    gaz_rows = [gaz[u] if u in gaz else {'source_url': u, 'sha256': '', 'retrieved_on': '', 'status': 'not fetched'} for u in urls]
    ctx.stage.put(S.QCO_DIR + '/gazette-pdf-hashes.csv', csv_bytes(GAZ_COLS, gaz_rows))
    ctx.stage.put(S.QCO_DIR + '/register.csv', qco_register.to_csv(qco_register.REGISTER_COLS, reg))
    ctx.stage.put(S.QCO_DIR + '/events.csv', qco_register.to_csv(qco_register.EVENT_COLS, ev))
    ctx.stage.put(S.QCO_DIR + '/products.csv', qco_register.to_csv(qco_register.PRODUCT_COLS, prod))
    by = {}
    for e in ev:
        by.setdefault(e['slug'], []).append({k: e[k] for k in ('seq', 'date', 'kind', 'text')})
    doc = [dict(r, product_count=int(r['product_count']), events=by.get(r['slug'], [])) for r in reg]
    ctx.stage.put(S.QCO_DIR + '/register.json', (json.dumps(doc, indent=1, ensure_ascii=False) + '\n').encode())
    ctx.stage.put(S.QCO_DIR + '/PROVENANCE.csv', csv_bytes(PROV_COLS, [{
        'file': 'register.csv', 'source_url': 'derived from data/bis/isi_qco.csv, qco_upcoming.csv, crs.csv', 'retrieved_on': max(r['retrieved_on'] for r in reg),
        'sha256': sha(qco_register.to_csv(qco_register.REGISTER_COLS, reg)), 'rows': len(reg), 'source_rows': len(reg), 'page_date': '',
        'parser': 'pipeline.qco_register.build', 'raw_file': '', 'raw_sha256': '', 'raw_bytes': '', 'raw_committed': 'gazette PDFs are not stored; see gazette-pdf-hashes.csv'}]))
    summary['qco'] = {'register': len(reg), 'events': len(ev), 'products': len(prod), 'gazette_pdfs': len(gaz_rows), 'gazette_pdfs_hashed': sum(1 for r in gaz_rows if r['sha256'])}
    return reg


# ---- run --------------------------------------------------------------------------------------------------------------

def http_fetch(url, _f=[]):
    if not _f:
        _f.append(A.PoliteFetcher())
    return _f[0](url)


def run(root, today, offline=False, dry_run=False, fetch=http_fetch):
    ctx = Ctx(root, today, offline, fetch, dry_run)
    summary = {'status': 'ok', 'date': today, 'offline': offline, 'lists': {}}
    provs = {'data/bis': prov_load(ctx, 'data/bis/PROVENANCE.csv'), 'data/tec': prov_load(ctx, 'data/tec/PROVENANCE.csv'), 'data/bee': prov_load(ctx, 'data/bee/PROVENANCE.csv')}
    for spec in S.LISTS:
        run_list(ctx, spec, summary, provs[os.path.dirname(spec['out'])])
    run_bee(ctx, summary, provs['data/bee'])
    for d, prov in provs.items():
        prov_write(ctx, d + '/PROVENANCE.csv', prov)
    all_rows = run_itchs(ctx, summary)
    run_qco(ctx, summary)
    cand = derived.candidates(all_rows)
    ctx.stage.put('data/derived/hs-scheme-candidates.csv', derived.to_csv(cand))
    summary['derived'] = {'hs_scheme_candidates': len(cand)}
    if dry_run:
        summary['dry_run'] = True
        summary['files_that_would_change'] = sum(1 for rel, b in ctx.stage.files.items() if read_file(root, rel) != b)
        return summary
    summary['files_written'] = ctx.stage.commit()
    summary['changed'] = summary['files_written'] > 0
    return summary


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--root', default=DEFAULT_ROOT)
    ap.add_argument('--today', default=datetime.date.today().isoformat())
    ap.add_argument('--offline', action='store_true')
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--report')
    ap.add_argument('--changelog-md')
    a = ap.parse_args(argv)
    try:
        summary, code = run(a.root, a.today, a.offline, a.dry_run), 0
    except Failure as e:
        summary, code = {'status': 'failed', 'date': a.today, 'reason': str(e)}, 1
    except Exception as e:  # noqa: BLE001 (nothing is written before every assertion has passed)
        summary, code = {'status': 'failed', 'date': a.today, 'reason': 'unexpected %s: %s' % (type(e).__name__, e)}, 1
    text = json.dumps(summary, indent=2, ensure_ascii=False)
    if a.report:
        with open(a.report, 'w', encoding='utf-8') as fh:
            fh.write(text + '\n')
    if a.changelog_md and not code:
        with open(a.changelog_md, 'w', encoding='utf-8') as fh:
            fh.write(changelog_entry(summary))
    print(text if code or a.report is None else json.dumps({k: v for k, v in summary.items() if k not in ('lists',)}, indent=1))
    if code:
        print('REFRESH FAILED, nothing written: %s' % summary['reason'], file=sys.stderr)
    return code


def changelog_entry(summary):
    lines = ['## %s' % summary['date'], '']
    lists = summary.get('lists') or {}
    moved = [f for f in sorted(lists) if rd.changed(lists[f])]
    if not moved and not (summary.get('itchs') or {}).get('chapters_changed'):
        lines.append('Re-verified; no list changed.')
    for f in moved:
        d = lists[f]
        lines.append('- `%s`: %d -> %d rows; %d added, %d removed, %d status changed, %d date changed, %d wording changed.' % (
            f, d['rows_before'], d['rows_after'], d['added'], d['removed'], d['status_changed'], d['date_changed'], d['other_changed']))
        for x in d['added_sample'][:5]:
            lines.append('  - added: %s' % x)
        for x in d['removed_sample'][:5]:
            lines.append('  - removed: %s' % x)
        for x in d['status_sample'][:5]:
            lines.append('  - status: %s: %s -> %s' % (x['row'], x['from'], x['to']))
    it = summary.get('itchs') or {}
    if it.get('chapters_changed'):
        lines.append('- `data/itchs/2022`: %d chapters changed (%s); %d codes added, %d removed, %d changed.' % (
            len(it['chapters_changed']), ', '.join(it['chapters_changed'][:20]), it['added'], it['removed'], it['changed']))
    q = summary.get('qco') or {}
    if q:
        lines.append('- `data/qco`: %d register records, %d events.' % (q['register'], q['events']))
    return '\n'.join(lines) + '\n'


if __name__ == '__main__':
    sys.exit(main())
