"""Builds data/measures/: one row per (8-digit ITC(HS) code, measure), in the shape of a tariff "measure" (type, value, conditions,
document code, legal reference, validity). Everything is derived from tables already in this repository; nothing is fetched.

A BIS, CRS or Scheme X measure is attached to an HS code only where the official ITC(HS) text for that code (its own condition, or the
chapter policy condition it cites) names an IS number that the BIS lists also carry. Keyword hits stay `confidence=candidate`.
The TEC, BEE and CRS lists, and most QCOs, carry no HS code in any official text held here, so they are reported as unmapped.

Run `python -m pipeline.measures` to rewrite the files; tests/test_measures.py fails when they are stale.
"""
import collections
import csv
import hashlib
import html
import io
import json
import os
import re
import sys

REPO = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
sys.path.insert(0, REPO)
from pipeline import derived  # noqa: E402

COLS = ['hs8', 'hs6', 'measure_type', 'measure_value', 'condition_text', 'document_code', 'legal_ref', 'valid_from', 'valid_to', 'status',
        'confidence', 'basis', 'qco_slug', 'source_file', 'source_sha256', 'as_of', 'is_title', 'is_status', 'is_superseded_by']
TYPE_ORDER = ['import_policy', 'policy_condition', 'import_monitoring', 'bis_isi_qco', 'bis_upcoming_qco', 'bis_crs', 'bis_scheme_x',
              'tec_mtcte', 'bee_label', 'other_condition']

ITC = 'data/itchs/2022/all.csv'
CHAP = 'data/itchs/2022/chapter-conditions.csv'
REG = 'data/qco/register.csv'
EVENTS = 'data/qco/events.csv'
PRODUCTS = 'data/qco/products.csv'
CANDS = 'data/derived/hs-scheme-candidates.csv'
LISTS = {'data/bis/crs.csv': ('bis_crs', 'BIS-CRS'), 'data/bis/scheme_ii_other.csv': ('bis_crs', 'BIS-CRS'),
         'data/bis/scheme_x.csv': ('bis_scheme_x', 'BIS-SCHEME-X'), 'data/bis/scheme_iv.csv': ('other_condition', 'BIS-SCHEME-IV'),
         'data/bis/option2.csv': ('bis_isi_qco', 'BIS-ISI-OPT2')}
STEEL = 'data/hs-links/steel-qco-hs-columns.csv'
APP3 = 'data/hs-links/appendix3-bis.csv'
ISSTD = 'data/is-standards/standards.csv'
CRS_GENERIC = 'compulsory-registration-scheme-crs'
SO = re.compile(r'S\.?\s?O\.?\s*(?:No\.?)?\s*\d+\s*\(\s*E\s*\)', re.I)
IS_RE = re.compile(r'\bIS(?:/(?:IEC|ISO))?\s*:?\s*(\d{2,6})(?!\d)')
IMS_NAMED = {'SIMS': re.compile(r'\bSIMS\b|Steel Import Monitoring System'), 'CHIMS': re.compile(r'\bCHIMS\b|Chip Import Monitoring System'),
             'NFMIMS': re.compile(r'\bNFMIMS\b|Non-?\s?Ferrous Metal Import Monitoring System'),
             'PIMS': re.compile(r'\bPIMS\b|Paper Import Monitoring System')}
IMS_ANY = re.compile(r'\b([A-Z]{1,8}-?IMS)\b|Import Monitoring System')
CAND_MAP = {'BIS': ('other_condition', 'BIS-STD'), 'IS': ('other_condition', 'BIS-STD'), 'CRS': ('bis_crs', 'BIS-CRS'),
            'QCO': ('bis_isi_qco', 'BIS-ISI'), 'TEC': ('tec_mtcte', 'TEC-MTCTE'), 'BEE': ('bee_label', 'BEE-LABEL'),
            'WPC': ('other_condition', 'WPC-ETA'), 'LegalMetrology': ('other_condition', 'LEGAL-METROLOGY'),
            'EPR': ('other_condition', 'EPR'), 'CDSCO': ('other_condition', 'CDSCO'), 'FSSAI': ('other_condition', 'FSSAI')}
MONITORING_HINTS = {'SIMS', 'CHIMS', 'NFMIMS', 'PIMS', 'import_monitoring'}


