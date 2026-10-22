"""Shared helpers for the adapter golden tests (test_adapter_*.py). Stdlib only."""
import csv
import hashlib
import io
import json
import os
import shutil
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.normpath(os.path.join(HERE, '..'))
sys.path.insert(0, REPO)
import importlib  # noqa: E402

import pipeline.adapters as A  # noqa: E402

RAW = os.path.join(REPO, 'raw')
GOLD = os.path.join(HERE, 'golden')
TODAY = '2026-10-22'
REGEN = bool(os.environ.get('GOLDEN_REGEN'))  # GOLDEN_REGEN=1 python3 -m pytest tests rewrites golden/ (review the diff before committing)
HAVE_PDF = shutil.which('pdftohtml') is not None
needs_pdf = unittest.skipUnless(HAVE_PDF or os.environ.get('CI'), 'pdftohtml (poppler-utils) is not installed')

ARCHIVES = {
    'isi_qco.csv': 'bis-scheme1/2026-10-21/www.bis.gov.in_scheme-1_2026-10-21.html',
    'scheme_ii_other.csv': 'bis-scheme2/2026-10-21/www.bis.gov.in_scheme-ii_2026-10-21.html',
    'scheme_iv.csv': 'bis-scheme4/2026-10-21/www.bis.gov.in_scheme-4_2026-10-21.html',
    'scheme_x.csv': 'bis-schemex/2026-10-21/www.bis.gov.in_scheme-x_2026-10-21.html',
    'qco_upcoming.csv': 'bis-upcoming/2026-10-21/www.bis.gov.in_upcoming-qcos_2026-10-21.html',
    'simplified_2024.csv': 'bis-option2/2026-10-21/www.bis.gov.in_simplified-2024_2026-10-21.pdf',
    'mtcte.csv': 'tec-mtcte/2026-10-21/mtcte.tec.gov.in_ProductsList_2026-10-21.pdf',
}
BEE_M, BEE_V = 'bee-mandatory/2026-10-22/www.beestarlabel.com_EquipmentSchemes-M_2026-10-22.html', 'bee-voluntary/2026-10-21/www.beestarlabel.com_EquipmentSchemes-V_2026-10-21.html'
PARSERS = {  # list file -> (module, function); imported on demand so each adapter's tests stand alone
    'isi_qco.csv': ('pipeline.adapter_bis', 'parse_scheme1'), 'scheme_ii_other.csv': ('pipeline.adapter_bis', 'parse_scheme2_other'), 'scheme_iv.csv': ('pipeline.adapter_bis', 'parse_scheme4'),
    'scheme_x.csv': ('pipeline.adapter_bis', 'parse_scheme_x'), 'qco_upcoming.csv': ('pipeline.adapter_bis', 'parse_upcoming'),
    'simplified_2024.csv': ('pipeline.adapter_pdf', 'parse_simplified'), 'mtcte.csv': ('pipeline.adapter_pdf', 'parse_mtcte'),
}
BIG = {'isi_qco.csv', 'simplified_2024.csv'}  # golden = counts + hash + sample rows


def raw(name):
    with open(os.path.join(RAW, name), 'rb') as fh:
        return fh.read()


def urls():
    from pipeline import sources as S
    u = {'isi_qco.csv': S.LISTS[0]['url'], 'scheme_ii_other.csv': S.LISTS[1]['url'], 'scheme_iv.csv': S.LISTS[3]['url'],
         'scheme_x.csv': S.LISTS[4]['url'], 'qco_upcoming.csv': S.LISTS[5]['url'], 'simplified_2024.csv': S.LISTS[6]['url'], 'mtcte.csv': S.LISTS[7]['url']}
    out = {k: {'url': v} for k, v in u.items()}
    out['bee.csv'] = {'urls': {'mandatory': S.BEE['mandatory']['url'], 'voluntary': S.BEE['voluntary']['url']}}
    return out


def parser(file):
    mod, fn = PARSERS[file]
    return getattr(importlib.import_module(mod), fn)


def parse(file):
    if file == 'bee.csv':
        u = urls()['bee.csv']['urls']
        return importlib.import_module('pipeline.adapter_bee').parse_bee(raw(BEE_M), raw(BEE_V), u['mandatory'], u['voluntary'], TODAY)
    return parser(file)(raw(ARCHIVES[file]), urls()[file]['url'], TODAY)


def read_csv_rows(path):
    with open(path, newline='', encoding='utf-8') as fh:
        return list(csv.DictReader(fh))


def as_csv(rows):
    buf = io.StringIO(newline='')
    w = csv.DictWriter(buf, fieldnames=A.COLS, lineterminator='\n')
    w.writeheader()
    for r in rows:
        w.writerow({c: r.get(c, '') for c in A.COLS})
    return buf.getvalue().encode('utf-8')


def golden_path(file):
    return os.path.join(GOLD, file if file not in BIG else file.replace('.csv', '.json'))


def summary_of(parsed):
    rows = parsed.rows
    return {
        'rows': len(rows), 'source_rows': parsed.source_rows, 'page_date': parsed.page_date, 'sha256': hashlib.sha256(as_csv(rows)).hexdigest(),
        'statuses': {k: sum(1 for r in rows if r['status'] == k) for k in sorted({r['status'] for r in rows})},
        'sample': [rows[i] for i in sorted({0, 1, len(rows) // 3, len(rows) // 2, 2 * len(rows) // 3, len(rows) - 2, len(rows) - 1})],
        'parse_notes': parsed.notes,
    }



class GoldenCheck:
    """Mixin with check(file): the parser output for the archived copy equals golden/."""

    def check(self, file):
        parsed = parse(file)
        self.assertEqual(parsed.source_rows, len(parsed.rows), 'rows parsed != rows counted in the source')
        path = golden_path(file)
        if REGEN:
            os.makedirs(GOLD, exist_ok=True)
            if file in BIG:
                with open(path, 'w', encoding='utf-8') as fh:
                    json.dump(summary_of(parsed), fh, indent=1, ensure_ascii=False)
                    fh.write('\n')
            else:
                with open(path, 'wb') as fh:
                    fh.write(as_csv(parsed.rows))
        if file in BIG:
            with open(path, encoding='utf-8') as fh:
                gold = json.load(fh)
            got = summary_of(parsed)
            for k in ('rows', 'source_rows', 'page_date', 'statuses', 'parse_notes', 'sample'):
                self.assertEqual(gold[k], got[k], k)
            self.assertEqual(gold['sha256'], got['sha256'], 'the parsed rows differ from the golden rows')
        else:
            with open(path, 'rb') as fh:
                want = list(csv.DictReader(io.StringIO(fh.read().decode('utf-8'), newline='')))
            self.assertEqual(len(want), len(parsed.rows))
            for i, (w, g) in enumerate(zip(want, parsed.rows)):
                self.assertEqual(w, g, 'row %d differs' % (i + 1))
