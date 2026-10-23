"""The release step folds the Unreleased section into the new tagged entry and bumps CITATION.cff (.github/scripts/release_prep.py)."""
import importlib.util
import os
import tempfile
import unittest

REPO = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
spec = importlib.util.spec_from_file_location('release_prep', os.path.join(REPO, '.github/scripts/release_prep.py'))
RP = importlib.util.module_from_spec(spec)
spec.loader.exec_module(RP)

CHANGELOG = """# Changelog

Intro.

## Unreleased

Changes on `main` after `v2026.10.22`; they ship in the next release.

- Fix: one.
- Docs: two.

## v2026.10.22, 2026-10-22

- old entry
"""
ENTRY = "## 2026-10-30\n\n- `data/x.csv`: 1 -> 2 rows.\n"
CFF = 'cff-version: 1.2.0\nversion: "v2026.10.22"\ndate-released: "2026-10-22"\nlicense: MIT\n'


class ReleasePrep(unittest.TestCase):
    def test_fold(self):
        out = RP.fold(CHANGELOG, 'v2026.10.30', '2026-10-30', ENTRY)
        self.assertEqual(1, out.count('## Unreleased'))
        self.assertLess(out.index('## Unreleased'), out.index('## v2026.10.30, 2026-10-30'))
        self.assertLess(out.index('## v2026.10.30, 2026-10-30'), out.index('## v2026.10.22, 2026-10-22'))
        new = out.split('## v2026.10.30, 2026-10-30')[1].split('## v2026.10.22')[0]
        self.assertIn('- `data/x.csv`: 1 -> 2 rows.', new)
        self.assertIn('- Fix: one.\n- Docs: two.', new)
        self.assertNotIn('ship in the next release', new)
        unreleased = out.split('## Unreleased')[1].split('## v2026.10.30')[0]
        self.assertNotIn('Fix: one', unreleased)
        self.assertIn('after `v2026.10.30`', unreleased)

    def test_without_unreleased(self):
        out = RP.fold("# Changelog\n\nIntro.\n\n## v1, 2026-01-01\n\n- a\n", 'v2', '2026-02-02', ENTRY)
        self.assertTrue(out.index('## Unreleased') < out.index('## v2, 2026-02-02') < out.index('## v1, 2026-01-01'))

    def test_cite_and_main(self):
        with tempfile.TemporaryDirectory() as d:
            for name, text in (('CHANGELOG.md', CHANGELOG), ('CITATION.cff', CFF), ('entry.md', ENTRY)):
                RP.wr(os.path.join(d, name), text)
            RP.main(['v2026.10.30', '2026-10-30', os.path.join(d, 'entry.md'), '--root', d])
            cff = RP.rd(os.path.join(d, 'CITATION.cff'))
        self.assertIn('version: "v2026.10.30"', cff)
        self.assertIn('date-released: "2026-10-30"', cff)
        self.assertIn('license: MIT', cff)


if __name__ == '__main__':
    unittest.main()
