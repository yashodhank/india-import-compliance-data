"""pipeline/adapter_kys.py: reference list, matching, status, resume, stop on 403/429. Every HTTP call is a stub; nothing touches the network."""
import csv
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from schemacheck import REPO, load_schema, validate  # noqa: E402

sys.path.insert(0, REPO)
from pipeline import adapter_kys as K  # noqa: E402

DETAILS = ('<html><input name="csrf_test_name" value="%s">Basic Details'
           '<label class="qs">IS Title/ <label class="rly">Widgets - Specification</label></div>'
           '<label class="qs">Number of Amendments/ <label class="rly">1</label></div>'
           '<label class="qs">Reaffirmation Year/ <label class="rly">2021</label></div>'
           '<label class="qs">Technical Committee/ <label class="rly">XYZ 1</label></div>Summary</html>')
CSRF = 'a' * 32


def hits(num, part='', year='2020', pk='100'):
    return {'id': pk, 'vc_doc_num': num, 'is_part': part, 'is_sec': '', 'is_prefix': 'IS', 'is_year': year, 'name': 'IS %s Widgets' % num,
            'is_no': 'IS %s' % num}


class Portal:
    """A stub portal. `db` maps base -> {part -> [hit dicts]}; `listing` maps pk -> (withdrawn flag, is_no text, title)."""

    def __init__(self, db, listing=None, block_after=None):
        self.db, self.listing, self.calls, self.block_after = db, listing or {}, [], block_after

    def __call__(self, method, url, data, headers):
        self.calls.append((method, url, dict(data or {})))
        if self.block_after is not None and len(self.calls) > self.block_after:
            return 429, b'slow down', ''
        if url.endswith('/robots.txt'):
            return 404, b'', ''
        if url.endswith('/indian_standards/isdetails'):
            return 200, ('<input name="csrf_test_name" value="%s">' % CSRF).encode(), ''
        assert data.get('csrf_test_name') == CSRF, url
        if 'getsearchAjax' in url:
            m = re.match(r'IS (\d+)(?: Part (\d+))?$', data['search'])
            return 200, json.dumps([h for hs in self.db.get(m.group(1), {}).values() for h in hs]).encode(), ''
        if url.endswith('/Indian_standards/isdetails/'):
            return 200, (DETAILS % CSRF).encode(), ''
        if 'getamendments' in url:
            return 200, json.dumps({'aaData': [{'AmendmentNumber': 'First Amendment', 'AmendmentYear': '2022', 'AmdFileName': 'x'}]}).encode(), ''
        if 'searchIS' in url:
            rows = [{'Action': '<a onclick="choosenIS(%s)">View</a>' % pk, 'withdrawn_status': w, 'is_no': n, 'is_title': t}
                    for pk, (w, n, t) in self.listing.items()]
            return 200, json.dumps({'iTotalDisplayRecords': len(rows), 'aaData': rows}).encode(), ''
        raise AssertionError(url)


def client(portal):
    return K.Client(transport=portal, delay=0, sleep=lambda s: None)


class RefsTest(unittest.TestCase):
    def test_refs_in_text(self):
        f = K.refs_in_text
        self.assertEqual([('302', '1')], f('IS 302 (Part 1) : 2024 IEC 60335-1:2020'))
        self.assertEqual([('13252', '1')], f('IS 13252(Part 1):2010, Essential Requirement(s) for Security of CCTV'))
        self.assertEqual([('60947', '2')], f('IS/IEC 60947: Part 2:2016'))
        self.assertEqual([('1391', '1'), ('1391', '2')], f('IS 1391 (Part-1): 2017 ; IS 1391 (Part-2): 2018'))
        self.assertEqual([('302', '2')], f('IS 302-2-26:2014'))
        self.assertEqual([('8510', '3')], f('IS 8510 (PartIII)'))
        self.assertEqual([('9438', '')], f('IS: 9438'))
        self.assertEqual([], f('Indian Standards and 2017'))

    def test_parse_ref_and_canon(self):
        self.assertEqual(('302', '1'), K.parse_ref('IS 302 (Part 1'))
        self.assertEqual('IS 302 (Part 1)', K.canon('302', '1'))
        self.assertEqual(('302', '1'), K.split_is_no('IS 302 (Part 1)'))
        self.assertIsNone(K.parse_ref('hello'))

    def test_repo_list_is_built_from_the_bis_lists_and_the_register(self):
        refs = K.repo_refs()
        self.assertGreater(len(refs), 1000)
        self.assertIn(('12330', ''), refs)
        self.assertIn(('1489', '1'), refs)
        self.assertEqual(sorted(refs, key=lambda x: (int(x[0]), int(x[1] or 0))), refs)


