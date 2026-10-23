"""Imports the two official HS-linked inputs into data/hs-links/ and archives their PDFs under raw/hs-links/<date>/.

    python -m pipeline.hs_links INPUT_DIR [--today YYYY-MM-DD]

INPUT_DIR holds `steel-qco-hs-rows.csv` (hs_code, source_url, page, raw_sha256, source; one row per HS code per page printed in the three 2020
Steel QCO gazette PDFs, text layer only), `appendix3.csv` (serial, is_code, description, section, notes, source_page: DGFT Appendix III, which lists
IS numbers and no HS codes) and `pdf/` with the PDFs. This is a one-off import: the outputs are static inputs of pipeline.measures.
"""
import csv
import hashlib
import io
import os
import sys

REPO = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
STEEL_PDFS = {  # basename -> (S.O. printed on the order, order date)
    'Steel-QCO-14022020-1.pdf': ('S.O. 756(E)', '2020-02-14'),
    'Steel-QCO-2020-dated-27th-May-2020.pdf': ('S.O. 1673(E)', '2020-05-27'),
    'Steel-QCO-dated-17-July-2020-with-corrigendum.pdf': ('S.O. 2379(E)', '2020-07-17'),
}
APP3_PDF = 'dgft-import-policy-appendix-III-bis-mandatory.pdf'
APP3_URL = 'https://content.dgft.gov.in/Website/dgftprod/c57aadc6-40b1-4688-b898-102e8aaa14c1/Appendix-III-updated (1).pdf'
STEEL_SLUG = 'steel-and-steel-products-quality-control-order-2020'
STEEL_COLS = ['hs_code', 'qco_slug', 'so_number', 'order_date', 'pages', 'source_url', 'raw_sha256']
APP3_COLS = ['serial', 'is_code', 'description', 'section', 'notes', 'source_page']
PROV_COLS = ['file', 'source_url', 'retrieved_on', 'sha256', 'rows', 'source_rows', 'page_date', 'parser', 'raw_file', 'raw_sha256', 'raw_bytes',
             'raw_committed', 'fetch_method', 'fetch_tier', 'fetch_cost_usd']
MAX_COMMIT = 2_000_000


def _csv(cols, rows):
    b = io.StringIO(newline='')
    w = csv.DictWriter(b, fieldnames=cols, lineterminator='\n')
    w.writeheader()
    w.writerows(rows)
    return b.getvalue().encode('utf-8')


def _sha(b):
    return hashlib.sha256(b).hexdigest()


def run(inp, root=REPO, today='2026-10-22'):
    rows = [r for r in csv.DictReader(open(os.path.join(inp, 'steel-qco-hs-rows.csv'), encoding='utf-8', newline='')) if r['source'] == 'text_layer']
    by_url = {}
    for r in rows:
        by_url.setdefault(r['source_url'], []).append(r)
    steel, prov, raw_dir = [], [], os.path.join(root, 'raw', 'hs-links', today)
    os.makedirs(raw_dir, exist_ok=True)
    per_pdf = {}
    for url, rs in sorted(by_url.items()):
        name = url.rsplit('/', 1)[1]
        so, date = STEEL_PDFS[name]
        data = open(os.path.join(inp, 'pdf', name), 'rb').read()
        assert _sha(data) == rs[0]['raw_sha256'] and all(r['raw_sha256'] == _sha(data) for r in rs), name
        pages = {}
        for r in rs:
            pages.setdefault(r['hs_code'], set()).add(int(r['page']))
        for hs, pg in sorted(pages.items()):
            steel.append({'hs_code': hs, 'qco_slug': STEEL_SLUG, 'so_number': so, 'order_date': date, 'pages': ';'.join(map(str, sorted(pg))),
                          'source_url': url, 'raw_sha256': _sha(data)})
        per_pdf[url] = (name, data, len(rs))
    steel.sort(key=lambda r: (r['order_date'], r['hs_code']))
    app3 = [{k: r[k] for k in APP3_COLS} for r in csv.DictReader(open(os.path.join(inp, 'itchs_appendix3_bis.csv'), encoding='utf-8', newline=''))]
    assert all(not r['hs_code'] for r in csv.DictReader(open(os.path.join(inp, 'itchs_appendix3_bis.csv'), encoding='utf-8', newline='')))
    app3_pdf = open(os.path.join(inp, 'pdf', APP3_PDF), 'rb').read()
    out = os.path.join(root, 'data', 'hs-links')
    os.makedirs(out, exist_ok=True)
    sb, ab = _csv(STEEL_COLS, steel), _csv(APP3_COLS, app3)
    open(os.path.join(out, 'steel-qco-hs-columns.csv'), 'wb').write(sb)
    open(os.path.join(out, 'appendix3-bis.csv'), 'wb').write(ab)

    def archive(name, data):
        committed = len(data) < MAX_COMMIT
        rel = 'raw/hs-links/%s/%s' % (today, name)
        if committed:
            open(os.path.join(root, rel), 'wb').write(data)
        return rel, 'yes' if committed else 'no (over 2 MB: URL and hash only)'
    parts = []
    for url, (name, data, n) in sorted(per_pdf.items(), key=lambda kv: STEEL_PDFS[kv[1][0]][1]):
        rel, c = archive(name, data)
        parts.append((url, rel, _sha(data), len(data), c, n))
    prov.append({'file': 'steel-qco-hs-columns.csv', 'source_url': ' ; '.join(p[0] for p in parts), 'retrieved_on': today, 'sha256': _sha(sb),
                 'rows': len(steel), 'source_rows': len(steel),
                 'parser': 'HS column of the three gazette PDFs (text layer), one row per HS code per order with its page numbers; %d page-level rows read' % sum(p[5] for p in parts),
                 'raw_file': ' ; '.join(p[1] for p in parts), 'raw_sha256': ' ; '.join(p[2] for p in parts), 'raw_bytes': sum(p[3] for p in parts),
                 'raw_committed': ' ; '.join(p[4] for p in parts)})
    rel, c = archive(APP3_PDF, app3_pdf)
    prov.append({'file': 'appendix3-bis.csv', 'source_url': APP3_URL, 'retrieved_on': today, 'sha256': _sha(ab), 'rows': len(app3), 'source_rows': len(app3),
                 'parser': 'Appendix III table of IS numbers (no HS codes) read from the PDF text layer', 'raw_file': rel, 'raw_sha256': _sha(app3_pdf),
                 'raw_bytes': len(app3_pdf), 'raw_committed': c})
    open(os.path.join(out, 'PROVENANCE.csv'), 'wb').write(_csv(PROV_COLS, prov))
    return len(steel), len(app3)


if __name__ == '__main__':
    a = sys.argv[1:]
    today = a[a.index('--today') + 1] if '--today' in a else '2026-10-22'
    print(run(a[0], today=today))
