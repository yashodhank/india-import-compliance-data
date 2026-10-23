"""The refresh is all-or-nothing and idempotent."""
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from testkit import REPO, needs_pdf  # noqa: E402

from pipeline import refresh as rf  # noqa: E402


def clone():
    d = tempfile.mkdtemp(prefix='icd-')
    for sub in ('raw', 'data'):
        # the IS-standards page archive (pipeline.adapter_kys, monthly, 120 MB) is not part of the offline rebuild
        shutil.copytree(os.path.join(REPO, sub), os.path.join(d, sub), ignore=shutil.ignore_patterns('is-standards') if sub == 'raw' else None)
    return d


def tree(root):
    out = {}
    for sub in ('data', 'raw'):
        for dp, _, fs in os.walk(os.path.join(root, sub)):
            for f in fs:
                p = os.path.join(dp, f)
                out[os.path.relpath(p, root)] = open(p, 'rb').read()
    return out


class RefreshTest(unittest.TestCase):
    def setUp(self):
        self.root = clone()
        self.addCleanup(shutil.rmtree, self.root, True)

    @needs_pdf
    def test_an_offline_rebuild_of_the_committed_tree_changes_nothing(self):
        before = tree(self.root)
        s = rf.run(self.root, '2026-10-22', offline=True)
        self.assertEqual(0, s['files_written'])
        self.assertEqual(before, tree(self.root))

    @needs_pdf
    def test_a_rebuild_from_nothing_reproduces_the_published_tree(self):
        want = tree(self.root)
        shutil.rmtree(os.path.join(self.root, 'data'))
        os.makedirs(os.path.join(self.root, 'data', 'qco'))
        shutil.copy(os.path.join(REPO, 'data', 'qco', 'gazette-pdf-hashes.csv'), os.path.join(self.root, 'data', 'qco'))
        shutil.copytree(os.path.join(REPO, 'data', 'hs6'), os.path.join(self.root, 'data', 'hs6'))  # a static input, not rebuilt from raw/
        shutil.copytree(os.path.join(REPO, 'data', 'hs-links'), os.path.join(self.root, 'data', 'hs-links'))  # static inputs imported once by pipeline.hs_links
        shutil.copytree(os.path.join(REPO, 'data', 'is-standards'), os.path.join(self.root, 'data', 'is-standards'))  # fetched monthly by pipeline.adapter_kys
        rf.run(self.root, '2026-10-22', offline=True)
        got = tree(self.root)
        self.assertEqual(sorted(want), sorted(got))
        for k in want:
            self.assertEqual(want[k], got[k], k)

    @needs_pdf
    def test_a_layout_change_stops_the_run_and_writes_nothing(self):
        raw = os.path.join(self.root, 'raw', 'bis-scheme4', '2026-10-21')
        p = os.path.join(raw, os.listdir(raw)[0])
        open(p, 'wb').write(b'<html><body>Under maintenance</body></html>')
        before = tree(self.root)
        with self.assertRaises(rf.Failure):
            rf.run(self.root, '2026-10-22', offline=True)
        self.assertEqual(before, tree(self.root))

    @needs_pdf
    def test_a_chapter_whose_hash_differs_from_provenance_stops_the_run(self):
        raw = os.path.join(self.root, 'raw', 'dgft-itchs-2022', '2026-10-22', 'ch01.json')
        open(raw, 'ab').write(b' ')
        with self.assertRaisesRegex(rf.Failure, 'no archived copy matches'):
            rf.run(self.root, '2026-10-22', offline=True)

    @needs_pdf
    def test_a_missing_chapter_stops_the_run(self):
        os.unlink(os.path.join(self.root, 'raw', 'dgft-itchs-2022', '2026-10-22', 'ch50.json'))
        with self.assertRaisesRegex(rf.Failure, 'no archived copy matches'):
            rf.run(self.root, '2026-10-22', offline=True)

    def test_main_exits_nonzero_on_failure(self):
        rc = rf.main(['--root', os.path.join(self.root, 'nowhere'), '--offline'])
        self.assertEqual(1, rc)


