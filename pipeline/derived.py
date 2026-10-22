"""Derived file: HS codes whose official condition text names a scheme, regulator or standard. Candidates only; nothing is concluded."""
import csv
import io
import re

COLS = ['hs_code', 'chapter', 'scheme_hint', 'matched_terms', 'condition_text', 'as_of', 'method']
METHOD = 'keyword match on the official condition text; candidates only'

# (hint, regex). Acronyms are matched in capitals only, as the Schedule writes them.
PATTERNS = [
    ('BIS', re.compile(r'\bBIS\b|Bureau of Indian Standards')),
    ('IS', re.compile(r'\bIS\s*[:.]?\s*\d{2,}|Indian Standards?\b')),
    ('CRS', re.compile(r'\bCRS\b|Compulsory Registration')),
    ('QCO', re.compile(r'\bQCOs?\b|Quality Control Orders?')),
    ('WPC', re.compile(r'\bWPC\b|Wireless Planning')),
    ('TEC', re.compile(r'\bTEC\b|Telecommunication Engineering Cent')),
    ('BEE', re.compile(r'\bBEE\b|Bureau of Energy Efficiency')),
    ('LegalMetrology', re.compile(r'Legal Metrology', re.I)),
    ('EPR', re.compile(r'\bEPR\b|Extended Producer Responsibility')),
    ('CDSCO', re.compile(r'\bCDSCO\b|Central Drugs? Standard')),
    ('FSSAI', re.compile(r'\bFSSAI\b|Food Safety and Standards')),
]


def candidates(rows):
    out = []
    for r in rows:
        if r['level'] != '8' and r['level'] != 8:
            continue
        text = r['condition_text']
        hits = [(h, m.group(0)) for h, p in PATTERNS for m in [p.search(text)] if m]
        if not hits:
            continue
        out.append({'hs_code': r['hs_code'], 'chapter': r['chapter'], 'scheme_hint': ';'.join(h for h, _ in hits),
                    'matched_terms': ';'.join(dict.fromkeys(t for _, t in hits)), 'condition_text': text, 'as_of': r['as_of'], 'method': METHOD})
    out.sort(key=lambda r: r['hs_code'])
    return out


def to_csv(rows):
    buf = io.StringIO(newline='')
    w = csv.DictWriter(buf, fieldnames=COLS, lineterminator='\n')
    w.writeheader()
    w.writerows(rows)
    return buf.getvalue().encode('utf-8')
