import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import { lookup, measures, search } from '../src/index.js';

const require = createRequire(import.meta.url);
const here = path.dirname(fileURLToPath(import.meta.url));
const repo = path.join(here, '..', '..', '..');

test('lookup 8 digits with punctuation', () => {
  const r = lookup('8517.13.00');
  assert.equal(r.hs_code, '85171300');
  assert.equal(r.policy, 'Free');
  assert.equal(r.hs6, '851713');
});

test('lookup unknown and malformed', () => {
  assert.equal(lookup('99999999'), null);
  assert.equal(lookup('85'), null);
  assert.equal(lookup('abc'), null);
  assert.equal(lookup('0101').level, '4');
});

test('measures for steel include IS 277', () => {
  const ms = measures('72104100');
  assert.ok(ms.some((m) => m.measure_type === 'import_policy'));
  assert.ok(ms.some((m) => m.measure_value === 'IS 277'));
  assert.ok(measures('721041').length > 0);
  assert.deepEqual(measures('1'), []);
});

test('search', () => {
  assert.ok(search('smartphones').some((h) => h.hs_code === '85171300'));
  assert.deepEqual(search('zzzzqqqq'), []);
  assert.ok(search('steel', 3).length <= 3);
});

test('CommonJS entry gives the same API', () => {
  const cjs = require('../src/index.cjs');
  assert.equal(cjs.lookup('85171300').hs_code, '85171300');
  assert.equal(typeof cjs.search, 'function');
});

test('results are copies', () => {
  lookup('85171300').policy = 'x';
  assert.equal(lookup('85171300').policy, 'Free');
});

test('quoted fields parse: commas inside a description', () => {
  assert.equal(lookup('01022990').description, 'Other, including calves');
  assert.ok(lookup('28444400').description.startsWith('"Radioactive elements'));
});

test('bundled data is the repository data', () => {
  for (const [src, name] of [['data/itchs/2022/all.csv', 'all.csv'], ['data/measures/measures.csv', 'measures.csv']]) {
    assert.ok(fs.readFileSync(path.join(repo, src)).equals(fs.readFileSync(path.join(here, '..', 'data', name))), 'run: python packages/sync.py');
  }
});