class MatchTest(unittest.TestCase):
    def test_pick_is_exact_on_number_and_part_and_takes_the_latest_year(self):
        c = [hits('302', '1', '2014', '1'), hits('302', '1', '2024', '2'), hits('302', '2', '2024', '3'), hits('3020', '', '2024', '4')]
        self.assertEqual('2', K.pick(c, '302', '1')[0]['id'])
        self.assertIsNone(K.pick(c, '302', '')[0])

    def test_status_from_list_row(self):
        self.assertEqual(('current', ''), K.status_from_list_row({'w': '', 'is_no': 'IS 5:2020', 'title': 'T'}))
        self.assertEqual(('withdrawn', ''), K.status_from_list_row({'w': 'W', 'is_no': 'IS 5:2000', 'title': 'T'}))
        self.assertEqual(('withdrawn', ''), K.status_from_list_row({'w': '', 'is_no': 'IS 5:2000 (Withdrawn)', 'title': 'T'}))
        self.assertEqual(('superseded', 'IS 5:2020'), K.status_from_list_row({'w': '', 'is_no': 'IS 5:2000 (Superceded by IS 5:2020)', 'title': 'T'}))

    def test_parse_details(self):
        d = K.parse_details(DETAILS % CSRF)
        self.assertEqual('Widgets - Specification', d['IS Title'])
        self.assertEqual('2021', d['Reaffirmation Year'])


class RunTest(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root)

    def rows(self, name):
        return list(csv.DictReader(open(os.path.join(self.root, 'data/is-standards', name), encoding='utf-8', newline='')))

    def test_fetch_writes_valid_tables_archives_html_and_sorts_status(self):
        db = {'100': {'': [hits('100', '', '2020', '501')]}, '200': {'': [hits('200', '', '2018', '502')]}, '300': {'1': [hits('300', '1', '2019', '503')]}}
        listing = {'501': ('', 'IS 100:2020', 'Widgets'), '502': ('W', 'IS 200:2018 (Withdrawn)', 'Widgets')}
        portal = Portal(db, listing)
        s = K.run(self.root, today='2026-10-25', refs=[('100', ''), ('200', ''), ('300', '1'), ('999', '')], transport=portal)
        self.assertEqual((4, 3, 1), (s['fetched'], s['matched'], s['unmatched']))
        st = {r['is_no']: r for r in self.rows('standards.csv')}
        self.assertEqual('current', st['IS 100']['status'])
        self.assertEqual('withdrawn', st['IS 200']['status'])
        self.assertEqual('unknown', st['IS 300 (Part 1)']['status'])  # pk 503 absent from the result list
        self.assertEqual('2021', st['IS 100']['reaffirmed_year'])
        self.assertEqual('First Amendment', json.loads(st['IS 100']['amendments'])[0]['number'])
        self.assertEqual('IS 999', self.rows('unmatched.csv')[0]['is_no'])
        raw = os.path.join(self.root, 'raw/is-standards/2026-10-25/501.html')
        self.assertEqual(st['IS 100']['sha256_detail'], hashlib.sha256(open(raw, 'rb').read()).hexdigest())
        for name, schema in (('standards.csv', 'is-standards'), ('unmatched.csv', 'is-standards-unmatched'), ('PROVENANCE.csv', 'provenance')):
            self.assertEqual([], validate(os.path.join(self.root, 'data/is-standards', name), load_schema(schema)), name)
        self.assertFalse([c for c in portal.calls if 'qco_file_details' in c[1]])
        self.assertEqual('GET', portal.calls[0][0])
        self.assertTrue(portal.calls[0][1].endswith('/robots.txt'))

    def test_resume_fetches_only_what_is_missing(self):
        db = {'100': {'': [hits('100', '', '2020', '501')]}, '200': {'': [hits('200', '', '2018', '502')]}}
        K.run(self.root, today='2026-10-25', refs=[('100', '')], transport=Portal(db))
        again = Portal(db)
        s = K.run(self.root, today='2026-10-26', refs=[('100', ''), ('200', '')], transport=again)
        self.assertEqual(1, s['fetched'])
        self.assertFalse([c for c in again.calls if c[2].get('search') == 'IS 100'])
        self.assertEqual(2, len(self.rows('standards.csv')))
        nothing = Portal(db)
        self.assertEqual(0, K.run(self.root, today='2026-10-27', refs=[('100', ''), ('200', '')], transport=nothing)['fetched'])
        self.assertEqual([], nothing.calls)

    def test_a_429_stops_the_run_and_keeps_what_was_fetched(self):
        db = {str(n): {'': [hits(str(n), '', '2020', str(600 + n))]} for n in (10, 20, 30)}
        portal = Portal(db)
        portal.block_after = 11
        with self.assertRaises(K.Blocked):
            K.run(self.root, today='2026-10-25', refs=[('10', ''), ('20', ''), ('30', '')], transport=portal, save_every=1)
        done = len(self.rows('standards.csv'))
        self.assertTrue(0 < done < 3)
        resumed = K.run(self.root, today='2026-10-26', refs=[('10', ''), ('20', ''), ('30', '')], transport=Portal(db))
        self.assertEqual(3 - done, resumed['fetched'])
        self.assertEqual(3, len(self.rows('standards.csv')))

    def test_403_stops_and_a_robots_disallow_stops(self):
        with self.assertRaises(K.Blocked):
            K.run(self.root, today='2026-10-25', refs=[('1', '')], transport=lambda *a: (403, b'', ''))
        with self.assertRaises(K.Blocked):
            K.run(self.root, today='2026-10-25', refs=[('1', '')], transport=lambda m, u, d, h: (200, b'User-agent: *\nDisallow: /', ''))

    def test_two_seconds_between_requests_and_an_honest_user_agent(self):
        slept, t = [], [100.0]
        seen = []

        def tr(m, u, d, h):
            seen.append(h['User-Agent'])
            return 404 if u.endswith('robots.txt') else 200, b'', ''
        cl = K.Client(transport=tr, sleep=lambda s: (slept.append(s), t.__setitem__(0, t[0] + s)), clock=lambda: t[0])
        cl.req('GET', K.HOST + '/robots.txt')
        cl.req('GET', K.HOST + '/robots.txt')
        self.assertEqual(1, len(slept))
        self.assertAlmostEqual(2.0, slept[0])
        self.assertIn('india-import-compliance-data', seen[0])

    def test_html_over_2_mb_is_hash_only(self):
        rel, note = K.archive_html(self.root, '2026-10-25', '1', b'x' * K.RAW_MAX)
        self.assertEqual('', rel)
        self.assertIn('hash only', note)
        self.assertFalse(os.path.exists(os.path.join(self.root, 'raw/is-standards')))

    def test_stale_records_are_refetched_after_the_new_ones(self):
        m = {'IS 1000': {'fetched_at': '2026-01-01T00:00:00Z'}, 'IS 2000': {'fetched_at': '2026-10-20T00:00:00Z'}}
        got = K.plan([('1000', ''), ('2000', ''), ('3000', '')], m, {}, '2026-10-25', 120)
        self.assertEqual([('3000', ''), ('1000', '')], got)