class OnlineChangeTest(unittest.TestCase):
    """Online mode with an injected fetcher: an unchanged page leaves the files byte-identical; a shrunken list is refused."""

    def setUp(self):
        self.root = clone()
        self.addCleanup(shutil.rmtree, self.root, True)

    def test_unchanged_list_is_left_alone_and_a_shrunk_one_is_refused(self):
        from pipeline import sources as S
        spec = S.LISTS[4]  # Scheme-X
        summary = {'lists': {}}
        ctx = rf.Ctx(self.root, '2026-10-29', False, None, False)
        raw = open(os.path.join(REPO, 'raw', 'bis-schemex', '2026-10-21', 'www.bis.gov.in_scheme-x_2026-10-21.html'), 'rb').read()
        ctx.fetch = lambda url: raw
        before = open(os.path.join(self.root, spec['out']), 'rb').read()
        rf.run_list(ctx, spec, summary, {})
        self.assertEqual({}, ctx.stage.files)  # unchanged: nothing staged, so nothing written, no new raw copy
        self.assertFalse(summary['lists'][spec['out']]['added'])
        # the same page, 29 days later, is re-stamped and archived
        ctx2 = rf.Ctx(self.root, '2026-11-20', False, lambda url: raw, False)
        rf.run_list(ctx2, spec, {'lists': {}}, {})
        self.assertIn(spec['out'], ctx2.stage.files)
        self.assertTrue(any(k.startswith('raw/bis-schemex/2026-11-20/') for k in ctx2.stage.files))
        self.assertEqual(before.count(b'\n'), ctx2.stage.files[spec['out']].count(b'\n'))
        # a current list twice the size makes the fresh parse look like a collapse
        cur = open(os.path.join(self.root, spec['out']), 'rb').read().decode()
        lines = cur.splitlines()
        open(os.path.join(self.root, spec['out']), 'w').write('\n'.join(lines + lines[1:] + lines[1:]) + '\n')
        with self.assertRaisesRegex(rf.Failure, 'more than 50% below'):
            rf.run_list(rf.Ctx(self.root, '2026-10-29', False, lambda url: raw, False), spec, {'lists': {}}, {})


if __name__ == '__main__':
    unittest.main()


class StaleSourceTest(unittest.TestCase):
    def test_an_unfetchable_source_keeps_its_last_good_file_and_is_reported_stale(self):
        root = clone()
        self.addCleanup(shutil.rmtree, root, True)
        spec = next(x for x in rf.S.LISTS if x['out'] == 'data/bis/isi_qco.csv')
        before = tree(root)

        def fetch(url):
            raise rf.Failure('HTTP 403 from %s' % url)
        ctx = rf.Ctx(root, '2026-10-29', False, fetch, False)
        summary = {'lists': {}}
        prov = {}
        rows = rf.run_list(ctx, spec, summary, prov)
        self.assertEqual(len(rf.read_rows(root, spec['out'])), len(rows))
        self.assertEqual('data/bis/isi_qco.csv', summary['stale'][0]['file'])
        self.assertIn('HTTP 403', summary['stale'][0]['reason'])
        self.assertFalse(rf.rd.changed(summary['lists'][spec['out']]))
        self.assertEqual({}, ctx.stage.files)
        self.assertEqual(before, tree(root))
        entry = rf.changelog_entry(dict(summary, date='2026-10-29'))
        self.assertIn('STALE since', entry)
        self.assertNotIn('Re-verified; no list changed', entry)

    def test_a_source_stale_for_more_than_thirty_days_escalates_and_a_fresh_one_does_not(self):
        e = rf.stale_entry('f.csv', 's', '2026-10-01', 'HTTP 403', '2026-10-31')
        self.assertEqual((30, False), (e['age_days'], e['escalate']))
        e = rf.stale_entry('f.csv', 's', '2026-10-01', 'HTTP 403', '2026-11-01')
        self.assertEqual((31, True), (e['age_days'], e['escalate']))
        e = rf.stale_entry('f.csv', 's', '', 'unknown age', '2026-11-01')
        self.assertEqual((None, True), (e['age_days'], e['escalate']))
        self.assertIn('ESCALATED', rf.changelog_entry({'date': '2026-11-01', 'stale': [rf.stale_entry('f.csv', 's', '2026-09-01', 'x', '2026-11-01')]}))

    def test_the_stale_entries_of_a_real_run_carry_every_key_the_report_schema_requires(self):
        import json
        sch = json.load(open(os.path.join(os.path.dirname(os.path.abspath(rf.__file__)), 'refresh-report.schema.json'), encoding='utf-8'))
        need = set(sch['properties']['stale']['items']['required'])
        root = clone()
        self.addCleanup(shutil.rmtree, root, True)
        spec = next(x for x in rf.S.LISTS if x['out'] == 'data/bis/isi_qco.csv')

        def fetch(url):
            raise rf.Failure('HTTP 403 from %s' % url)
        summary = {'lists': {}}
        rf.run_list(rf.Ctx(root, '2026-10-29', False, fetch, False), spec, summary, {})
        self.assertEqual(need, set(summary['stale'][0]))
        self.assertTrue(set(sch['required']) <= {'status', 'date'})

    def test_a_source_with_no_last_good_file_is_a_failure_and_contradictory_data_still_fails(self):
        root = tempfile.mkdtemp(prefix='icd-')
        self.addCleanup(shutil.rmtree, root, True)
        spec = next(x for x in rf.S.LISTS if x['out'] == 'data/bis/isi_qco.csv')

        def fetch(url):
            raise rf.Failure('HTTP 403')
        with self.assertRaises(rf.Failure):
            rf.run_list(rf.Ctx(root, '2026-10-29', False, fetch, False), spec, {'lists': {}}, {})
        fetched = lambda url: b'<html><body><table><tr><th>Sr No.</th></tr></table></body></html>'  # noqa: E731 (a page that parses to nothing known)
        root2 = clone()
        self.addCleanup(shutil.rmtree, root2, True)
        with self.assertRaises(rf.Failure):
            rf.run_list(rf.Ctx(root2, '2026-10-29', False, fetched, False), spec, {'lists': {}}, {})


