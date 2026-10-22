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
