"""datapackage.json lists every CSV under data/, matches the schemas, is current, and every CSV validates against its entry."""
import glob
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from schemacheck import REPO, validate  # noqa: E402
from pipeline import datapackage  # noqa: E402

DP = json.load(open(os.path.join(REPO, 'datapackage.json'), encoding='utf-8'))


class DataPackageTest(unittest.TestCase):
    def test_every_csv_under_data_is_a_resource(self):
        found = sorted(os.path.relpath(p, REPO) for p in glob.glob(os.path.join(REPO, 'data', '**', '*.csv'), recursive=True))
        self.assertEqual(found, sorted(r['path'] for r in DP['resources']))

    def test_resource_names_are_unique_and_valid(self):
        names = [r['name'] for r in DP['resources']]
        self.assertEqual(len(names), len(set(names)))
        for n in names:
            self.assertRegex(n, r'^[a-z0-9._-]+$')

    def test_file_is_what_the_generator_writes(self):
        self.assertEqual(datapackage.dumps(datapackage.build()), open(os.path.join(REPO, 'datapackage.json'), encoding='utf-8').read(),
                         'run: python -m pipeline.datapackage')

    def test_each_resource_validates_against_its_own_embedded_schema(self):
        for r in DP['resources']:
            with self.subTest(path=r['path']):
                self.assertEqual([], validate(os.path.join(REPO, r['path']), r['schema']))


if __name__ == '__main__':
    unittest.main()