def clean(text):
    t = html.unescape(re.sub(r'<[^>]+>', ' ', text or ''))
    t = re.sub(r'\s+', ' ', t.replace('\xa0', ' ')).strip()
    return '' if t in ('-', '--') else t


def is_bases(text):
    return list(dict.fromkeys(IS_RE.findall(text or '')))


PART_RE = re.compile(r'^\s*[:,]?\s*\(?\s*(?:Part|Pt)\.?\s*(\d+)', re.I)


def is_refs(text):
    """-> [(base, part or '')] for every IS number in the text, with the part number when it is printed right after it."""
    out = []
    for m in IS_RE.finditer(text or ''):
        pm = PART_RE.match((text or '')[m.end():m.end() + 24])
        out.append((m.group(1), pm.group(1) if pm else ''))
    return list(dict.fromkeys(out))


def _compatible(ref, entries):
    """An IS 302 (Part 2) condition does not tie to the entry for IS 302 (Part 1): same base, both parts printed, parts differ."""
    return [e for e in entries if not ref[1] or not e['parts'].get(ref[0]) or ref[1] in e['parts'][ref[0]]]


def monitoring(text):
    """-> [(document_code, system name as the text names it)]"""
    out = [(c, p.search(text).group(0)) for c, p in IMS_NAMED.items() if p.search(text or '')]
    if not out:
        m = IMS_ANY.search(text or '')
        if m:
            out = [('IMS', m.group(1) or m.group(0))]
    return out


def _read(root, rel, files):
    if rel in files:
        return files[rel]
    with open(os.path.join(root, rel), 'rb') as fh:
        return fh.read()


def _csv(b):
    return list(csv.DictReader(io.StringIO(b.decode('utf-8'), newline='')))


def _sha(b):
    return hashlib.sha256(b).hexdigest()


def _norm_policy(p):
    p = (p or '').strip()
    if p.startswith('Free'):
        return 'Free'
    if p.startswith('State Trading') or p.startswith('STE'):
        return 'STE'
    return p


def _date(s):
    return s if re.match(r'^\d{4}-\d{2}-\d{2}$', s or '') else ''


def join_standards(out, std_rows):
    """Adds is_title, is_status, is_superseded_by to the rows whose measure_value is a single IS number (bis_isi_qco, bis_upcoming_qco, and
    the Appendix III rows). The key is the exact IS number and part; a value with no part is not guessed onto one part of a multi-part
    standard. The measure's own `status` is never touched: a standard's withdrawal on the BIS portal is not a withdrawal of the order.
    -> (joined, ambiguous_multi_part, not_in_table, warnings)"""
    by_no = {r['is_no']: r for r in std_rows}
    parts_of = collections.defaultdict(list)
    for r in std_rows:
        parts_of[r['is_base']].append(r)
    joined = ambiguous = missing = 0
    warn = {}
    for m in out:
        m.setdefault('is_title', '')
        m.setdefault('is_status', '')
        m.setdefault('is_superseded_by', '')
        if m['measure_type'] not in ('bis_isi_qco', 'bis_upcoming_qco') or not re.match(r'^IS \d', m['measure_value'] or ''):
            continue
        refs = is_refs(m['measure_value'])
        if len(refs) != 1:
            continue
        base, part = refs[0]
        std = by_no.get('IS %s%s' % (base, (' (Part %s)' % part) if part else ''))
        if std is None:
            if not part and any(r['part'] for r in parts_of.get(base, [])):
                ambiguous += 1
            else:
                missing += 1
            continue
        m['is_title'], m['is_status'], m['is_superseded_by'] = std['title'], std['status'], std['superseded_by']
        joined += 1
        if std['status'] in ('withdrawn', 'superseded'):
            warn[std['is_no']] = {'is_no': std['is_no'], 'status': std['status'], 'superseded_by': std['superseded_by'], 'title': std['title'],
                                  'hs8_rows': warn.get(std['is_no'], {}).get('hs8_rows', 0) + 1}
    return joined, ambiguous, missing, sorted(warn.values(), key=lambda w: w['is_no'])


