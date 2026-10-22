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
        with self.assertRaisesRegex(A.Failure, 'shape'):
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


def table(rows, head=('Sr No.', 'IS No.', 'Product', 'For Notification Details')):
    return '<table><tr>' + ''.join('<th>%s</th>' % h for h in head) + '</tr>' + ''.join(rows) + '</table>'


class BisRowspanTest(unittest.TestCase):
    """Reviewer findings 1, 14, 15 and the duplicate-key claim: every <tr> is accounted for, and a rowspan row keeps what the rows above span over it."""

    def test_a_rowspan_remainder_is_not_dropped(self):
        html = table(['<tr><td colspan="4">Section One</td></tr>',
                      '<tr><td rowspan="2">1.</td><td rowspan="2">IS 1</td><td>Product A</td><td rowspan="2">QCO One</td></tr>',
                      '<tr><td>Product B</td></tr>'])
        p = AB.parse_scheme1(html.encode(), 'u', TODAY)
        self.assertEqual(['Product A', 'Product B'], [r['product_name'] for r in p.rows])
        self.assertEqual(['IS 1', 'IS 1'], [r['is_codes'] for r in p.rows])
        self.assertEqual({'Section One'}, {r['group'] for r in p.rows})
        self.assertIn('QCO One', p.rows[1]['notes'])

    def test_the_appliance_series_the_old_scraper_took_for_section_titles_is_parsed(self):
        rows = {r['product_name']: r for r in parse('isi_qco.csv').rows}
        self.assertIn('Spin Extractors', rows)
        self.assertEqual('IS 302 (Part 1) : 2024 IEC 60335-1:2020', rows['Spin Extractors']['is_codes'])

    def test_a_short_row_that_is_neither_a_section_nor_spanned_is_a_failure(self):
        html = table(['<tr><td>1.</td><td>IS 1</td><td>Product A</td><td>QCO</td></tr>', '<tr><td>9.</td><td>Orphan product</td></tr>'])
        with self.assertRaisesRegex(A.Failure, 'shape'):
            AB.parse_scheme1(html.encode(), 'u', TODAY)

    def test_scheme_i_repeated_key_is_a_failure(self):
        html = table(['<tr><td>1.</td><td>IS 1</td><td>Product A</td><td>QCO</td></tr>', '<tr><td>2.</td><td>IS 1</td><td>Product A</td><td>QCO</td></tr>'])
        with self.assertRaisesRegex(A.Failure, 'share one IS code'):
            AB.parse_scheme1(html.encode(), 'u', TODAY)

    def test_the_product_name_has_no_stray_serial_digit_from_the_first_copy_of_the_table(self):
        names = [r['product_name'] for r in parse('isi_qco.csv').rows if r['is_codes'] == 'IS 5522:2014']
        self.assertEqual(1, len(names))
        self.assertFalse(names[0][0].isdigit(), names)

    def test_scheme_x_machinery_rows_equal_the_tr_count(self):
        base = raw(ARCHIVES['scheme_x.csv']).decode('utf-8', 'replace')
        i = base.rindex('</table>')
        extra = base[:i] + '<tr><td>21</td><td>Extra machinery</td><td>IS 1</td></tr>' + base[i:]
        p = AB.parse_scheme_x(extra.encode(), 'u', TODAY)
        self.assertEqual(21, p.notes['machinery'])
        bad = base[:i] + '<tr><td>Note</td><td>footnote</td></tr>' + base[i:]
        with self.assertRaisesRegex(A.Failure, 'shape'):
            AB.parse_scheme_x(bad.encode(), 'u', TODAY)



if __name__ == '__main__':
    unittest.main()
