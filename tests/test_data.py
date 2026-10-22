"""The published data: counts, invariants, and agreement with the parsers run over the archived raw copies."""
import csv
import glob
import hashlib
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from testkit import HAVE_PDF, REPO  # noqa: E402


def rows(rel):
    with open(os.path.join(REPO, rel), newline='', encoding='utf-8') as fh:
        return list(csv.DictReader(fh))


class ItchsTest(unittest.TestCase):
    D = 'data/itchs/2022'

    def test_ninety_seven_chapters_and_the_build_report_passed(self):
        rep = json.load(open(os.path.join(REPO, self.D, 'BUILD-REPORT.json'), encoding='utf-8'))
        self.assertEqual(97, rep['chapters'])
        self.assertGreater(rep['rows_8digit'], 12000)
        self.assertTrue(rep['all_passed'])
        for c in rep['per_chapter']:
            self.assertEqual(c['items_in_export'], c['rows_parsed'], c['chapter'])
            self.assertEqual(c['notes_in_export'], c['notes_parsed'], c['chapter'])

    def test_all_csv_is_the_concatenation_of_the_chapter_files(self):
        allr = rows(self.D + '/all.csv')
        parts = []
        for ch in sorted({r['chapter'] for r in allr}):
            parts += rows('%s/ch%s.csv' % (self.D, ch))
            j = json.load(open(os.path.join(REPO, self.D, 'ch%s.json' % ch), encoding='utf-8'))
            self.assertEqual(len(j['rows']), len(rows('%s/ch%s.csv' % (self.D, ch))))
        self.assertEqual(allr, parts)
        self.assertEqual(sum(1 for r in allr if r['level'] == '8'), json.load(open(os.path.join(REPO, self.D, 'BUILD-REPORT.json')))['rows_8digit'])

    def test_the_chapter_files_agree_with_the_provenance_counts(self):
        for p in rows(self.D + '/PROVENANCE.csv'):
            ch = p['chapter']
            n8 = sum(1 for r in rows('%s/ch%s.csv' % (self.D, ch)) if r['level'] == '8')
            self.assertEqual(int(p['rows_in_json']), n8, ch)
            self.assertEqual('DGFTCOMS-2026-24H4345L', p['permission_ref'])

    def test_archived_raw_bytes_match_the_recorded_hashes(self):
        for p in rows(self.D + '/PROVENANCE.csv'):
            found = [open(f, 'rb').read() for f in glob.glob(os.path.join(REPO, 'raw', 'dgft-itchs-2022', '*', 'ch%s.json' % p['chapter']))]
            self.assertIn(p['sha256'], [hashlib.sha256(b).hexdigest() for b in found], p['chapter'])
            self.assertIn(int(p['bytes']), [len(b) for b in found])

    def test_html_is_gone_from_text_columns(self):
        for r in rows(self.D + '/all.csv'):
            for c in ('description', 'condition_text'):
                self.assertNotRegex(r[c], r'<[a-z/][^>]*>', r['hs_code'])
        for r in rows(self.D + '/chapter-conditions.csv'):
            self.assertNotRegex(r['text'], r'<[a-z/][^>]*>')

    def test_chapter_conditions_exist_for_policy_chapters(self):
        notes = rows(self.D + '/chapter-conditions.csv')
        self.assertGreater(len(notes), 700)
        self.assertGreater(sum(1 for n in notes if n['note_type'] == 'Policy Condition'), 100)


