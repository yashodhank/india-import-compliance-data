"""pipeline/check.py passes on the committed tree, and each of its assertions fails on data that breaks it (positive controls)."""
import datetime
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from pipeline import check as C  # noqa: E402

real_rows = C.rows


def mutated(rel, edit):
    """check.rows with `edit(list of dict rows)` applied to one file."""
    def rows(r):
        out = [dict(x) for x in real_rows(r)]
        if r == rel:
            edit(out)
        return out
    return rows


class CheckTest(unittest.TestCase):
    TODAY = datetime.date(2026, 10, 23)

    def problems(self, rel=None, edit=None, only=None):
        errs = []
        with mock.patch.object(C, 'rows', mutated(rel, edit) if rel else real_rows):
            for fn in only:
                fn(errs.append) if fn is not C.check_status_and_dates else fn(errs.append, self.TODAY)
        return errs

    def test_the_committed_data_passes(self):
        self.assertEqual([], C.run(self.TODAY))

    def test_an_unknown_status_word_fails(self):
        e = self.problems('data/bis/isi_qco.csv', lambda r: r[0].update(status='expired'), [C.check_status_and_dates])
        self.assertTrue(any('status' in x and 'expired' in x for x in e), e)

    def test_a_future_or_malformed_date_fails(self):
        e = self.problems('data/bis/isi_qco.csv', lambda r: r[0].update(retrieved_on='2027-01-01'), [C.check_status_and_dates])
        self.assertTrue(any('future' in x for x in e), e)
        e = self.problems('data/bis/isi_qco.csv', lambda r: r[0].update(retrieved_on='22/10/2026'), [C.check_status_and_dates])
        self.assertTrue(any('ISO' in x for x in e), e)

    def test_a_measure_whose_qco_slug_is_unknown_fails(self):
        e = self.problems('data/measures/measures.csv', lambda r: [x.update(qco_slug='no-such-order') for x in r if x['qco_slug']][:1], [C.check_measures])
        self.assertTrue(any('no-such-order' in x for x in e), e)

    def test_a_dangling_superseded_by_fails(self):
        e = self.problems('data/is-standards/standards.csv', lambda r: r[0].update(superseded_by='IS 99999 : 2030'), [C.check_measures])
        self.assertTrue(any('IS 99999' in x for x in e), e)

    def test_a_malformed_so_reference_fails(self):
        e = self.problems('data/hs-links/steel-qco-hs-columns.csv', lambda r: r[0].update(so_number='SO 756'), [C.check_measures])
        self.assertTrue(any('malformed' in x for x in e), e)

    def test_a_duplicate_row_fails(self):
        e = self.problems('data/bis/crs.csv', lambda r: r.append(dict(r[0])), [C.check_duplicates])
        self.assertTrue(any('crs.csv' in x and 'duplicate' in x for x in e), e)

    def test_the_known_corrections_are_enforced(self):
        def feeds(r):
            [x.update(group='Something else') for x in r if x['is_codes'] == 'IS 920']
        self.assertTrue(any('Animal Feeds' in x for x in self.problems('data/bis/isi_qco.csv', feeds, [C.check_known_corrections])))

        def foot(r):
            [x.update(status='withdrawn') for x in r if 'ootwear' in x['notes']][:1]
        self.assertTrue(any('Foot Wear' in x for x in self.problems('data/bis/isi_qco.csv', foot, [C.check_known_corrections])))
        self.assertTrue(any('IS 1660' in x for x in self.problems('data/bis/qco_upcoming.csv', lambda r: r[0].update(is_codes='IS 1660:2024'), [C.check_known_corrections])))

    def test_a_provenance_hash_that_does_not_match_fails(self):
        e = self.problems('data/bis/PROVENANCE.csv', lambda r: r[0].update(sha256='0' * 64), [C.check_provenance])
        self.assertTrue(any('sha256' in x for x in e), e)

    def test_a_missing_raw_file_fails(self):
        e = self.problems('data/bis/PROVENANCE.csv', lambda r: r[0].update(raw_file='raw/nowhere/x.html'), [C.check_provenance])
        self.assertTrue(any('does not exist' in x for x in e), e)


if __name__ == '__main__':
    unittest.main()
