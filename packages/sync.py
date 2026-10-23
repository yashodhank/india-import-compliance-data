"""Copies the two bundled tables into both packages.

    python packages/sync.py           copy (run after the data changes)
    python packages/sync.py --check   change nothing; exit 1 and name the command when a bundled copy differs
"""
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.normpath(os.path.join(HERE, '..'))
FILES = {'data/itchs/2022/all.csv': 'all.csv', 'data/measures/measures.csv': 'measures.csv'}
TARGETS = ['packages/python/india_import_compliance/data', 'packages/node/data']


def pairs():
    for src, name in FILES.items():
        for t in TARGETS:
            yield os.path.join(REPO, src), os.path.join(REPO, t, name)


def stale():
    out = []
    for s, d in pairs():
        if not os.path.exists(d) or open(s, 'rb').read() != open(d, 'rb').read():
            out.append(os.path.relpath(d, REPO))
    return out


if __name__ == '__main__':
    if '--check' in sys.argv[1:]:
        bad = stale()
        if bad:
            print('bundled package data is out of sync with data/: %s' % ', '.join(bad), file=sys.stderr)
            print('fix: python packages/sync.py && git add packages', file=sys.stderr)
            sys.exit(1)
        print('bundled package data is in sync')
    else:
        for s, d in pairs():
            shutil.copyfile(s, d)
        print('synced')
