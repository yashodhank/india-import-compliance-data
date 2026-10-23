"""Writes docs/data-dictionary.md from schemas/*.json and schemas/index.json.

    python docs/build_data_dictionary.py           # rewrite the file
    python docs/build_data_dictionary.py --check   # exit 1 when the file is stale
"""
import json
import os
import sys

REPO = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
OUT = os.path.join(REPO, 'docs', 'data-dictionary.md')


def _cell(s):
    return str(s).replace('|', '\\|').replace('\n', ' ')


def render():
    index = json.load(open(os.path.join(REPO, 'schemas', 'index.json'), encoding='utf-8'))['files']
    users = {}
    for path, name in index.items():
        users.setdefault(name, []).append(path)
    lines = ['# Data dictionary', '',
             'Generated from `schemas/*.json` by `python docs/build_data_dictionary.py`; do not edit by hand. A test fails when this file is stale.',
             'Every CSV is UTF-8, LF line endings, comma separated, with a header row. Each schema is a Frictionless Table Schema.', '']
    for name in sorted(users):
        sp = os.path.join(REPO, 'schemas', name + '.json')
        if not os.path.exists(sp):
            continue
        sch = json.load(open(sp, encoding='utf-8'))
        paths = sorted(users[name])
        shown = ', '.join('`%s`' % p for p in paths[:3]) + (' and %d more of the same shape' % (len(paths) - 3) if len(paths) > 3 else '')
        lines += ['## %s' % name, '', sch.get('title', ''), '', 'Files: %s' % shown, '',
                  '| Field | Type | Required | Constraints | Meaning |', '|---|---|---|---|---|']
        for f in sch['fields']:
            c = dict(f.get('constraints', {}))
            req = 'yes' if c.pop('required', False) else 'no'
            con = '; '.join('%s: %s' % (k, ', '.join(map(str, v)) if isinstance(v, list) else v) for k, v in sorted(c.items()))
            lines.append('| `%s` | %s | %s | %s | %s |' % (f['name'], f.get('type', 'string'), req, _cell(con), _cell(f.get('description', ''))))
        if sch.get('primaryKey'):
            lines += ['', 'Primary key: `%s`' % '`, `'.join(sch['primaryKey'] if isinstance(sch['primaryKey'], list) else [sch['primaryKey']])]
        lines.append('')
    return '\n'.join(lines).rstrip() + '\n'


if __name__ == '__main__':
    text = render()
    if '--check' in sys.argv:
        cur = open(OUT, encoding='utf-8').read() if os.path.exists(OUT) else ''
        sys.exit(0 if cur == text else 1)
    with open(OUT, 'w', encoding='utf-8', newline='\n') as fh:
        fh.write(text)
    print('wrote', OUT)
