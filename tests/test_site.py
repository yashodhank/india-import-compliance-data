"""pipeline/site.py builds the static API and the chapter pages."""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from schemacheck import REPO  # noqa: E402

sys.path.insert(0, REPO)
from pipeline import site  # noqa: E402


def j(root, rel):
    return json.load(open(os.path.join(root, rel), encoding='utf-8'))


class SiteTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.out = cls.tmp.name
        cls.counts = site.build(REPO, cls.out, release='v2026.10.23')
        cls.idx_out = tempfile.TemporaryDirectory()
        site.build(REPO, cls.idx_out.name, release='v2026.10.24')

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()
        cls.idx_out.cleanup()

    def test_latest_json(self):
        d = j(self.out, 'api/latest.json')
        self.assertEqual('v2026.10.23', d['release'])
        self.assertEqual(12571, d['counts']['hs8_codes'])
        self.assertEqual(12587, d['counts']['hs8_lines'])
        self.assertEqual(d['counts']['measures'], sum(d['counts']['measures_by_type'].values()))
        self.assertRegex(d['as_of'], r'^\d{4}-\d{2}-\d{2}$')
        self.assertIn('Not legal advice', d['notice'])

    def test_one_json_per_code_with_its_measures(self):
        files = os.listdir(os.path.join(self.out, 'api/codes'))
        self.assertEqual(12571, len(files))
        d = j(self.out, 'api/codes/72104100.json')
        self.assertEqual('72104100', d['hs8'])
        self.assertEqual('721041', d['hs6'])
        self.assertTrue(d['hs6_description'])
        self.assertIn('import_policy', [m['measure_type'] for m in d['measures']])
        self.assertTrue(any(m['measure_value'] == 'IS 277' for m in d['measures']))

    def test_per_code_json_stays_small(self):
        biggest = max(os.path.getsize(os.path.join(self.out, 'api/codes', f)) for f in os.listdir(os.path.join(self.out, 'api/codes')))
        self.assertLess(biggest, 120_000)

    def test_chapters(self):
        self.assertEqual(97, len(os.listdir(os.path.join(self.out, 'api/chapters'))))
        d = j(self.out, 'api/chapters/85.json')
        self.assertEqual('85', d['chapter'])
        self.assertTrue(any(c['hs8'] == '85171300' for c in d['codes']))
        html = open(os.path.join(self.out, 'chapters/85.html'), encoding='utf-8').read()
        self.assertIn('85171300', html)
        self.assertNotRegex(html, r'<script|<link[^>]+stylesheet')

    def test_noindex_until_the_release_is_cut(self):
        for rel in ('index.html', 'chapters/85.html'):
            self.assertIn('noindex', open(os.path.join(self.out, rel), encoding='utf-8').read(), rel)
            self.assertNotIn('noindex', open(os.path.join(self.idx_out.name, rel), encoding='utf-8').read(), rel)
        self.assertIn('Disallow: /', open(os.path.join(self.out, 'robots.txt')).read())
        self.assertNotIn('Disallow: /', open(os.path.join(self.idx_out.name, 'robots.txt')).read())

    def test_openapi_describes_every_static_endpoint(self):
        y = open(os.path.join(self.out, 'openapi.yaml'), encoding='utf-8').read()
        for p in ('/api/latest.json', '/api/codes/{hs8}.json', '/api/chapters/{chapter}.json'):
            self.assertIn('  %s:' % p, y)
        self.assertTrue(y.startswith('openapi: 3'))

    def test_html_escapes_text(self):
        html = open(os.path.join(self.out, 'chapters/08.html'), encoding='utf-8').read()
        self.assertNotRegex(html, r'<(?!/?(?:html|head|meta|title|body|h1|h2|p|a|table|thead|tbody|tr|th|td|ul|li|nav|code|small|em|style|br|link)\b)[a-zA-Z]')
        self.assertIn('Not legal advice', html)


if __name__ == '__main__':
    unittest.main()
