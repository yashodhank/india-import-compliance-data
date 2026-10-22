"""data/measures/measures.csv: one row per (hs8, measure), derived only from tables already in this repository."""
import csv
import json
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from schemacheck import REPO  # noqa: E402

sys.path.insert(0, REPO)
from pipeline import measures  # noqa: E402


def rows(rel):
    with open(os.path.join(REPO, rel), encoding='utf-8', newline='') as fh:
        return list(csv.DictReader(fh))


M = rows('data/measures/measures.csv')
ITC = rows('data/itchs/2022/all.csv')
HS8 = [r for r in ITC if r['level'] == '8']
REPORT = json.load(open(os.path.join(REPO, 'data/measures/BUILD-REPORT.json'), encoding='utf-8'))
TYPES = {'import_policy', 'policy_condition', 'bis_isi_qco', 'bis_crs', 'bis_scheme_x', 'bis_upcoming_qco', 'tec_mtcte', 'bee_label',
         'import_monitoring', 'other_condition'}


class HelperTest(unittest.TestCase):
    def test_is_bases(self):
        self.assertEqual(['13334', '14542'], measures.is_bases('must conform to IS 13334 (Part 1) and IS 14542'))
        self.assertEqual(['60947'], measures.is_bases('IS/IEC 60947: Part 2:2016'))
        self.assertEqual(['616'], measures.is_bases('IS 616 :2017 OR IS 616:2017 & IS 18112:2025')[:1])
        self.assertEqual([], measures.is_bases('Indian Standards and 2017'))

    def test_clean_strips_html_and_dash(self):
        self.assertEqual('a b & c', measures.clean('<p>a&nbsp;<b>b</b> &amp; c</p>'))
        self.assertEqual('', measures.clean('-'))

    def test_monitoring_systems(self):
        self.assertEqual(['SIMS'], [c for c, _ in measures.monitoring('subject to registration under SIMS')])
        self.assertEqual(['PIMS'], [c for c, _ in measures.monitoring('Paper Import Monitoring System')])
        self.assertEqual([], measures.monitoring('nothing here'))


