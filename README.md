# India import compliance data

Open, versioned, weekly-refreshed tables that answer one question: **what does Indian import policy and product-compliance regulation say about this product?**

Every row carries its source URL, retrieval date and a hash of the archived original, so any figure can be traced back to the page or Gazette it came from.

## What is here

| Dataset | Path | Rows | Source |
|---|---|---|---|
| ITC(HS) 2022 Schedule 1 (Import Policy), all 97 chapters, 4, 6 and 8-digit lines | `data/itchs/2022/` (`all.csv`, `chNN.csv`, `chNN.json`) | 15,943 lines, of which 12,587 are 8-digit | DGFT |
| Chapter policy conditions and notes | `data/itchs/2022/chapter-conditions.csv`, `section-notes.csv` | 729 + 53 | DGFT |
| BIS Scheme I (ISI / QCO) | `data/bis/isi_qco.csv` | 799 | BIS |
| BIS Scheme II (CRS, registration) | `data/bis/crs.csv`, `data/bis/scheme_ii_other.csv` | 74 + 9 | CRS portal, BIS |
| BIS Scheme IV, Scheme X | `data/bis/scheme_iv.csv`, `data/bis/scheme_x.csv` | 2 + 52 | BIS |
| BIS upcoming QCOs | `data/bis/qco_upcoming.csv` | 122 | BIS |
| BIS Option-2 (simplified procedure) list | `data/bis/option2.csv` | 1,085 | BIS |
| TEC MTCTE product list | `data/tec/mtcte.csv` | 200 | TEC |
| BEE star-label lists | `data/bee/mandatory.csv`, `voluntary.csv` | 19 + 23 | BEE |
| QCO register (order, S.O. number, dates, IS codes, state, Gazette PDF hash) | `data/qco/register.csv`, `register.json`, `events.csv`, `products.csv` | 311 records | derived from the BIS lists and the Gazette |
| HS to scheme candidates | `data/derived/hs-scheme-candidates.csv` | 402 | derived from the ITC(HS) condition text |

Each data directory has a `PROVENANCE.csv`: source URL, retrieval date, row count, the source's own row count (the two must be equal or the run fails), SHA-256 of the published file and of the raw copy under `raw/`.

The HS to scheme file is **candidates only**: a keyword match on the official condition text (BIS, IS, CRS order, import-monitoring systems, QCO, WPC, TEC, BEE, Legal Metrology, EPR, CDSCO, FSSAI). It is a pointer to where a rule may apply, not a determination that one does. Read `DATA-QUALITY.md` before relying on any table.

## Licences

- **Data** (`data/`, `schemas/`): [CC BY 4.0](LICENSE-DATA). Attribute this repository and the original source named below.
- **Code** (`pipeline/`, `tests/`, `.github/`): [MIT](LICENSE-CODE).

## Source acknowledgement

Use the line for each dataset you reuse.