class NoStructureTest(unittest.TestCase):
    """A 200 body without the expected tables is a fetch problem: paid fallback first, then stale, never a parse failure."""
    SHELL = b'<html><body>Please enable JavaScript</body></html>'

    def setUp(self):
        self.root = clone()
        self.addCleanup(shutil.rmtree, self.root, True)
        self.spec = next(x for x in rf.S.LISTS if x['out'] == 'data/bis/scheme_x.csv')
        self.good = open(os.path.join(self.root, 'raw', 'bis-schemex', '2026-10-21', 'www.bis.gov.in_scheme-x_2026-10-21.html'), 'rb').read()

    def fetcher(self, direct, paid):
        calls = []

        def f(url):
            return direct
        f.rescrape = lambda url, why: calls.append(why) or (paid if isinstance(paid, bytes) else (_ for _ in ()).throw(rf.Failure(paid)))
        f.info = {}
        return f, calls

    def test_the_paid_fallback_gets_the_page_when_the_direct_body_has_no_tables(self):
        f, calls = self.fetcher(self.SHELL, self.good)
        ctx = rf.Ctx(self.root, '2026-10-29', False, f, False)
        summary = {'lists': {}}
        rf.run_list(ctx, self.spec, summary, {})
        self.assertEqual(1, len(calls))
        self.assertNotIn('stale', summary)

    def test_when_the_paid_fallback_also_has_no_tables_the_source_is_stale(self):
        for paid in (self.SHELL, 'fallback HTTP 500'):
            f, calls = self.fetcher(self.SHELL, paid)
            ctx = rf.Ctx(self.root, '2026-10-29', False, f, False)
            summary = {'lists': {}}
            rows = rf.run_list(ctx, self.spec, summary, {})
            self.assertTrue(rows)
            self.assertIn('page answered 200 without the expected tables', summary['stale'][0]['reason'])
            self.assertEqual({}, ctx.stage.files)

    def test_a_fetcher_without_a_fallback_goes_stale_and_the_body_is_kept_for_the_artifact(self):
        d = tempfile.mkdtemp(prefix='dbg-')
        self.addCleanup(shutil.rmtree, d, True)
        os.environ['REFRESH_DEBUG_DIR'] = d
        self.addCleanup(os.environ.pop, 'REFRESH_DEBUG_DIR', None)
        ctx = rf.Ctx(self.root, '2026-10-29', False, lambda url: self.SHELL, False)
        summary = {'lists': {}}
        rf.run_list(ctx, self.spec, summary, {})
        self.assertIn('stale', summary)
        self.assertEqual([self.SHELL], [open(os.path.join(d, n), 'rb').read() for n in os.listdir(d)])

    def test_tables_with_the_wrong_columns_still_fail_the_run(self):
        bad = self.good.replace(b'Indian Standards', b'Something else')
        self.assertNotEqual(bad, self.good)
        f, calls = self.fetcher(bad, self.good)
        with self.assertRaises(rf.Failure):
            rf.run_list(rf.Ctx(self.root, '2026-10-29', False, f, False), self.spec, {'lists': {}}, {})
        self.assertEqual([], calls)