class MeasuresTest(unittest.TestCase):
    def test_every_8digit_code_has_exactly_one_import_policy_row(self):
        pol = [m['hs8'] for m in M if m['measure_type'] == 'import_policy']
        self.assertEqual(12587, len(HS8))
        self.assertEqual(sorted(r['hs_code'] for r in HS8), sorted(pol))

    def test_import_policy_values(self):
        allowed = {'Free', 'Restricted', 'Prohibited', 'STE', ''}
        for m in M:
            if m['measure_type'] == 'import_policy':
                self.assertIn(m['measure_value'], allowed)
        src = {r['hs_code']: r['policy'] for r in HS8}
        for m in M:
            if m['measure_type'] == 'import_policy' and src[m['hs8']].startswith('Prohibited'):
                self.assertEqual('Prohibited', m['measure_value'])

    def test_enums_and_shapes(self):
        for m in M:
            self.assertIn(m['measure_type'], TYPES)
            self.assertIn(m['status'], ('in_force', 'upcoming', 'withdrawn'))
            self.assertIn(m['confidence'], ('official', 'candidate'))
            self.assertRegex(m['hs8'], r'^\d{8}$')
            self.assertEqual(m['hs8'][:6], m['hs6'])
            self.assertTrue(m['basis'])
            self.assertTrue(m['source_file'] and m['source_sha256'] and m['as_of'])
            self.assertNotRegex(m['condition_text'], r'<[a-z/][^>]*>')

    def test_no_bis_row_without_legal_ref(self):
        bad = [m for m in M if m['measure_type'].startswith('bis_') and not m['legal_ref']]
        self.assertEqual([], bad[:5])

    def test_candidates_are_flagged_and_only_candidates(self):
        for m in M:
            self.assertEqual(m['basis'].startswith('candidate'), m['confidence'] == 'candidate', m)

    def test_document_codes_are_documented(self):
        doc = open(os.path.join(REPO, 'docs/document-codes.md'), encoding='utf-8').read()
        codes = {m['document_code'] for m in M if m['document_code']}
        self.assertTrue(codes)
        for c in codes:
            self.assertIn('`%s`' % c, doc)

    def test_no_duplicate_rows(self):
        keys = [(m['hs8'], m['measure_type'], m['measure_value'], m['document_code'], m['legal_ref'], m['basis'], m['qco_slug']) for m in M]
        self.assertEqual(len(keys), len(set(keys)))

    def test_every_qco_register_record_is_mapped_or_reported_unmapped(self):
        reg = {r['slug'] for r in rows('data/qco/register.csv')}
        mapped = {m['qco_slug'] for m in M if m['qco_slug']}
        unmapped = set(REPORT['qco_unmapped_to_hs'])
        self.assertEqual(reg, mapped | unmapped)
        self.assertFalse(mapped & unmapped)
        self.assertEqual(len(reg), REPORT['qco_records'])
        self.assertEqual(len(mapped), REPORT['qco_mapped_to_hs'])

    def test_is_tie_comes_from_the_text(self):
        itc = {r['hs_code']: r for r in HS8}
        chap = rows('data/itchs/2022/chapter-conditions.csv')
        for m in M:
            if m['measure_type'] in ('bis_isi_qco', 'bis_crs', 'bis_scheme_x', 'bis_upcoming_qco') and m['confidence'] == 'official' and not m['basis'].startswith('QCO S.O.'):
                base = re.search(r'\d+', m['measure_value']).group(0)
                text = itc[m['hs8']]['condition_text'] + ' ' + ' '.join(c['text'] for c in chap if c['chapter'] == m['hs8'][:2])
                self.assertIn(base, measures.is_bases(text), m)

    def test_report_counts_match(self):
        by = {}
        for m in M:
            by[m['measure_type']] = by.get(m['measure_type'], 0) + 1
        self.assertEqual(by, REPORT['rows_by_type'])
        self.assertEqual(len(M), REPORT['rows'])

    def test_worked_examples(self):
        steel = [m for m in M if m['hs8'] == '72104100']
        self.assertEqual({'Free'}, {m['measure_value'] for m in steel if m['measure_type'] == 'import_policy'})
        self.assertTrue(any('IS 277' in m['measure_value'] for m in steel))
        phone = [m for m in M if m['hs8'] == '85171300']
        pol = [m for m in phone if m['measure_type'] == 'import_policy']
        self.assertEqual(1, len(pol))
        self.assertEqual('54/2015-2020', pol[0]['legal_ref'])

    def test_steel_hs_columns_become_measures(self):
        steel = rows('data/hs-links/steel-qco-hs-columns.csv')
        itc8 = {r['hs_code'] for r in HS8}
        have = {(m['hs8'], m['legal_ref'].split(' (')[0]) for m in M if m['basis'].startswith('QCO S.O.')}
        want = {(r['hs_code'], r['so_number']) for r in steel if r['hs_code'] in itc8}
        self.assertEqual(want, have)
        for m in M:
            if m['basis'].startswith('QCO S.O.'):
                self.assertEqual('bis_isi_qco', m['measure_type'])
                self.assertEqual('BIS-ISI', m['document_code'])
                self.assertEqual('steel-and-steel-products-quality-control-order-2020', m['qco_slug'])
                self.assertIn('HS column, page', m['basis'])
        self.assertEqual(sorted({r['hs_code'] for r in steel} - itc8), REPORT['steel_hs_columns_not_in_itchs'])

    def test_appendix3_is_an_additional_basis_where_the_text_names_the_is(self):
        app = {r['serial']: r for r in rows('data/hs-links/appendix3-bis.csv')}
        got = [m for m in M if m['document_code'] == 'BIS-APP3']
        self.assertTrue(got)
        for m in got:
            n = re.search(r'Appendix III serial (\d+)', m['basis']).group(1)
            self.assertIn(re.search(r'\d+', m['measure_value']).group(0), measures.is_bases(app[n]['is_code']))
            self.assertTrue(m['legal_ref'])

    def test_hs_link_inputs_are_archived_and_hashed(self):
        import hashlib
        for p in rows('data/hs-links/PROVENANCE.csv'):
            data = open(os.path.join(REPO, 'data/hs-links', p['file']), 'rb').read()
            self.assertEqual(p['sha256'], hashlib.sha256(data).hexdigest())
            files, shas, flags = p['raw_file'].split(' ; '), p['raw_sha256'].split(' ; '), p['raw_committed'].split(' ; ')
            self.assertEqual(len(files), len(shas))
            for f, h, c in zip(files, shas, flags):
                self.assertRegex(h, r'^[0-9a-f]{64}$')
                if c == 'yes':
                    self.assertEqual(h, hashlib.sha256(open(os.path.join(REPO, f), 'rb').read()).hexdigest())

    def test_json_matches_csv(self):
        j = json.load(open(os.path.join(REPO, 'data/measures/measures.json'), encoding='utf-8'))
        self.assertEqual(M, j)

    def test_files_are_what_the_builder_writes(self):
        out = measures.build(REPO)
        self.assertEqual(out['csv'], open(os.path.join(REPO, 'data/measures/measures.csv'), 'rb').read(), 'run: python -m pipeline.measures')
        self.assertEqual(out['json'], open(os.path.join(REPO, 'data/measures/measures.json'), 'rb').read())
        self.assertEqual(out['report'], open(os.path.join(REPO, 'data/measures/BUILD-REPORT.json'), 'rb').read())