class PublishedTablesTest(unittest.TestCase):
    D = os.path.join(REPO, 'data/is-standards')

    def rows(self, name):
        return list(csv.DictReader(open(os.path.join(self.D, name), encoding='utf-8', newline='')))

    def test_every_is_no_the_repo_names_is_matched_unmatched_or_pending(self):
        have = {r['is_no'] for r in self.rows('standards.csv')} | {r['is_no'] for r in self.rows('unmatched.csv')}
        self.assertFalse({r['is_no'] for r in self.rows('standards.csv')} & {r['is_no'] for r in self.rows('unmatched.csv')})
        want = {K.canon(*r) for r in K.repo_refs()}
        self.assertFalse(have - want, 'rows for numbers this repository does not name')
        self.assertLess(len(want - have), 60, 'pending references')

    def test_provenance_counts_and_archived_pages_match_their_hashes(self):
        std = self.rows('standards.csv')
        prov = {p['file']: p for p in self.rows('PROVENANCE.csv')}
        self.assertEqual(len(std), int(prov['standards.csv']['rows']))
        self.assertEqual(len(self.rows('unmatched.csv')), int(prov['unmatched.csv']['rows']))
        for f in prov:
            self.assertEqual(prov[f]['sha256'], hashlib.sha256(open(os.path.join(self.D, f), 'rb').read()).hexdigest(), f)
        for r in std:
            self.assertIn(r['status'], K.STATUSES)
            day = r['fetched_at'][:10]
            p = os.path.join(REPO, K.RAW_DIR, day, r['pk_is_id'] + '.html')
            if os.path.exists(p):
                self.assertEqual(r['sha256_detail'], hashlib.sha256(open(p, 'rb').read()).hexdigest(), r['is_no'])
        self.assertEqual(len({r['is_no'] for r in std}), len(std))


if __name__ == '__main__':
    unittest.main()
