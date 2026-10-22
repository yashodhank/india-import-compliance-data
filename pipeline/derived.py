"""Derived file: HS codes whose official condition text names a scheme, regulator or standard. Candidates only; nothing is concluded."""
import csv
import io
import re

COLS = ['hs_code', 'chapter', 'scheme_hint', 'matched_terms', 'condition_text', 'as_of', 'method']
METHOD = 'keyword match on the official condition text; candidates only'

MONITORING = {'SIMS', 'CHIMS', 'NFMIMS', 'PIMS'}

# (hint, regex). Acronyms are matched in capitals only, as the Schedule writes them.
PATTERNS = [
    ('BIS', re.compile(r'\bBIS\b|Bureau of Indian Standards')),
    ('IS', re.compile(r'\bIS\s*[:.]?\s*\d{2,}|Indian Standards?\b')),
    # BIS CRS only from text that names the BIS order or the ministry; "Compulsory Registration" in ITC(HS) text means an import-monitoring system
    ('CRS', re.compile(r'Compulsory Registration Order|\bCRO\b|\bMeitY\b|Electronics and Information Technology Goods')),
    ('SIMS', re.compile(r'\bSIMS\b|Steel Import Monitoring System')),
    ('CHIMS', re.compile(r'\bCHIMS\b|Chip Import Monitoring System')),
    ('NFMIMS', re.compile(r'\bNFMIMS\b|Non-?\s?Ferrous Metal Import Monitoring System')),
    ('PIMS', re.compile(r'\bPIMS\b|Paper Import Monitoring System')),
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
        if re.search(r'Compulsory Registration|Import Monitoring System', text) and not any(h in MONITORING for h, _ in hits):
            hits.append(('import_monitoring', re.search(r'Compulsory Registration|Import Monitoring System', text).group(0)))
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
