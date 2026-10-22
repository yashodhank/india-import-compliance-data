#!/usr/bin/env python3
"""Copy the release assets into one flat directory with unique names: python -m pipeline.assets dist"""
import os
import shutil
import sys

ASSETS = {
    'itchs-2022-all.csv': 'data/itchs/2022/all.csv',
    'itchs-2022-chapter-conditions.csv': 'data/itchs/2022/chapter-conditions.csv',
    'qco-register.csv': 'data/qco/register.csv',
    'qco-register.json': 'data/qco/register.json',
    'measures.csv': 'data/measures/measures.csv',
    'measures.json': 'data/measures/measures.json',
    'hs-scheme-candidates.csv': 'data/derived/hs-scheme-candidates.csv',
    'bis-isi_qco.csv': 'data/bis/isi_qco.csv',
    'bis-crs.csv': 'data/bis/crs.csv',
    'bis-scheme_ii_other.csv': 'data/bis/scheme_ii_other.csv',
    'bis-scheme_iv.csv': 'data/bis/scheme_iv.csv',
    'bis-scheme_x.csv': 'data/bis/scheme_x.csv',
    'bis-qco_upcoming.csv': 'data/bis/qco_upcoming.csv',
    'bis-option2.csv': 'data/bis/option2.csv',
    'tec-mtcte.csv': 'data/tec/mtcte.csv',
    'bee-mandatory.csv': 'data/bee/mandatory.csv',
    'bee-voluntary.csv': 'data/bee/voluntary.csv',
}


def main(out):
    root = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
    os.makedirs(out, exist_ok=True)
    for name, rel in ASSETS.items():
        shutil.copyfile(os.path.join(root, rel), os.path.join(out, name))
    print(len(ASSETS), 'assets in', out)


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else 'dist')
