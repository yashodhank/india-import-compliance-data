"""Copies the two bundled tables into both packages. Run after the data changes: python packages/sync.py"""
import os
import shutil

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.normpath(os.path.join(HERE, '..'))
FILES = {'data/itchs/2022/all.csv': 'all.csv', 'data/measures/measures.csv': 'measures.csv'}
TARGETS = ['packages/python/india_import_compliance/data', 'packages/node/data']

if __name__ == '__main__':
    for src, name in FILES.items():
        for t in TARGETS:
            shutil.copyfile(os.path.join(REPO, src), os.path.join(REPO, t, name))
    print('synced')
