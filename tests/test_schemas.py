"""Every published CSV conforms to its table schema, and every CSV under data/ is covered by schemas/index.json."""
import glob
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from schemacheck import REPO, load_schema, validate  # noqa: E402

INDEX = json.load(open(os.path.join(REPO, 'schemas', 'index.json'), encoding='utf-8'))['files']


class SchemaTest(unittest.TestCase):
    def test_every_csv_under_data_has_a_schema(self):
        found = sorted(os.path.relpath(p, REPO) for p in glob.glob(os.path.join(REPO, 'data', '**', '*.csv'), recursive=True))
        self.assertEqual(sorted(INDEX), found)

    def test_every_schema_file_is_used_and_well_formed(self):
        used = set(INDEX.values())
        for p in glob.glob(os.path.join(REPO, 'schemas', '*.json')):
            name = os.path.basename(p)[:-5]
            if name == 'index':
                continue
            self.assertIn(name, used, name)
            s = json.load(open(p, encoding='utf-8'))
            self.assertEqual(len({f['name'] for f in s['fields']}), len(s['fields']), 'duplicate field names in ' + name)

    def test_each_published_csv_conforms(self):
        for rel, name in sorted(INDEX.items()):
            with self.subTest(file=rel):
                errs = validate(os.path.join(REPO, rel), load_schema(name))
                self.assertEqual([], errs)


if __name__ == '__main__':
    unittest.main()


class ValidatorControlTest(unittest.TestCase):
    """Positive control: the checker does report a bad file."""

    def check(self, text, schema='list'):
        import tempfile
        with tempfile.NamedTemporaryFile('w', suffix='.csv', delete=False, newline='') as fh:
            fh.write(text)
        try:
            return validate(fh.name, load_schema(schema))
        finally:
            os.unlink(fh.name)

    def test_bad_header_status_date_and_missing_required_are_reported(self):
        head = 'product_name,is_codes,scheme,authority,group,source_url,retrieved_on,status,notes\n'
        self.assertTrue(self.check('x\n1\n'))
        errs = self.check(head + ',,S,A,,ftp://u,2026-13-40,bogus,\n')
        joined = ' '.join(errs)
        for want in ('product_name is required', 'retrieved_on', 'status', 'source_url'):
            self.assertIn(want, joined)
        self.assertEqual([], self.check(head + 'P,IS 1,S,A,,https://u,2026-10-22,active,\n'))