class ListsTest(unittest.TestCase):
    """The committed CSV equals what the parser reads from the newest archived raw copy: the published file is reproducible."""

    def test_every_list_is_reproducible_from_its_newest_raw_copy(self):
        from pipeline import refresh as rf
        from pipeline import sources as S
        for spec in S.LISTS:
            if spec['ext'] == 'pdf' and not HAVE_PDF:
                continue
            with self.subTest(spec['out']):
                date, path = rf.newest_raw(REPO, spec['id'])
                parsed = spec['parse'](open(path, 'rb').read(), spec['url'], date)
                want = rows(spec['out'])
                self.assertEqual(len(want), len(parsed.rows))
                self.assertEqual(parsed.source_rows, len(parsed.rows))
                for w, g in zip(want, parsed.rows):
                    for k in w:
                        if k != 'retrieved_on':
                            self.assertEqual(w[k], g.get(k, ''), '%s %s' % (spec['out'], k))

    def test_list_sizes_are_in_the_expected_range(self):
        ranges = {'data/bis/isi_qco.csv': (500, 1500), 'data/bis/crs.csv': (50, 200), 'data/bis/qco_upcoming.csv': (20, 400), 'data/bis/option2.csv': (500, 3000),
                  'data/tec/mtcte.csv': (100, 600), 'data/bis/scheme_x.csv': (20, 200), 'data/bee/mandatory.csv': (10, 60), 'data/bee/voluntary.csv': (10, 80)}
        for rel, (lo, hi) in ranges.items():
            self.assertTrue(lo <= len(rows(rel)) <= hi, '%s has %d rows' % (rel, len(rows(rel))))

    def test_provenance_hashes_match_the_files_and_the_raw_copies(self):
        for d in ('bis', 'tec', 'bee'):
            for p in rows('data/%s/PROVENANCE.csv' % d):
                data = open(os.path.join(REPO, 'data', d, p['file']), 'rb').read()
                self.assertEqual(p['sha256'], hashlib.sha256(data).hexdigest(), p['file'])
                self.assertEqual(int(p['rows']), len(rows('data/%s/%s' % (d, p['file']))))
                self.assertEqual(p['rows'], p['source_rows'], 'parsed count must equal the source count: ' + p['file'])
                if p['raw_committed'] == 'yes':
                    raw = open(os.path.join(REPO, p['raw_file']), 'rb').read()
                    self.assertEqual(p['raw_sha256'], hashlib.sha256(raw).hexdigest(), p['raw_file'])


class QcoTest(unittest.TestCase):
    def test_register_links_events_and_products(self):
        reg, ev, prod = rows('data/qco/register.csv'), rows('data/qco/events.csv'), rows('data/qco/products.csv')
        slugs = {r['slug'] for r in reg}
        self.assertEqual(len(reg), len(slugs))
        self.assertTrue({e['slug'] for e in ev} <= slugs)
        self.assertTrue({p['slug'] for p in prod} <= slugs)
        j = json.load(open(os.path.join(REPO, 'data/qco/register.json'), encoding='utf-8'))
        self.assertEqual(len(reg), len(j))
        self.assertEqual(len(ev), sum(len(r['events']) for r in j))

    def test_gazette_hashes_align_with_the_urls(self):
        known = {r['source_url']: r['sha256'] for r in rows('data/qco/gazette-pdf-hashes.csv')}
        n = 0
        for r in rows('data/qco/register.csv'):
            urls = [u.strip() for u in r['pdf_urls'].split(' ; ') if u.strip()]
            hashes = r['gazette_pdf_sha256'].split(' ; ') if urls else []
            self.assertEqual(len(urls), len(hashes), r['slug'])
            for u, h in zip(urls, hashes):
                self.assertEqual(known[u], h)
                n += 1
        self.assertGreater(n, 100)


class DerivedTest(unittest.TestCase):
    def test_candidates_are_eight_digit_rows_whose_text_names_a_scheme(self):
        items = {r['hs_code']: r for r in rows('data/itchs/2022/all.csv') if r['level'] == '8'}
        cand = rows('data/derived/hs-scheme-candidates.csv')
        self.assertGreater(len(cand), 100)
        for c in cand:
            self.assertEqual(items[c['hs_code']]['condition_text'], c['condition_text'])
            self.assertEqual('keyword match on the official condition text; candidates only', c['method'])
            self.assertIn(c['matched_terms'].split(';')[0], c['condition_text'])

    def test_keywords(self):
        from pipeline import derived
        rows_ = [{'hs_code': '11111111', 'level': '8', 'chapter': '11', 'condition_text': 'Free subject to Compulsory Registration under CRS', 'as_of': 'x'},
                 {'hs_code': '22222222', 'level': '8', 'chapter': '22', 'condition_text': 'technical specifications apply; this is fine', 'as_of': 'x'},
                 {'hs_code': '3333', 'level': '4', 'chapter': '33', 'condition_text': 'BIS', 'as_of': 'x'}]
        got = derived.candidates(rows_)
        self.assertEqual(['11111111'], [g['hs_code'] for g in got])
        self.assertEqual('CRS', got[0]['scheme_hint'])


if __name__ == '__main__':
    unittest.main()
