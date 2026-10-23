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
from testkit import BEE_M, BEE_V, TODAY, GoldenCheck, parse, raw  # noqa: E402


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


class BeeBlankRowTest(unittest.TestCase):
    def test_a_blank_row_above_the_live_list_does_not_discontinue_it(self):
        html = raw(BEE_M).decode('utf-8', 'replace')
        i = html.index('<tr', html.index('<tr') + 3)  # the first row after the header
        edited = (html[:i] + '<tr><td></td><td></td><td></td><td></td><td></td></tr>' + html[i:]).encode()
        p = AE.parse_bee(edited, raw(BEE_V), 'm', 'v', TODAY)
        live = [r for r in p.rows if r['scheme'].endswith('(mandatory)') and r['status'] == 'active']
        self.assertEqual(18, len(live))
        self.assertEqual(['Tubular Fluorescent Lamps'], [r['product_name'] for r in p.rows if r['status'] == 'discontinued'])

    def test_the_same_appliance_on_both_lists_is_two_rows_with_two_schemes(self):
        rows = parse('bee.csv').rows
        hobs = [r for r in rows if r['product_name'] == 'Induction Hob']
        self.assertEqual(['BEE star-label (mandatory)', 'BEE star-label (voluntary)'], sorted(r['scheme'] for r in hobs)[::-1] if False else sorted(r['scheme'] for r in hobs))



if __name__ == '__main__':
    unittest.main()
