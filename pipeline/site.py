"""Builds the static API and chapter pages (GitHub Pages) from data/measures and the ITC(HS) table. Plain files, no framework.

    python -m pipeline.site OUTDIR            # release read from CITATION.cff
    python -m pipeline.site OUTDIR --release v2026.10.24

Pages are `noindex` (and robots.txt disallows everything) until the release is v2026.10.24 or later.
"""
import collections
import csv
import html
import json
import os
import re
import sys

REPO = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
sys.path.insert(0, REPO)
from pipeline import measures as M  # noqa: E402

BASE = 'https://yashodhank.github.io/india-import-compliance-data'
REPO_URL = 'https://github.com/yashodhank/india-import-compliance-data'
INDEXABLE_FROM = 'v2026.10.24'
NOTICE = ('Not legal advice. Every row carries an as_of date and was true of its source on that date only. The official source prevails; '
          'confirm with the issuing authority before you ship, file or certify anything. Data CC BY 4.0, code MIT.')
M_FIELDS = ['measure_type', 'measure_value', 'condition_text', 'document_code', 'legal_ref', 'valid_from', 'valid_to', 'status', 'confidence', 'basis',
            'qco_slug']
STYLE = ('body{font:16px/1.5 system-ui,sans-serif;max-width:70rem;margin:1rem auto;padding:0 1rem}table{border-collapse:collapse;width:100%}'
         'th,td{border:1px solid #bbb;padding:.3rem .5rem;vertical-align:top;text-align:left}small{color:#444}code{background:#eee;padding:0 .2rem}')


def release_of(root):
    m = re.search(r'^version:\s*"?([^"\n]+)"?', open(os.path.join(root, 'CITATION.cff'), encoding='utf-8').read(), re.M)
    return m.group(1).strip()


def indexable(release):
    return release >= INDEXABLE_FROM


def _write(out, rel, text):
    p = os.path.join(out, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, 'w', encoding='utf-8', newline='\n') as fh:
        fh.write(text)


def _json(obj):
    return json.dumps(obj, ensure_ascii=False, separators=(',', ':')) + '\n'


def _e(s):
    return html.escape(s or '', quote=True)


def _page(title, body, robots):
    meta = '' if robots else '<meta name="robots" content="noindex,nofollow">\n'
    return ('<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n<meta name="viewport" content="width=device-width,initial-scale=1">\n'
            '%s<title>%s</title>\n<style>%s</style>\n</head>\n<body>\n%s\n<p><small>%s</small></p>\n</body>\n</html>\n') % (
        meta, _e(title), STYLE, body, _e(NOTICE))


def build(root, out, release=None):
    release = release or release_of(root)
    idx = indexable(release)
    itc = [r for r in M._csv(open(os.path.join(root, M.ITC), 'rb').read()) if r['level'] == '8']
    ms = json.load(open(os.path.join(root, 'data/measures/measures.json'), encoding='utf-8'))
    by_hs = collections.defaultdict(list)
    for m in ms:
        by_hs[m['hs8']].append({k: m[k] for k in M_FIELDS if m[k] != ''})
    counts = collections.Counter(m['measure_type'] for m in ms)
    as_of = max(r['as_of'] for r in itc)
    chapters = collections.defaultdict(list)
    seen = set()
    for r in itc:
        chapters[r['chapter']].append(r)
        if r['hs_code'] in seen:
            continue
        seen.add(r['hs_code'])
        _write(out, 'api/codes/%s.json' % r['hs_code'], _json({
            'hs8': r['hs_code'], 'hs6': r['hs6'], 'chapter': r['chapter'], 'description': r['description'], 'hs6_description': r['hs6_description'],
            'measures': by_hs[r['hs_code']], 'as_of': r['as_of'], 'release': release, 'notice': NOTICE}))
    for ch, rs in sorted(chapters.items()):
        codes, rows_html = [], []
        done = set()
        for r in rs:
            if r['hs_code'] in done:
                continue
            done.add(r['hs_code'])
            mm = by_hs[r['hs_code']]
            pol = next((m.get('measure_value', '') for m in mm if m['measure_type'] == 'import_policy'), '')
            codes.append({'hs8': r['hs_code'], 'hs6': r['hs6'], 'description': r['description'], 'policy': pol,
                          'measure_types': sorted({m['measure_type'] for m in mm if m['measure_type'] != 'import_policy'})})
            items = []
            for m in mm:
                if m['measure_type'] == 'import_policy':
                    continue
                t = m.get('condition_text', '')
                t = (t[:280] + '...') if len(t) > 280 else t
                items.append('<li><code>%s</code> %s%s%s%s<br><small>%s</small></li>' % (
                    _e(m['measure_type']), _e(m.get('measure_value', '')),
                    ' [%s]' % _e(m['document_code']) if m.get('document_code') else '', ' (%s)' % _e(m['status']) if m['status'] != 'in_force' else '',
                    ' <em>candidate</em>' if m['confidence'] == 'candidate' else '',
                    _e((m.get('legal_ref', '') + ' ' + t).strip())))
            rows_html.append('<tr><td><a href="../api/codes/%s.json">%s</a></td><td>%s</td><td>%s</td><td>%s</td></tr>' % (
                r['hs_code'], r['hs_code'], _e(r['description']), _e(pol), '<ul>%s</ul>' % ''.join(items) if items else ''))
        _write(out, 'api/chapters/%s.json' % ch, _json({'chapter': ch, 'codes': codes, 'release': release, 'as_of': as_of, 'notice': NOTICE}))
        body = ('<nav><a href="../index.html">All chapters</a></nav>\n<h1>ITC(HS) 2022, chapter %s</h1>\n<p>%d eight-digit codes. Import policy and the other '
                'measures that apply to each. Release %s, as of %s.</p>\n<table>\n<thead><tr><th>HS code</th><th>Description</th><th>Policy</th>'
                '<th>Other measures</th></tr></thead>\n<tbody>\n%s\n</tbody>\n</table>') % (ch, len(codes), _e(release), as_of, '\n'.join(rows_html))
        _write(out, 'chapters/%s.html' % ch, _page('India import compliance, chapter %s' % ch, body, idx))
    latest = {'release': release, 'as_of': as_of, 'indexable': idx, 'repository': REPO_URL, 'notice': NOTICE,
              'counts': {'hs8_codes': len(seen), 'hs8_lines': len(itc), 'chapters': len(chapters), 'measures': len(ms), 'measures_by_type': dict(sorted(counts.items())),
                         'measures_candidate': sum(1 for m in ms if m['confidence'] == 'candidate')}}
    _write(out, 'api/latest.json', _json(latest))
    links = ''.join('<li><a href="chapters/%s.html">Chapter %s</a> (%d codes)</li>' % (c, c, len({r['hs_code'] for r in rs})) for c, rs in sorted(chapters.items()))
    body = ('<h1>India import compliance data</h1>\n<p>What approval applies to a product at import into India, per 8-digit ITC(HS) code, as a table of '
            'measures. Release %s, as of %s. Source, licences and method: <a href="%s">%s</a>.</p>\n<p>Static JSON: <a href="api/latest.json">'
            'api/latest.json</a>, <code>api/codes/&lt;hs8&gt;.json</code>, <code>api/chapters/&lt;NN&gt;.json</code>; <a href="openapi.yaml">openapi.yaml</a>.'
            '</p>\n<ul>%s</ul>') % (_e(release), as_of, REPO_URL, REPO_URL, links)
    _write(out, 'index.html', _page('India import compliance data', body, idx))
    _write(out, 'robots.txt', ('User-agent: *\nAllow: /\nSitemap: %s/sitemap.xml\n' % BASE) if idx else 'User-agent: *\nDisallow: /\n')
    _write(out, 'sitemap.xml', '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n%s</urlset>\n' % ''.join(
        '<url><loc>%s/%s</loc></url>\n' % (BASE, p) for p in ['index.html'] + ['chapters/%s.html' % c for c in sorted(chapters)]))
    _write(out, '.nojekyll', '')
    _write(out, 'openapi.yaml', openapi(release))
    return latest['counts']


