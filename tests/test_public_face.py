"""The public face (README, CHANGELOG, CITATION, data dictionary, site extras) says what the repository holds today."""
import csv
import collections
import os
import re
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from schemacheck import REPO  # noqa: E402

sys.path.insert(0, REPO)
from pipeline import site  # noqa: E402


def rows(rel):
    return list(csv.DictReader(open(os.path.join(REPO, rel), encoding='utf-8', newline='')))


def read(rel):
    return open(os.path.join(REPO, rel), encoding='utf-8').read()


class PublicFaceTest(unittest.TestCase):
    def test_readme_counts(self):
        readme = read('README.md')
        isi = rows('data/bis/isi_qco.csv')
        st = collections.Counter(r['status'] for r in isi)
        self.assertIn('| %s (%d active, %d withdrawn, %d de-notified) |' % (format(len(isi), ','), st['active'], st['withdrawn'], st['de-notified']), readme)
        for rel, label in (('data/bis/qco_upcoming.csv', 'qco_upcoming.csv'), ('data/derived/hs-scheme-candidates.csv', 'hs-scheme-candidates.csv'),
                           ('data/measures/measures.csv', 'measures.csv')):
            self.assertRegex(readme, r'%s`[^|]*\| %s' % (re.escape(label), format(len(rows(rel)), ',').replace(',', ',?')), rel)
        self.assertIn('| %d records |' % len(rows('data/qco/register.csv')), readme)

    def test_citation_names_a_real_release_and_the_changelog_covers_every_tag(self):
        tags = subprocess.run(['git', 'tag', '-l', 'v*'], cwd=REPO, capture_output=True, text=True).stdout.split()
        heads = re.findall(r'^## (v\d[\d.]*), \d{4}-\d{2}-\d{2}$', read('CHANGELOG.md'), re.M)
        self.assertEqual(len(heads), len(set(heads)))
        if tags:  # a shallow checkout has no tags
            self.assertFalse(set(tags) - set(heads), 'tags without a changelog entry')
        self.assertIn(site.release_of(REPO), heads)

    def test_data_dictionary_is_current(self):
        r = subprocess.run([sys.executable, os.path.join(REPO, 'docs', 'build_data_dictionary.py'), '--check'])
        self.assertEqual(0, r.returncode, 'run python docs/build_data_dictionary.py')

    def test_site_extras(self):
        with tempfile.TemporaryDirectory() as out:
            site.build(REPO, out)
            import json
            idx = json.load(open(os.path.join(out, 'api/index.json'), encoding='utf-8'))
            self.assertEqual('1', idx['api_version'])
            for e in idx['endpoints']:
                if e['schema']:
                    self.assertTrue(os.path.exists(os.path.join(out, 'api/schemas', e['schema'].rsplit('/', 1)[1])), e)
            home = open(os.path.join(out, 'index.html'), encoding='utf-8').read()
            for needle in ('<title>', 'name="description"', 'rel="canonical"', 'feed.xml'):
                self.assertIn(needle, home)
            self.assertNotIn('noindex', home)
            feed = open(os.path.join(out, 'feed.xml'), encoding='utf-8').read()
            self.assertIn('<entry>', feed)
            self.assertNotIn('Unreleased', feed)
            self.assertIn('Sitemap:', open(os.path.join(out, 'robots.txt')).read())


if __name__ == '__main__':
    unittest.main()