- ITC(HS): *Source: Directorate General of Foreign Trade (DGFT), Ministry of Commerce and Industry, Government of India, ITC(HS) 2022 Schedule 1 (Import Policy), https://www.dgft.gov.in. Retrieved 2026-10-22, republished in `india-import-compliance-data`.*
- BIS lists and Option-2 list: *Source: Bureau of Indian Standards (BIS), https://www.bis.gov.in, products under compulsory certification and related lists.*
- CRS: *Source: Compulsory Registration Scheme portal, Ministry of Electronics and Information Technology and BIS, https://www.crsbis.in.*
- MTCTE: *Source: Telecommunication Engineering Centre (TEC), Department of Telecommunications, Government of India, https://mtcte.tec.gov.in.*
- BEE: *Source: Bureau of Energy Efficiency (BEE), Ministry of Power, Government of India, https://www.beestarlabel.com.*
- QCO register: *Derived from the BIS lists above and the Gazette of India (https://egazette.gov.in) notifications they cite.*

## Legal basis for republication

The ITC(HS) chapters were acquired with permission from DGFT under ticket `DGFTCOMS-2026-24H4345L` (recorded as `permission_ref` in `data/itchs/2022/PROVENANCE.csv`). Policy text published in the Gazette of India is also covered by section 52(1)(q) of the Copyright Act, 1957 (reproduction of matter published in the Official Gazette). The other lists are public pages of the named authorities, read politely (see below). This repository is not an official publication of any of these bodies. For legal effect, consult the Gazette and the authority's own current page.

## Using the data

```python
import csv
rows = list(csv.DictReader(open("data/itchs/2022/all.csv", encoding="utf-8")))
hit = [r for r in rows if r["hs_code"] == "85171300"]
```

Every CSV is UTF-8, LF line endings, comma separated, with a header row. `schemas/*.json` holds a Table Schema for each shape and `schemas/index.json` maps each file to its schema. Releases (`vYYYY.MM.DD`) carry the main CSVs as assets, and `CHANGELOG.md` says what changed.

## How it stays current

`pipeline/` is plain Python 3.12 (standard library; `pdftohtml` from poppler for the two PDF lists). A GitHub Actions workflow runs weekly (Monday 02:00 IST) and on demand:

1. fetch each source: `robots.txt` honoured, 2 seconds between requests to a host (1 second for the DGFT web app), a user agent that names this repository;
2. archive the raw bytes under `raw/<source>/<date>/` with SHA-256 (files under 2 MB are committed; larger ones are listed by URL and hash only);
3. parse, and assert that the parsed row count equals the source's own count;
4. a list that is unchanged stays byte-identical; a list that shrinks by more than half is refused;
5. if anything changed and every assertion and test passed: commit to `main`, add a `CHANGELOG.md` entry and publish a release. If anything failed: open or update an issue and publish nothing.

### Fetching, fallback and change detection

- **Direct fetch is free and always first.** `robots.txt` is checked before any request and always wins: a disallowed path is fetched by no route.
- **Fallback only on refusal.** If the origin answers 403, 429 or 5xx, or returns a page that needs JavaScript, and the environment variable `ALTERLAB_API_KEY` (a repository secret of the same name) is set, the page is fetched once through a pay-per-success scraping API with a per-request cap. The bytes it returns are archived and hashed like any direct fetch, and `PROVENANCE.csv` records `fetch_method`, `fetch_tier` and `fetch_cost_usd`. Without the key the pipeline fetches directly only and prints `fallback fetcher: not configured` once.
- **Ceiling.** `ALTERLAB_MAX_USD` (default 0.25) is the most one run may spend; when it is reached the fallback is not used for the rest of the run and the run summary says so. Each refresh entry in `CHANGELOG.md` ends with `Fallback fetches: N, cost USD x.xxxx`.
- **Change detection.** `.github/workflows/monitor.yml` runs every 6 hours: it fetches each of the 10 source pages by the cheapest route, normalises the body (whitespace, scripts, styles, CSRF tokens, cache-busting query values, copyright year), compares its SHA-256 with `state/monitor.json`, and starts the refresh workflow when one differs. The weekly refresh stays as the safety net.
- **Cost model.** Direct fetch: free. Fallback: only for a refused source, a fraction of a cent per page. Monitor: at most 12 sources x 4 runs a day, direct unless refused, so zero in the normal case and bounded by its own `ALTERLAB_MAX_USD` (0.10) per run otherwise.

```
python -m pipeline.refresh --offline    # rebuild every file from the archived raw copies, no network
python -m pipeline.refresh              # fetch and rebuild
python -m pytest tests                  # golden tests, schema validation of every CSV, pipeline behaviour
```

## Contributing

Corrections are welcome as issues or pull requests, ideally with a pointer to the official page or Gazette that shows the right value. Files under `data/` are generated: fix the parser or the archived input, not the CSV.

## Raw archive

`raw/<source>/<date>/` holds the bytes each source returned, **verbatim**: nothing is rewritten, so `raw_sha256` in `PROVENANCE.csv` verifies against what the server sent. Third-party links inside an archived page are that page's own content.

## Glossary

- **Compulsory Registration (in ITC(HS) condition text)**: registration on a DGFT import-monitoring system, not BIS certification. Named systems: SIMS (steel), CHIMS (chips), NFMIMS (non-ferrous metals), PIMS (paper). In `hs-scheme-candidates.csv` these appear as `SIMS`, `CHIMS`, `NFMIMS`, `PIMS`, or `import_monitoring` when the text does not name the system.
- **CRS**: BIS Compulsory Registration Scheme for electronics (Scheme II; list in `data/bis/crs.csv`). A candidate is labelled `CRS` only when the condition text says "Compulsory Registration Order", "CRO", "MeitY" or "Electronics and Information Technology Goods".
- **QCO**: Quality Control Order. **MTCTE**: Mandatory Testing and Certification of Telecom Equipment.