class UpcomingReconcileTest(unittest.TestCase):
    def row(self, name, code, notes='List serial 1'):
        return {'product_name': name, 'is_codes': code, 'notes': notes}

    def test_leaving_the_list_is_explained_or_kept_never_dropped_silently(self):
        root = tempfile.mkdtemp(prefix='icd-')
        self.addCleanup(shutil.rmtree, root, True)
        ctx = rf.Ctx(root, '2026-10-22', False, None, False)
        ctx.stage.put('data/bis/isi_qco.csv', b'product_name,is_codes\nWrought Aluminium Utensils,IS 1660:2024\n')
        current = [self.row('Wrought Aluminium Utensils', 'IS 1660:2024'), self.row('Pliers', '3650:1981', 'serial 28'), self.row('Pliers', '3650:1981', 'serial 31'),
                   self.row('Vanished', 'IS 9999')]
        new = [self.row('Pliers', '3650:1981', 'serial 26')]
        summary = {}
        out = rf.reconcile_upcoming(ctx, current, new, summary)
        self.assertEqual(['Pliers', 'Vanished'], [r['product_name'] for r in out])
        self.assertTrue(out[1]['notes'].endswith('| source_removed 2026-10-22'))
        notes = summary['explained']['data/bis/qco_upcoming.csv']
        self.assertTrue(any('now in force' in n and '1660' in n for n in notes))
        self.assertTrue(any('source_removed' in n and 'Vanished' in n for n in notes))
        self.assertTrue(any('de-duplicated' in n and 'Pliers' in n for n in notes))
        self.assertEqual(out, rf.reconcile_upcoming(ctx, out, new, {}), 'stable on the next run')


class OlderEditionTest(unittest.TestCase):
    def test_a_pdf_older_than_the_archived_copy_keeps_the_source_stale_instead_of_being_parsed(self):
        """2026-10-22: the TEC host served the runner its 2022 edition (175 serials, another column geometry) of a list the archive holds from 2023."""
        root = clone()
        self.addCleanup(shutil.rmtree, root, True)
        spec = next(x for x in rf.S.LISTS if x['out'] == 'data/tec/mtcte.csv')
        have = open(rf.newest_raw(root, spec['id'])[1], 'rb').read()
        stamp = rf.pdf_created(have)
        self.assertTrue(stamp)
        older = have.replace(b'D:' + stamp.encode(), b'D:20220714134537')
        self.assertNotEqual(have, older)
        summary = {'lists': {}}
        ctx = rf.Ctx(root, '2026-10-29', False, lambda url: older, False)
        rows = rf.run_list(ctx, spec, summary, {})
        self.assertTrue(rows)
        self.assertIn('older edition', summary['stale'][0]['reason'])
        self.assertEqual({}, ctx.stage.files)
        self.assertEqual('', rf.older_edition(root, spec['id'], have))


class DgftStaleTest(unittest.TestCase):
    def test_an_unreachable_dgft_keeps_the_archived_itchs_data_and_reports_it_stale(self):
        root = clone()
        self.addCleanup(shutil.rmtree, root, True)
        orig = (rf.itchs.DgftSession, rf.run_list, rf.run_bee)

        class Blocked(orig[0]):
            def listing(self):
                raise rf.itchs.Unreachable('HTTP 403 from https://www.dgft.gov.in/CP/?opt=itchs-import-export')
        rf.itchs.DgftSession, rf.run_list, rf.run_bee = Blocked, (lambda ctx, spec, summary, prov: None), (lambda ctx, summary, prov: None)
        self.addCleanup(lambda: (setattr(rf.itchs, 'DgftSession', orig[0]), setattr(rf, 'run_list', orig[1]), setattr(rf, 'run_bee', orig[2])))
        summary = rf.run(root, '2026-10-29', dry_run=True, fetch=lambda url: b'')
        self.assertEqual('data/itchs/2022', summary['stale'][0]['file'])
        self.assertIn('HTTP 403', summary['stale'][0]['reason'])
        self.assertEqual(97, summary['itchs']['chapters'])
        self.assertEqual(0, summary['itchs']['rows_8digit'] - summary['itchs']['rows_8digit'])

    def test_main_prints_the_traceback_and_the_url_of_an_unexpected_error(self):
        import urllib.error
        import io
        import contextlib
        rep = os.path.join(tempfile.mkdtemp(prefix='rep-'), 'r.json')
        orig = rf.run

        def boom(*a, **k):
            raise urllib.error.HTTPError('https://x.example/p', 403, 'Forbidden', {}, None)
        rf.run = boom
        self.addCleanup(setattr, rf, 'run', orig)
        err = io.StringIO()
        with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
            code = rf.main(['--report', rep])
        self.assertEqual(1, code)
        import json
        reason = json.load(open(rep))['reason']
        self.assertIn('https://x.example/p', reason)
        self.assertIn('Traceback', reason)
        self.assertIn('Traceback', err.getvalue())