def build(root=REPO, files=None):
    """-> {'rows','csv','json','report'}. `files` optionally overrides repo files by relative path (bytes), as the refresh stage does."""
    files = files or {}
    raw = {rel: _read(root, rel, files) for rel in [ITC, CHAP, REG, EVENTS, PRODUCTS, CANDS, STEEL, APP3] + sorted(LISTS) + [
        'data/bis/isi_qco.csv', 'data/bis/qco_upcoming.csv']}
    sha = {rel: _sha(b) for rel, b in raw.items()}
    itc = [r for r in _csv(raw[ITC]) if r['level'] == '8']
    chap = _csv(raw[CHAP])
    register = {r['slug']: r for r in _csv(raw[REG])}
    products = _csv(raw[PRODUCTS])
    events = collections.defaultdict(list)
    for e in _csv(raw[EVENTS]):
        events[e['slug']].append(e)

    cond = collections.defaultdict(dict)  # (chapter, serial) -> {text: notification}
    for c in chap:
        if c['note_type'] == 'Policy Condition' and c['serial_no'].strip().isdigit():
            cond[(c['chapter'], int(c['serial_no']))][clean(c['text'])] = (c['notification_no'], _date(c['notification_date']))

    def qco_facts(slug):
        ev = events.get(slug, [])
        reg = register[slug]
        so = []
        for kinds in (('notified', 'order'), ('amended', 'extended', 'enforcement', 'exemption', 'rescinded', 'superseded')):
            for e in ev:
                if e['kind'] in kinds:
                    so += [re.sub(r'\s+', '', m) for m in SO.findall(e['text'])]
            if so:
                break
        legal = '; '.join(dict.fromkeys('S.O. ' + re.sub(r'^S\.?O\.?(No\.?)?', '', s, flags=re.I) for s in so)) or reg['title']
        enf = sorted(e['date'] for e in ev if e['kind'] == 'enforcement' and e['date'])
        resc = sorted(e['date'] for e in ev if e['kind'] == 'rescinded' and e['date'])
        state = reg['state']
        status = {'in_force': 'in_force', 'notified': 'upcoming'}.get(state, 'withdrawn')
        return {'legal': legal, 'from': enf[0] if enf else _date(reg['first_date']), 'to': resc[-1] if status == 'withdrawn' and resc else '',
                'status': status, 'title': reg['title']}

    def _parts(codes):
        d = collections.defaultdict(set)
        for b, pt in is_refs(codes):
            if pt:
                d[b].add(pt)
        return d

    # IS base number -> BIS list entries
    index = collections.defaultdict(list)
    for p in products:
        if p['source_file'] in ('isi_qco.csv', 'qco_upcoming.csv'):
            typ, doc = ('bis_upcoming_qco', 'BIS-ISI-UPCOMING') if p['source_file'] == 'qco_upcoming.csv' else ('bis_isi_qco', 'BIS-ISI')
            for b in is_bases(p['is_codes']):
                index[b].append({'parts': _parts(p['is_codes']), 'kind': 'qco', 'slug': p['slug'], 'type': typ, 'doc': doc, 'name': p['product_name'], 'file': 'data/bis/' + p['source_file'],
                                 'enf': _date(p['enforcement_date'])})
    for rel, (typ, doc) in LISTS.items():
        for n, r in enumerate(_csv(raw[rel]), start=1):
            for b in is_bases(r['is_codes']):
                index[b].append({'parts': _parts(r['is_codes']), 'kind': 'list', 'type': typ, 'doc': doc, 'name': r['product_name'], 'file': rel, 'row': r, 'n': n,
                                 'slug': CRS_GENERIC if rel == 'data/bis/crs.csv' else ''})

    app3 = collections.defaultdict(list)
    for a in _csv(raw[APP3]):
        for b, pt in is_refs(a['is_code']):
            app3[b].append({'serial': a['serial'], 'parts': {b: {pt}} if pt else {}})

    out, seen = [], set()
    stats = collections.Counter()
    mapped_slugs = collections.defaultdict(set)

    def add(**kw):
        row = {c: '' for c in COLS}
        row.update(kw)
        row['hs6'] = row['hs8'][:6]
        key = (row['hs8'], row['measure_type'], row['measure_value'], row['document_code'], row['legal_ref'], row['basis'], row['qco_slug'])
        if key in seen:
            return
        seen.add(key)
        out.append(row)

    official_is = set()
    dup = collections.Counter(r['hs_code'] for r in itc)
    nth = collections.Counter()
    for r in itc:
        hs, ch, asof = r['hs_code'], r['chapter'], r['as_of']
        nth[hs] += 1
        suffix = ' [source line %d of %d for this code]' % (nth[hs], dup[hs]) if dup[hs] > 1 else ''
        base = {'hs8': hs, 'as_of': asof, 'confidence': 'official', 'status': 'in_force'}
        itc_src = {'source_file': ITC, 'source_sha256': sha[ITC]}
        raw_policy = r['policy'].strip()
        add(**base, **itc_src, measure_type='import_policy', measure_value=_norm_policy(raw_policy), legal_ref=r['notification_no'],
            valid_from=_date(r['notification_date']),
            basis='row policy' + (" ('%s' in source)" % raw_policy if raw_policy and _norm_policy(raw_policy) != raw_policy else '')
            + (' (blank in source)' if not raw_policy else '') + suffix)
        texts = []  # (text, basis, legal_ref, valid_from)
        rt = clean(r['condition_text'])
        if rt:
            texts.append((rt, 'row condition', r['notification_no'], _date(r['notification_date'])))
            add(**base, **itc_src, measure_type='policy_condition', measure_value=_norm_policy(raw_policy), condition_text=rt,
                document_code='DGFT-LIC' if re.search(r'licen[cs]e', rt, re.I) else '', legal_ref=r['notification_no'],
                valid_from=_date(r['notification_date']), basis='row condition')
        for s in [x for x in r['condition_ref'].split(';') if x.strip().isdigit()]:
            hit = cond.get((ch, int(s)))
            if not hit:
                stats['chapter_condition_not_found'] += 1
                continue
            for t, (nn, nd) in hit.items():
                if not t:
                    continue
                b = 'chapter condition %d' % int(s)
                texts.append((t, b, nn, nd))
                add(**base, source_file=ITC + ';' + CHAP, source_sha256=sha[ITC] + ';' + sha[CHAP], measure_type='policy_condition',
                    measure_value=_norm_policy(raw_policy), condition_text=t, document_code='DGFT-LIC' if re.search(r'licen[cs]e', t, re.I) else '',
                    legal_ref=nn or ('ITC(HS) 2022 Schedule 1, chapter %s, policy condition %d' % (ch, int(s))), valid_from=nd, basis=b)
        # import monitoring systems named in the text
        for t, b, nn, nd in texts:
            for code, name in monitoring(t):
                add(**base, source_file=ITC + (';' + CHAP if b != 'row condition' else ''),
                    source_sha256=sha[ITC] + (';' + sha[CHAP] if b != 'row condition' else ''), measure_type='import_monitoring',
                    measure_value=code if code != 'IMS' else name, condition_text=t, document_code=code, legal_ref=nn or
                    ('ITC(HS) 2022 Schedule 1, chapter %s' % ch), valid_from=nd, basis=b + ': names ' + name)
        # IS numbers named in the text
        for t, b, nn, nd in texts:
            for ref in is_refs(t):
                ib = ref[0]
                official_is.add(hs)
                for e in _compatible(ref, app3.get(ib, [])):
                    add(**base, source_file=ITC + (';' + CHAP if b != 'row condition' else '') + ';' + APP3,
                        source_sha256=sha[ITC] + (';' + sha[CHAP] if b != 'row condition' else '') + ';' + sha[APP3], measure_type='bis_isi_qco',
                        measure_value='IS %s' % ib, condition_text=t, document_code='BIS-APP3',
                        legal_ref='ITC(HS) 2022 Schedule 1, Appendix III, serial %s' % e['serial'], valid_from=nd,
                        basis='%s: names IS %s; Appendix III serial %s' % (b, ib, e['serial']))
                hits = _compatible(ref, index.get(ib, []))
                src = ITC + (';' + CHAP if b != 'row condition' else '')
                srcsha = sha[ITC] + (';' + sha[CHAP] if b != 'row condition' else '')
                if not hits:
                    add(**base, source_file=src, source_sha256=srcsha, measure_type='other_condition', measure_value='IS %s' % ib, condition_text=t,
                        document_code='BIS-STD', legal_ref=nn or 'ITC(HS) 2022 Schedule 1, line %s' % hs, valid_from=nd,
                        basis=b + ': names IS %s; no BIS compulsory-certification list carries it' % ib)
                    stats['is_named_unmatched'] += 1
                    continue
                grouped = {}
                for h in hits:
                    if h['kind'] == 'list':
                        k = (h['type'], h['doc'], h['file'])
                        g = grouped.setdefault(k, dict(h, rows=[]))
                        g['rows'].append(h)
                    else:
                        grouped[('qco', h['slug'])] = h
                for h in grouped.values():
                    if h['kind'] == 'qco':
                        f = qco_facts(h['slug'])
                        valid_from = h['enf'] or f['from']
                        add(**base | {'status': f['status']}, source_file=src + ';' + REG, source_sha256=srcsha + ';' + sha[REG],
                            measure_type=h['type'], measure_value='IS %s' % ib, condition_text=t, document_code=h['doc'], legal_ref=f['legal'],
                            valid_from=valid_from, valid_to=f['to'], qco_slug=h['slug'],
                            basis='%s: names IS %s; QCO register record "%s"' % (b, ib, f['title']))
                        mapped_slugs[h['slug']].add(hs)
                    else:
                        rel, rows_ = h['file'], h['rows']
                        row = rows_[0]['row']
                        so, sls = [], []
                        for e in rows_:
                            note = e['row']['notes']
                            so += [re.sub(r'\s+', ' ', m) for m in SO.findall(note)]
                            sl = re.search(r'\b(Sl|Sr|List serial)\s+([\d.()a-z]+)', note)
                            sls.append(sl.group(0) if sl else 'row %d' % e['n'])
                        so = list(dict.fromkeys(so))
                        sls = list(dict.fromkeys(sls))
                        legal = '; '.join(so) or ('%s %s' % (row['scheme'], ', '.join(sls[:8]) + (' (+%d more)' % (len(sls) - 8) if len(sls) > 8 else '')))
                        enf = _date(row.get('enforcement_date', ''))
                        st = 'in_force' if any(e['row']['status'] == 'active' for e in rows_) else (
                            'upcoming' if row['status'] == 'upcoming' else 'withdrawn')
                        add(**base | {'status': st}, source_file=src + ';' + rel, source_sha256=srcsha + ';' + sha[rel], measure_type=h['type'],
                            measure_value='IS %s' % ib, condition_text=t, document_code=h['doc'], legal_ref=legal, valid_from=enf,
                            qco_slug=h['slug'], basis='%s: names IS %s; %s, %d list entr%s (first: "%s")' % (
                                b, ib, row['scheme'], len(rows_), 'y' if len(rows_) == 1 else 'ies', row['product_name'][:70]))
                        if h['slug']:
                            mapped_slugs[h['slug']].add(hs)

    # HS column printed in the 2020 Steel QCO gazette PDFs
    itc_codes = {r['hs_code']: r for r in itc}
    steel_missing = set()
    for st in _csv(raw[STEEL]):
        r = itc_codes.get(st['hs_code'])
        if not r:
            steel_missing.add(st['hs_code'])
            continue
        f = qco_facts(st['qco_slug'])
        pages = st['pages'].replace(';', ', ')
        add(hs8=st['hs_code'], as_of=r['as_of'], confidence='official', status=f['status'], source_file=STEEL + ';' + REG,
            source_sha256=sha[STEEL] + ';' + sha[REG], measure_type='bis_isi_qco', measure_value=f['title'], document_code='BIS-ISI',
            legal_ref=st['so_number'] + ' (HS column); the QCO register lists the order as in force under later S.O. numbers',
            valid_from=st['order_date'], valid_to='', qco_slug=st['qco_slug'],
            basis='QCO %s HS column, page%s %s' % (st['so_number'], 's' if ';' in st['pages'] else '', pages))
        mapped_slugs[st['qco_slug']].add(st['hs_code'])

    # keyword candidates: only where no explicit IS tie or named system already describes the code
    named_ims = {m['hs8'] for m in out if m['measure_type'] == 'import_monitoring'}
    for c in _csv(raw[CANDS]):
        hs = c['hs_code']
        for hint in c['scheme_hint'].split(';'):
            if hint in MONITORING_HINTS:
                if hs in named_ims:
                    continue
                typ, doc, val = 'import_monitoring', hint if hint != 'import_monitoring' else 'IMS', hint
            elif hint in ('IS', 'BIS') and hs in official_is:
                continue
            else:
                typ, doc = CAND_MAP[hint]
                val = ''
            add(hs8=hs, as_of=c['as_of'], confidence='candidate', status='in_force', measure_type=typ, measure_value=val,
                condition_text=clean(c['condition_text']), document_code=doc, legal_ref='ITC(HS) 2022 Schedule 1, line %s' % hs,
                basis='candidate: keyword "%s" in the condition text' % c['matched_terms'], source_file=CANDS, source_sha256=sha[CANDS])

    try:
        std_rows = _csv(_read(root, ISSTD, files))
    except FileNotFoundError:
        std_rows = []
    joined, ambiguous, no_std, std_warn = join_standards(out, std_rows)
    tidx = {t: i for i, t in enumerate(TYPE_ORDER)}
    out.sort(key=lambda m: (m['hs8'], tidx[m['measure_type']], m['measure_value'], m['basis'], m['legal_ref'], m['qco_slug']))

    buf = io.StringIO(newline='')
    w = csv.DictWriter(buf, fieldnames=COLS, lineterminator='\n')
    w.writeheader()
    w.writerows(out)
    by_type = collections.Counter(m['measure_type'] for m in out)
    mapped = {s for s in mapped_slugs}
    unmapped = sorted(set(register) - mapped)
    by_conf = collections.Counter(m['confidence'] for m in out)
    report = {
        'rows': len(out), 'rows_by_type': dict(sorted(by_type.items())), 'rows_by_confidence': dict(sorted(by_conf.items())),
        'hs8_codes': len(itc), 'hs8_with_import_policy_row': by_type['import_policy'],
        'hs8_with_a_bis_row': len({m['hs8'] for m in out if m['measure_type'].startswith('bis_') and m['confidence'] == 'official'}),
        'qco_records': len(register), 'qco_mapped_to_hs': len(mapped), 'qco_unmapped_to_hs': unmapped,
        'is_named_in_itchs_but_on_no_bis_list': stats['is_named_unmatched'], 'chapter_condition_refs_not_found': stats['chapter_condition_not_found'],
        'note': 'A BIS measure is attached to an HS code only where the ITC(HS) text for that code (or the chapter policy condition it cites) '
                'names an IS number carried by a BIS list or by DGFT Appendix III, or where the HS column of the 2020 Steel QCO gazette PDFs prints the code. No official text held in this repository ties the other QCOs, or any TEC MTCTE, '
                'BEE or CRS entry, to an HS code, so those are unmapped, not absent.',
        'is_standards_join': {'rows_with_title_and_status': joined, 'rows_status_not_known': sum(1 for m in out if m['is_title'] and m['is_status'] == 'unknown'),
                              'rows_multi_part_standard_not_guessed': ambiguous, 'rows_standard_not_in_table': no_std,
                              'warning_standard_withdrawn_or_superseded': std_warn,
                              'note': 'DATA-QUALITY warning only: the measure status is never changed from this signal.'},
        'steel_hs_columns_not_in_itchs': sorted(steel_missing),
        'lists_with_no_hs_link': ['data/tec/mtcte.csv', 'data/bee/mandatory.csv', 'data/bee/voluntary.csv'],
    }
    return {'rows': out, 'csv': buf.getvalue().encode('utf-8'),
            'json': (json.dumps(out, ensure_ascii=False, separators=(',', ':')) + '\n').encode('utf-8'),
            'report': (json.dumps(report, indent=1, ensure_ascii=False) + '\n').encode('utf-8')}


def main():
    o = build()
    d = os.path.join(REPO, 'data', 'measures')
    os.makedirs(d, exist_ok=True)
    for name, key in (('measures.csv', 'csv'), ('measures.json', 'json'), ('BUILD-REPORT.json', 'report')):
        with open(os.path.join(d, name), 'wb') as fh:
            fh.write(o[key])
    print(o['report'].decode())


if __name__ == '__main__':
    main()
