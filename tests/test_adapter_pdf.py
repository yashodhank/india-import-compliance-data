"""Golden tests for the PDF adapters (adapter_pdf.py): the BIS Option-2 list and the TEC MTCTE list. They need pdftohtml (poppler-utils).

GOLDEN_REGEN=1 python3 -m pytest tests rewrites golden/ from the archived copies (review the diff).
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
import pipeline.adapter_pdf as AP  # noqa: E402
import pipeline.adapters as A  # noqa: E402
from testkit import TODAY, GoldenCheck, needs_pdf  # noqa: E402


class PdfGoldenTest(GoldenCheck, unittest.TestCase):
    @needs_pdf
    def test_simplified_option_2_pdf(self):
        self.check('simplified_2024.csv')

    @needs_pdf
    def test_mtcte_pdf(self):
        self.check('mtcte.csv')



class PdfLayoutChangeTest(unittest.TestCase):
    @needs_pdf
    def test_a_pdf_that_is_not_a_pdf_is_a_failure(self):
        with self.assertRaises(A.Failure):
            AP.parse_mtcte(b'%PDF-1.4 not really', 'u', TODAY)


class PdfSerialColumnTest(unittest.TestCase):
    """Reviewer finding 2: a serial the column cut would miss is counted by a wider rule, so the two counts disagree and the parse fails."""

    def simplified_items(self, serial_left):
        it = [(1, 100, 65, 52, 'Sr. No.'), (1, 100, 139, 82, 'IS Number'), (1, 100, 490, 98, 'Product/Title')]
        for n, top in ((1, 150), (2, 200), (3, 250)):
            it += [(1, top, serial_left if n == 2 else 85, 12, str(n)), (1, top, 148, 64, 'IS %d' % n), (1, top, 400, 200, 'Product %d' % n)]
        return it

    def test_the_cut_serials_parse(self):
        from unittest import mock
        with mock.patch.object(AP, 'pdf_items', return_value=self.simplified_items(85)):
            p = AP.parse_simplified(b'x', 'u', TODAY)
        self.assertEqual((3, 3), (len(p.rows), p.source_rows))

    def test_a_serial_outside_the_left_column_fails(self):
        from unittest import mock
        with mock.patch.object(AP, 'pdf_items', return_value=self.simplified_items(200)):
            with self.assertRaisesRegex(A.Failure, 'serial'):
                AP.parse_simplified(b'x', 'u', TODAY)

    def test_mtcte_serials_must_be_continuous(self):
        from unittest import mock
        it = [(1, 120, 84, 28, 'S.N.'), (1, 120, 141, 145, 'Essential Requirement/'), (1, 120, 346, 144, 'Product Variant Name'),
              (1, 120, 523, 95, 'MTCTE Phase'), (1, 120, 661, 118, 'Mandatory date of')]
        for n, top in ((1, 180), (2, 220), (4, 260)):
            it += [(1, top, 93, 7, str(n)), (1, top, 127, 100, 'ER %d' % n), (1, top, 354, 100, 'Variant %d' % n), (1, top, 546, 48, 'Phase-1'), (1, top, 667, 100, '1st May, 2020')]
        with mock.patch.object(AP, 'pdf_items', return_value=it):
            with self.assertRaisesRegex(A.Failure, 'serial'):
                AP.parse_mtcte(b'x', 'u', TODAY)



if __name__ == '__main__':
    unittest.main()
