"""Golden tests for the BIS HTML-table adapters (adapter_bis.py): Scheme-I, Scheme-II, Scheme-IV, Scheme-X and the upcoming QCOs.

GOLDEN_REGEN=1 python3 -m pytest tests rewrites golden/ from the archived copies (review the diff).
"""
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
import pipeline.adapter_bis as AB  # noqa: E402
import pipeline.adapters as A  # noqa: E402
from testkit import ARCHIVES, REPO, TODAY, GoldenCheck, parse, raw, read_csv_rows  # noqa: E402


class BisGoldenTest(GoldenCheck, unittest.TestCase):
    def test_scheme_i(self):
        self.check('isi_qco.csv')

    def test_scheme_ii_non_meity_tables(self):
        self.check('scheme_ii_other.csv')

    def test_scheme_iv(self):
        self.check('scheme_iv.csv')

    def test_scheme_x(self):
        self.check('scheme_x.csv')

    def test_upcoming_qcos(self):
        self.check('qco_upcoming.csv')



class BisLayoutChangeTest(unittest.TestCase):
    """A page that no longer looks like the one the parser was proved against fails; it is never half-read."""

    def page(self, name, edit):
        html = raw(name).decode('utf-8', 'replace')
        out = edit(html)
        self.assertNotEqual(html, out, 'the edit changed nothing')
        return out.encode('utf-8')

    def test_a_row_the_parser_would_skip_is_a_failure_not_a_silent_drop(self):
        body = self.page(ARCHIVES['isi_qco.csv'], lambda h: h.replace('</table>', '<tr><td>9999.</td><td></td><td>Ghost product</td></tr></table>', 1))
        with self.assertRaisesRegex(A.Failure, 'parsed 710 rows but the source table has 711'):
            AB.parse_scheme1(body, 'u', TODAY)

    def test_a_changed_header_is_a_failure(self):
        body = self.page(ARCHIVES['isi_qco.csv'], lambda h: re.sub(r'(<table.*?)IS No\.', r'\1Standard', h, count=1, flags=re.S))
        with self.assertRaisesRegex(A.Failure, 'header'):
            AB.parse_scheme1(body, 'u', TODAY)

    def test_an_unknown_upcoming_row_shape_is_a_failure(self):
        body = self.page(ARCHIVES['qco_upcoming.csv'], lambda h: h.replace('</table>', '<tr><td>1</td><td>2</td></tr></table>', 1))
        with self.assertRaisesRegex(A.Failure, 'shape'):
            AB.parse_upcoming(body, 'u', TODAY)

    def test_a_missing_table_is_a_failure(self):
        with self.assertRaisesRegex(A.Failure, 'tables on the page'):
            AB.parse_scheme_x(b'<html><body><p>Under maintenance</p></body></html>', 'u', TODAY)

    def test_a_new_scheme_ii_table_needs_a_decision(self):
        body = self.page(ARCHIVES['scheme_ii_other.csv'], lambda h: h.replace('</table>', '</table><table><tr><th>Sl. No.</th><th>IS No.</th></tr></table>', 1) if h.count('</table>') == 4 else h + '<table><tr><th>Sl. No.</th><th>IS No.</th></tr></table>')
        with self.assertRaisesRegex(A.Failure, '4 expected'):
            AB.parse_scheme2_other(body, 'u', TODAY)

    def test_the_page_date_is_read_from_the_page(self):
        self.assertEqual('2026-10-15', A.page_date(raw(ARCHIVES['isi_qco.csv'])))
        self.assertEqual('', A.page_date(b'<html>no date</html>'))


if __name__ == '__main__':
    unittest.main()
