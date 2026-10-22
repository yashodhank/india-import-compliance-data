"""Golden tests for the BEE star-label adapter (adapter_bee.py): mandatory and voluntary appliance pages.

GOLDEN_REGEN=1 python3 -m pytest tests rewrites golden/ from the archived copies (review the diff).
"""
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
import pipeline.adapter_bee as AE  # noqa: E402
import pipeline.adapters as A  # noqa: E402
from testkit import BEE_M, BEE_V, REPO, TODAY, GoldenCheck, parse, raw  # noqa: E402


class BeeGoldenTest(GoldenCheck, unittest.TestCase):
    def test_bee(self):
        self.check('bee.csv')


class BeeLayoutChangeTest(unittest.TestCase):
    def page(self, name, edit):
        html = raw(name).decode('utf-8', 'replace')
        out = edit(html)
        self.assertNotEqual(html, out, 'the edit changed nothing')
        return out.encode('utf-8')

    def test_a_bee_row_with_no_serial_is_a_failure(self):
        body = self.page(BEE_V, lambda h: re.sub(r'(<td[^>]*>)\s*23\s*(</td>)', r'\1x\2', h, count=1))
        with self.assertRaisesRegex(A.Failure, 'shape'):
            AE.parse_bee(raw(BEE_M), body, 'm', 'v', TODAY)


if __name__ == '__main__':
    unittest.main()