class IsStandardsJoinTest(unittest.TestCase):
    STD = {r['is_no']: r for r in rows('data/is-standards/standards.csv')}

    def test_joined_rows_carry_the_table_values_and_nothing_else_changes(self):
        joined = [m for m in M if m['is_title']]
        self.assertEqual(REPORT['is_standards_join']['rows_with_title_and_status'], len(joined))
        self.assertGreater(len(joined), 200)
        for m in joined:
            self.assertIn(m['measure_type'], ('bis_isi_qco', 'bis_upcoming_qco'))
            refs = measures.is_refs(m['measure_value'])
            self.assertEqual(1, len(refs))
            s = self.STD['IS %s%s' % (refs[0][0], (' (Part %s)' % refs[0][1]) if refs[0][1] else '')]
            self.assertEqual((s['title'], s['status'], s['superseded_by']), (m['is_title'], m['is_status'], m['is_superseded_by']))
        self.assertTrue(all(not m['is_title'] and not m['is_status'] for m in M if m['measure_type'] in ('import_policy', 'policy_condition')))

    def test_join_unit(self):
        std = [{'is_no': 'IS 55', 'is_base': '55', 'part': '', 'title': 'Five', 'status': 'withdrawn', 'superseded_by': 'IS 55:2020'},
               {'is_no': 'IS 77 (Part 1)', 'is_base': '77', 'part': '1', 'title': 'Seven', 'status': 'current', 'superseded_by': ''}]
        out = [dict(measure_type='bis_isi_qco', measure_value='IS 55', status='in_force'),
               dict(measure_type='bis_isi_qco', measure_value='IS 77', status='in_force'),
               dict(measure_type='bis_isi_qco', measure_value='IS 77 (Part 1)', status='in_force'),
               dict(measure_type='bis_isi_qco', measure_value='IS 99', status='in_force'),
               dict(measure_type='import_policy', measure_value='Free', status='in_force')]
        joined, ambiguous, missing, warn = measures.join_standards(out, std)
        self.assertEqual((2, 1, 1), (joined, ambiguous, missing))
        self.assertEqual('withdrawn', out[0]['is_status'])
        self.assertEqual('in_force', out[0]['status'])  # the measure's own status is never changed from this signal
        self.assertEqual('', out[1]['is_title'])  # a multi-part standard is not guessed onto one part
        self.assertEqual(['IS 55'], [w['is_no'] for w in warn])


if __name__ == '__main__':
    unittest.main()
