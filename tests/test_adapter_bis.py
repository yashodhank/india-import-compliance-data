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
from testkit import ARCHIVES, REPO, TODAY, GoldenCheck, parse, raw  # noqa: E402


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

    def fixture(self):
        with open(os.path.join(REPO, 'tests', 'fixtures', 'scheme1_copies_2026-10-22.html'), encoding='utf-8') as fh:
            return fh.read()

    def test_scheme_i_copy_with_rows_the_others_lack_is_the_source_of_truth(self):
        """Live 2026-10-22: BIS had added IS 1664, IS 5470 and IS 920 to one of the page's three table copies only (799/802/799 rows)."""
        got = AB.parse_scheme1(self.fixture().encode('utf-8'), 'u', TODAY)
        self.assertEqual(['IS 12330', 'IS 12600', 'IS 1489 (Part 1)', 'IS 1664', 'IS 5470', 'IS 920'], [r['is_codes'] for r in got.rows])
        self.assertEqual(3, got.notes['rows_only_in_the_longest_table_copy'])
        self.assertEqual(['Animal Feeds and Feed Ingredients'] * 3, [r['group'] for r in got.rows[3:]])  # the page gives them no section title: the order's own name

    def test_scheme_i_only_the_compregs_rows_differ_in_section_between_first_and_longest_copy(self):
        """The longest copy gives the compregs rows no section title of their own (they fall under the flask section above); the first copy does.
        Rows keep the first copy's section, so those three are the only rows where the two copies disagree."""
        with open(os.path.join(REPO, 'raw', 'bis-scheme1', '2026-10-22', 'www.bis.gov.in_scheme-1_2026-10-22.html'), 'rb') as fh:  # the live page with three different copies
            ts = AB.grid_tables(fh.read(), [['sr no', 'is no', 'product']], 'scheme_1')
        base = AB.table_copies(ts)[0]
        self.assertNotEqual(0, base)
        spacer = lambda r: AB.blank(r) or (len(r) >= 3 and not r[1][0] and not r[2][0])  # noqa: E731
        def by_code(t):
            secs = AB.first_copy_sections(t, spacer)
            return {r[1][0]: secs[id(r)] for r in t[1:] if id(r) in secs}
        first, longest = by_code(ts[0]), by_code(ts[base])
        flips = sorted(c for c in first if c in longest and first[c] != longest[c])
        self.assertEqual(['IS 3513 (Part 1) : 1989', 'IS 3513 (Part 2) : 1989', 'IS 3513 (Part 3) : 1989'], flips)

    def test_scheme_i_cookware_row_keeps_every_order_of_a_long_history_including_the_one_only_one_copy_lists(self):
        """Live 2026-10-22: 'Cookware ... (Quality Control) Second Order, 2026, S.O. 5624(E), 13 Oct 2026' was only in the second table copy, and the
        notes were cut at 600 characters, so neither the order nor the end of the history reached isi_qco.csv."""
        with open(os.path.join(REPO, 'raw', 'bis-scheme1', '2026-10-22', 'www.bis.gov.in_scheme-1_2026-10-22.html'), 'rb') as fh:
            got = AB.parse_scheme1(fh.read(), 'u', TODAY)
        cook = [r for r in got.rows if r['is_codes'] == 'IS 14756 : 2022']
        self.assertEqual(1, len(cook))
        qco = cook[0]['notes'].split(' | QCO PDF:')[0]
        self.assertGreater(len(qco), 700)  # the old cut was at 606
        flat = re.sub(r'S\.\s?O\.\s*', 'S.O.', qco)
        for so in ('3583', '1365', '4494', '3850', '219', '1661', '5624'):
            self.assertIn('S.O.' + so + '(E)', re.sub(r'(\d)\s+\(E\)', r'\1(E)', flat))
        self.assertIn('Second Order, 2026', qco)
        self.assertTrue(qco.rstrip().endswith('13 October, 2026'))
        self.assertTrue(all(r['notes'].count('S.O.5624') == 1 for r in got.rows if r['group'].startswith('Cookware')))

    def test_newer_orders_appends_only_the_orders_a_cell_lacks(self):
        cell = 'A Order, 2024 S.O. 100(E), dated 1st May 2024 B Order, 2025 S.O.200(E) Dated 2 June, 2025'
        later = cell + ' C Second Order, 2026 S.O.5624(E) Dated 13 October, 2026'
        self.assertEqual([], AB.newer_orders(cell, [cell, cell[:60]]))
        self.assertEqual(['C Second Order, 2026 S.O.5624(E) Dated 13 October, 2026'], AB.newer_orders(cell, [later, later]))
        self.assertEqual([], AB.newer_orders(later, [cell]))  # an older copy never removes or reorders anything

    def test_scheme_i_copies_that_contradict_each_other_still_fail(self):
        h = self.fixture()
        out = h.replace('IS 12600', 'IS 12601', 1)  # the first copy now holds a code the longest copy does not
        self.assertNotEqual(h, out)
        with self.assertRaisesRegex(A.Failure, 'different IS numbers'):
            AB.parse_scheme1(out.encode('utf-8'), 'u', TODAY)

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
