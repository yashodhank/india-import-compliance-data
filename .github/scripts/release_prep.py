#!/usr/bin/env python3
"""Release bookkeeping, run by refresh.yml and refresh-is-standards.yml before the data commit.

    python .github/scripts/release_prep.py TAG DATE ENTRY_FILE [--root DIR]

1. CHANGELOG.md: the entry in ENTRY_FILE (first line is its heading, replaced by "## TAG, DATE") goes in as the newest release, and the
   body of the "## Unreleased" section is folded into it (its intro sentence is dropped, its lines follow the entry's own lines). An
   empty "## Unreleased" heading is left above it.
2. CITATION.cff: `version` and `date-released` are set to TAG and DATE. (datapackage.json takes its version from CITATION.cff:
   the caller runs `python -m pipeline.datapackage` afterwards.)
"""
import argparse
import os
import re
import sys

INTRO = re.compile(r'^Changes on `main` after .*ship in the next release\.\s*$')


def fold(changelog, tag, date, entry):
    body = entry.split('\n', 1)[1] if '\n' in entry else ''
    body = body.strip('\n')
    head, sep, rest = changelog.partition('\n## ')
    unreleased = ''
    if sep and rest.startswith('Unreleased'):
        section, sep2, after = rest.partition('\n## ')
        lines = section.split('\n')[1:]
        lines = [l for l in lines if not INTRO.match(l)]
        unreleased = '\n'.join(lines).strip('\n')
        rest = ('## ' + after) if sep2 else ''
    else:
        rest = ('## ' + rest) if sep else ''
    parts = [body, unreleased]
    new = '## %s, %s\n\n%s\n' % (tag, date, '\n'.join(p for p in parts if p))
    empty = '## Unreleased\n\nChanges on `main` after `%s`; they ship in the next release.\n' % tag
    return head.rstrip('\n') + '\n\n' + empty + '\n' + new + ('\n' + rest if rest else '')


def cite(text, tag, date):
    for key, val in (('version', tag), ('date-released', date)):
        text, n = re.subn(r'^%s:.*$' % key, '%s: "%s"' % (key, val), text, count=1, flags=re.M)
        if n != 1:
            raise SystemExit('CITATION.cff has no %s line' % key)
    return text


def rd(path):
    with open(path, encoding='utf-8') as fh:
        return fh.read()


def wr(path, text):
    with open(path, 'w', encoding='utf-8', newline='\n') as fh:
        fh.write(text)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('tag')
    ap.add_argument('date')
    ap.add_argument('entry')
    ap.add_argument('--root', default='.')
    a = ap.parse_args(argv)
    p = os.path.join(a.root, 'CHANGELOG.md')
    c = os.path.join(a.root, 'CITATION.cff')
    entry = rd(a.entry)
    wr(p, fold(rd(p), a.tag, a.date, entry))
    wr(c, cite(rd(c), a.tag, a.date))
    print('release prepared: %s %s' % (a.tag, a.date))


if __name__ == '__main__':
    sys.exit(main())
