"""Golden tests for the PDF adapters (adapter_pdf.py): the BIS Option-2 list and the TEC MTCTE list. They need pdftohtml (poppler-utils).

GOLDEN_REGEN=1 python3 -m pytest tests rewrites golden/ from the archived copies (review the diff).
"""
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
import pipeline.adapter_pdf as AP  # noqa: E402
import pipeline.adapters as A  # noqa: E402
from testkit import REPO, TODAY, GoldenCheck, needs_pdf, parse, read_csv_rows  # noqa: E402


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


if __name__ == '__main__':
    unittest.main()