def openapi(release):
    return '''openapi: 3.0.3
info:
  title: India import compliance data (static)
  version: "%(r)s"
  description: >
    Static JSON files, not a live service. What import policy and product-compliance measures apply to an 8-digit ITC(HS) 2022 code.
    Not legal advice: every row carries an as_of date; the official source prevails. Data CC BY 4.0.
  license:
    name: CC BY 4.0
    url: https://creativecommons.org/licenses/by/4.0/
servers:
  - url: %(b)s
paths:
  /api/latest.json:
    get:
      summary: Release, as_of date and counts
      responses:
        "200":
          description: Release metadata
          content:
            application/json:
              schema:
                type: object
                properties:
                  release: {type: string}
                  as_of: {type: string, format: date}
                  counts: {type: object}
  /api/codes/{hs8}.json:
    get:
      summary: One 8-digit code with its description, hs6 and measures
      parameters:
        - {name: hs8, in: path, required: true, schema: {type: string, pattern: "^[0-9]{8}$"}}
      responses:
        "200":
          description: The code and its measures
          content:
            application/json:
              schema:
                type: object
                properties:
                  hs8: {type: string}
                  hs6: {type: string}
                  description: {type: string}
                  hs6_description: {type: string}
                  measures:
                    type: array
                    items:
                      type: object
                      properties:
                        measure_type: {type: string, enum: [import_policy, policy_condition, bis_isi_qco, bis_crs, bis_scheme_x, bis_upcoming_qco, tec_mtcte, bee_label, import_monitoring, other_condition]}
                        measure_value: {type: string}
                        condition_text: {type: string}
                        document_code: {type: string}
                        legal_ref: {type: string}
                        valid_from: {type: string, format: date}
                        valid_to: {type: string, format: date}
                        status: {type: string, enum: [in_force, upcoming, withdrawn]}
                        confidence: {type: string, enum: [official, candidate]}
                        basis: {type: string}
        "404":
          description: Not an 8-digit code in ITC(HS) 2022
  /api/chapters/{chapter}.json:
    get:
      summary: Every 8-digit code of a chapter with its policy and the measure types that apply
      parameters:
        - {name: chapter, in: path, required: true, schema: {type: string, pattern: "^[0-9]{2}$"}}
      responses:
        "200":
          description: Chapter listing
          content:
            application/json:
              schema:
                type: object
                properties:
                  chapter: {type: string}
                  codes: {type: array, items: {type: object}}
''' % {'r': release, 'b': BASE}


def main(argv=None):
    a = list(argv if argv is not None else sys.argv[1:])
    rel = None
    if '--release' in a:
        i = a.index('--release')
        rel = a[i + 1]
        del a[i:i + 2]
    out = a[0] if a else os.path.join(REPO, 'site')
    print(json.dumps(build(REPO, out, rel)))


if __name__ == '__main__':
    main()
