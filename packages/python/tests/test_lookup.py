import filecmp
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))
import india_import_compliance as iic  # noqa: E402

REPO = os.path.normpath(os.path.join(HERE, '..', '..', '..'))
DATA = os.path.join(HERE, '..', 'india_import_compliance', 'data')


class LookupTest(unittest.TestCase):
    def test_lookup_8_digit_with_punctuation(self):
        r = iic.lookup('8517.13.00')
        self.assertEqual('85171300', r['hs_code'])
        self.assertEqual('Free', r['policy'])
        self.assertEqual('851713', r['hs6'])

    def test_lookup_unknown_and_malformed(self):
        self.assertIsNone(iic.lookup('99999999'))
        self.assertIsNone(iic.lookup('85'))
        self.assertIsNone(iic.lookup('abc'))

    def test_lookup_heading(self):
        self.assertEqual('4', iic.lookup('0101')['level'])

    def test_measures_steel(self):
        ms = iic.measures('72104100')
        self.assertIn('import_policy', [m['measure_type'] for m in ms])
        self.assertTrue(any(m['measure_value'] == 'IS 277' for m in ms))

    def test_measures_prefix_and_none(self):
        self.assertGreater(len(iic.measures('721041')), 0)
        self.assertEqual([], iic.measures('1'))

    def test_search(self):
        hits = iic.search('smartphones')
        self.assertIn('85171300', [h['hs_code'] for h in hits])
        self.assertEqual([], iic.search('zzzzqqqq'))
        self.assertLessEqual(len(iic.search('steel', limit=3)), 3)

    def test_results_are_copies(self):
        iic.lookup('85171300')['policy'] = 'x'
        self.assertEqual('Free', iic.lookup('85171300')['policy'])

    def test_bundled_data_is_the_repository_data(self):
        for src, name in (('data/itchs/2022/all.csv', 'all.csv'), ('data/measures/measures.csv', 'measures.csv')):
            self.assertTrue(filecmp.cmp(os.path.join(REPO, src), os.path.join(DATA, name), shallow=False), 'run: python packages/sync.py')


if __name__ == '__main__':
    unittest.main()
