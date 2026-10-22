"""A small Table Schema checker (header, types, required, enum, pattern, primaryKey) so every published CSV is validated with the standard library."""
import csv
import datetime
import io
import json
import os
import re

REPO = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))


def load_schema(name):
    with open(os.path.join(REPO, 'schemas', name + '.json'), encoding='utf-8') as fh:
        return json.load(fh)


def check_value(field, v):
    t = field['type']
    if t == 'integer':
        int(v)
    elif t == 'number':
        float(v)
    elif t == 'boolean':
        if v not in ('true', 'false'):
            raise ValueError('not a boolean: %r' % v)
    elif t == 'date':
        datetime.date.fromisoformat(v)


def validate(path, schema, limit=20):
    """-> list of error strings (empty when the file conforms)."""
    errs = []
    with open(path, 'rb') as fh:
        raw = fh.read()
    if b'\r' in raw:
        errs.append('CR in file (expected LF line endings)')
    rd = csv.reader(io.StringIO(raw.decode('utf-8'), newline=''))
    head = next(rd)
    names = [f['name'] for f in schema['fields']]
    if head != names:
        return ['header %r differs from schema %r' % (head, names)]
    fields = schema['fields']
    seen, pk = set(), schema.get('primaryKey')
    for n, row in enumerate(rd, start=2):
        if len(row) != len(fields):
            errs.append('line %d: %d cells, expected %d' % (n, len(row), len(fields)))
            continue
        for f, v in zip(fields, row):
            c = f.get('constraints', {})
            if v == '':
                if c.get('required'):
                    errs.append('line %d: %s is required' % (n, f['name']))
                continue
            try:
                check_value(f, v)
            except ValueError as e:
                errs.append('line %d: %s: %s' % (n, f['name'], e))
            if 'enum' in c and (int(v) if f['type'] == 'integer' else v) not in c['enum']:
                errs.append('line %d: %s=%r not in enum' % (n, f['name'], v))
            if 'pattern' in c and not re.search(c['pattern'], v):
                errs.append('line %d: %s=%r does not match %s' % (n, f['name'], v[:40], c['pattern']))
        if pk:
            key = tuple(row[names.index(k)] for k in pk)
            if key in seen:
                errs.append('line %d: duplicate primary key %r' % (n, key))
            seen.add(key)
        if len(errs) >= limit:
            errs.append('(stopping after %d errors)' % limit)
            break
    return errs
