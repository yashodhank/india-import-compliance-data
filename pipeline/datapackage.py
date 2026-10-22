"""Builds datapackage.json (Frictionless Data Package) from schemas/index.json and the CSVs under data/.

Run `python -m pipeline.datapackage` to rewrite it; tests/test_datapackage.py fails when the file is stale or incomplete.
"""
import json
import os
import re
import sys

REPO = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
VERSION_FROM = os.path.join(REPO, 'CITATION.cff')


def _version():
    m = re.search(r'^version:\s*"?([^"\n]+)"?', open(VERSION_FROM, encoding='utf-8').read(), re.M)
    return m.group(1).strip() if m else ''


def _name(rel):
    parts = rel[len('data/'):-len('.csv')].split('/')
    return re.sub(r'[^a-z0-9._-]+', '-', '-'.join(parts).lower())


def build(repo=REPO):
    index = json.load(open(os.path.join(repo, 'schemas', 'index.json'), encoding='utf-8'))['files']
    resources = []
    for rel in sorted(index):
        schema = json.load(open(os.path.join(repo, 'schemas', index[rel] + '.json'), encoding='utf-8'))
        schema = {k: v for k, v in schema.items() if k in ('fields', 'primaryKey')}
        resources.append({
            'name': _name(rel), 'title': json.load(open(os.path.join(repo, 'schemas', index[rel] + '.json'), encoding='utf-8')).get('title', ''),
            'path': rel, 'format': 'csv', 'mediatype': 'text/csv', 'encoding': 'utf-8', 'schema': schema})
    return {
        'name': 'india-import-compliance-data',
        'title': 'India import compliance data',
        'description': 'What approval applies to a product at import into India: ITC(HS) 2022 import policy and conditions, BIS, TEC and BEE compulsory lists, a QCO register with Gazette hashes. Not a trade-statistics dataset.',
        'version': _version(),
        'homepage': 'https://github.com/yashodhank/india-import-compliance-data',
        'keywords': ['India', 'import policy', 'ITC(HS)', 'HS code', 'BIS', 'QCO', 'customs', 'open data'],
        'licenses': [
            {'name': 'CC-BY-4.0', 'path': 'https://creativecommons.org/licenses/by/4.0/', 'title': 'Creative Commons Attribution 4.0 (data)'}],
        'sources': [
            {'title': 'DGFT ITC(HS) 2022 Schedule 1', 'path': 'https://www.dgft.gov.in'},
            {'title': 'Bureau of Indian Standards', 'path': 'https://www.bis.gov.in'},
            {'title': 'Compulsory Registration Scheme portal', 'path': 'https://www.crsbis.in'},
            {'title': 'Telecommunication Engineering Centre MTCTE', 'path': 'https://mtcte.tec.gov.in'},
            {'title': 'Bureau of Energy Efficiency', 'path': 'https://www.beestarlabel.com'},
            {'title': 'datasets/harmonized-system (HS 2022 six-digit table, ODC-PDDL-1.0)', 'path': 'https://github.com/datasets/harmonized-system'}],
        'resources': resources}


def dumps(dp):
    return json.dumps(dp, indent=2, ensure_ascii=False) + '\n'


if __name__ == '__main__':
    open(os.path.join(REPO, 'datapackage.json'), 'w', encoding='utf-8', newline='\n').write(dumps(build()))
    print('wrote datapackage.json', file=sys.stderr)
