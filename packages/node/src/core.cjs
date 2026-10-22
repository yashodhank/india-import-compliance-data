'use strict';
// Shared implementation (CommonJS); src/index.js re-exports it for ESM. No dependencies.
const fs = require('fs');
const path = require('path');

const DATA = path.join(__dirname, '..', 'data');
const cache = {};

function parseCsv(text) {
  const rows = [];
  let row = [], field = '', q = false;
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (q) {
      if (c === '"') { if (text[i + 1] === '"') { field += '"'; i++; } else q = false; } else field += c;
    } else if (c === '"') q = true;
    else if (c === ',') { row.push(field); field = ''; }
    else if (c === '\n') { row.push(field); rows.push(row); row = []; field = ''; }
    else if (c !== '\r') field += c;
  }
  if (field !== '' || row.length) { row.push(field); rows.push(row); }
  const head = rows.shift();
  return rows.filter((r) => r.length === head.length).map((r) => Object.fromEntries(head.map((h, i) => [h, r[i]])));
}

function load(name) {
  if (!cache[name]) cache[name] = parseCsv(fs.readFileSync(path.join(DATA, name), 'utf8'));
  return cache[name];
}

function norm(hs) {
  const d = String(hs).replace(/\D/g, '');
  return [4, 6, 8].includes(d.length) ? d : '';
}

function lookup(hs) {
  const d = norm(hs);
  if (!d) return null;
  const r = load('all.csv').find((x) => x.hs_code === d);
  return r ? { ...r } : null;
}

function measures(hs) {
  const d = norm(hs);
  if (!d) return [];
  return load('measures.csv').filter((m) => m.hs8.startsWith(d)).map((m) => ({ ...m }));
}

function search(text, limit = 20) {
  const words = String(text).toLowerCase().split(/\W+/).filter(Boolean);
  if (!words.length) return [];
  const hits = [];
  for (const r of load('all.csv')) {
    if (r.level !== '8') continue;
    const hay = [r.hs_code, r.hs6_description, r.description].join(' ').toLowerCase();
    if (words.every((w) => hay.includes(w))) {
      hits.push([words.every((w) => r.hs6_description.toLowerCase().includes(w)) ? 0 : 1, r.description.length, r]);
    }
  }
  hits.sort((a, b) => a[0] - b[0] || a[1] - b[1] || (a[2].hs_code < b[2].hs_code ? -1 : 1));
  return hits.slice(0, limit).map((h) => ({ ...h[2] }));
}

module.exports = { lookup, measures, search };
