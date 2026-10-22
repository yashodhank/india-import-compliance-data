# India import compliance data

Open, versioned, weekly-refreshed tables that answer one question: **what does Indian import policy and product-compliance regulation say about this product?**

Every row carries its source URL, retrieval date and a hash of the archived original, so any figure can be traced back to the page or Gazette it came from.

**Not legal advice.** Every row carries an `as_of` date; it was true of the source on that date only.
The official source prevails over this repository wherever they differ.
Confirm with the issuing authority before you ship, file or certify anything.

## Where this fits

This is **not a trade-statistics dataset**. It holds no import values, volumes, ports or partner countries. It answers what approval applies to a product at import, per HS code. The repositories below answer other questions and complement it: join them on the HS code (`hs6` here is the common key).

| Repository | What it answers | Licence | Use it with this one for |
|---|---|---|---|
| [Vonter/india-export-import](https://github.com/Vonter/india-export-import) | How much India trades: DGCIS FTDDP values by commodity, port and country | ODbL | Value and volume of a code you are checking the rules for |
| [Lekh007/india-import-atlas-data](https://github.com/Lekh007/india-import-atlas-data) | Sector import bill, import-substitution ratings, ventures | GODL and CC BY 4.0 | Where imports are large, then what approval each line needs |
| [lakshyaag/India-Trade-Data](https://github.com/lakshyaag/India-Trade-Data) | A scraper for the TRADESTAT portal | see the repository | Fetching statistics to put beside the policy tables |
| [datasets/harmonized-system](https://github.com/datasets/harmonized-system) | HS 2022 nomenclature to six digits (data package) | ODC-PDDL-1.0 | The source of `data/hs6/`; the shared vocabulary of all of the above |
| **this repository** | What approval applies per HS code: ITC(HS) policy and conditions, BIS, QCO, TEC and BEE lists, QCO register with Gazette hashes | CC BY 4.0 (data), MIT (code) | |

The licence column is as stated by each project when this section was written; check it before reuse.

## What is here

| Dataset | Path | Rows | Source |
|---|---|---|---|
| HS 2022 six-digit descriptions (join table for `hs6`) | `data/hs6/harmonized-system.csv` | 5,613 | datasets/harmonized-system (WCO nomenclature via UN Comtrade) |
| ITC(HS) 2022 Schedule 1 (Import Policy), all 97 chapters, 4, 6 and 8-digit lines, with `hs6` and `hs6_description` columns | `data/itchs/2022/` (`all.csv`, `chNN.csv`, `chNN.json`) | 15,943 lines, of which 12,587 are 8-digit | DGFT |
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
| Measures: one row per (8-digit code, measure) | `data/measures/measures.csv`, `measures.json`, `BUILD-REPORT.json` | 16,900 | derived from the tables above |
| IS standards metadata: title, year, status, amendments, classification per IS number (no standard texts) | `data/is-standards/standards.csv`, `unmatched.csv`, `BUILD-REPORT.json` | 1,187 + 64 unmatched | BIS Know Your Standards |

Each data directory has a `PROVENANCE.csv`: source URL, retrieval date, row count, the source's own row count (the two must be equal or the run fails), SHA-256 of the published file and of the raw copy under `raw/`.

The HS to scheme file is **candidates only**: a keyword match on the official condition text (BIS, IS, CRS order, import-monitoring systems, QCO, WPC, TEC, BEE, Legal Metrology, EPR, CDSCO, FSSAI). It is a pointer to where a rule may apply, not a determination that one does. Read `DATA-QUALITY.md` before relying on any table.

## Data model: measures

`data/measures/measures.csv` encodes what applies to a code the way a tariff does: as measures. This follows the shape of the UK Online Trade Tariff (measure type, conditions, document codes, legal base, validity), filled from the Indian sources held here.

- One row per (`hs8`, measure). Every 8-digit ITC(HS) line has an `import_policy` row (`Free`, `Restricted`, `Prohibited`, `STE`), with the DGFT notification in `legal_ref` and its date in `valid_from`.
- `policy_condition`: the line's own condition text, and each chapter policy condition it cites, verbatim with HTML stripped. `basis` says which ("row condition", "chapter condition 6").
- `import_monitoring`: SIMS, CHIMS, NFMIMS, PIMS or another system the text names (`document_code` carries the system).
- `bis_isi_qco`, `bis_upcoming_qco`, `bis_crs`, `bis_scheme_x`: a BIS measure is attached to a code **only** where the ITC(HS) text for that code (or the chapter condition it cites) names an IS number that a BIS list also carries. `legal_ref` is the S.O. number from the QCO register; `qco_slug` keys into `data/qco/register.csv`.
- `other_condition`: a named standard that no BIS list carries (`BIS-STD`), and keyword **candidates** (`confidence=candidate`, `basis` starts with "candidate"). A candidate points to where a rule may apply; it is not a determination.
- `document_code` is a short stable code for the certificate (`BIS-ISI`, `BIS-CRS`, `TEC-MTCTE`, `BEE-LABEL`, `DGFT-LIC`, `SIMS`, ...), defined in `docs/document-codes.md`. `status` is `in_force`, `upcoming` or `withdrawn`; a blank `valid_to` means open. `source_file` and `source_sha256` name the repository files a row came from.

BIS measures also come from two further official inputs in `data/hs-links/`: the HS column printed in the three 2020 Steel QCO gazette PDFs (basis "QCO S.O. ... HS column, page N"), and DGFT Appendix III, which lists IS numbers without HS codes and is used as an additional basis ("Appendix III serial N") where the ITC(HS) text names the IS number.

**What it does not do.** No official text held here ties the TEC MTCTE list, the BEE lists, the CRS list as a whole, or most QCOs to an HS code: those lists are by product name. They are therefore not joined to codes, and `data/measures/BUILD-REPORT.json` lists the QCO register records that are unmapped (`qco_unmapped_to_hs`). Absent from `measures.csv` means "not tied to this code by an official text we hold", not "does not apply".

Worked example, `85171300` (smartphones): one `import_policy` row, `Free`, `legal_ref` `54/2015-2020`, `valid_from` 2022-02-09. Nothing else is tied to this code by official text here, although smartphones are a product line in `data/tec/mtcte.csv` and may be in `data/bis/crs.csv`; look those up by product name and check the authority.

Worked example, `72104100` (galvanised corrugated steel): `import_policy` `Free`; `policy_condition` "Galvanised steel sheets (plain and corrugated) must conform to IS 277"; `bis_isi_qco` `IS 277` with `document_code` `BIS-ISI`, `legal_ref` `S.O. 756(E); S.O. 574(E); S.O. 3716(E)`, `valid_from` 2020-02-14 and `qco_slug` of the steel QCO record; and a second `bis_isi_qco` row, `BIS-ISI-OPT2`, from the Option-2 list.

## Static API

Generated by `python -m pipeline.site OUTDIR` and published to GitHub Pages at <https://yashodhank.github.io/india-import-compliance-data/> by `.github/workflows/pages.yml` after the tests pass. Plain files, no service:

- `api/latest.json`: release, `as_of`, counts.
- `api/codes/<hs8>.json`: the code, its description, `hs6` and its description, and its measures.
- `api/chapters/<NN>.json` and `chapters/<NN>.html`: every code of a chapter with its policy and the other measures.
- `openapi.yaml` describes the three endpoints.

The pages carry `noindex` and `robots.txt` disallows crawling until release `v2026.10.24`.

## IS standards (metadata only — standard texts are BIS copyright; source: BIS Know Your Standards)

`data/is-standards/` answers "what is IS 302 (Part 1), and is it still current?" for every IS number that the BIS lists and the QCO register in this repository name (1,272 number-and-part references; 1,187 matched, 64 not matched, 21 not yet fetched). It holds **metadata only**: the standard's number, part, title, year, status, supersession, amendments list, reaffirmation year, the QCO label and the classification block the portal prints. The text of a standard is BIS copyright; no standard, amendment file or Gazette PDF is fetched or redistributed.

- Source: BIS "Know Your Standards" on BIS Connect (`services.bis.gov.in`), the public search, no login. `source_url` and `pk_is_id` name the page; the page bytes are archived under `raw/is-standards/<date>/<pk_is_id>.html` with the hash in `sha256_detail`.
- Key: `is_no` as `IS 302 (Part 1)`. The references in this repository carry no year, so **the latest edition** the portal lists is matched. `status` is `current`, `withdrawn`, `superseded` or `unknown`, read from the portal's result list (the details page carries no status); `unknown` means the chosen edition was not in that list.
- `unmatched.csv` lists the references the portal search did not match exactly, with the nearest portal hits for a person to judge; none is guessed. `data/is-standards/BUILD-REPORT.json` holds the counts.
- Join: `data/measures/measures.csv` carries `is_title`, `is_status`, `is_superseded_by` on `bis_isi_qco` and `bis_upcoming_qco` rows whose `measure_value` is a single IS number and part found in the table (227 rows). A standard's portal status is a data-quality signal only: it never changes a measure's own `status`, which comes from the order. A number printed without a part is not joined to a multi-part standard.
- Not on the public page: ICS codes, and the QCO document list (the endpoint is gated for an anonymous session and is not called). See `DATA-QUALITY.md`.
- Refresh: `python -m pipeline.adapter_kys` (monthly workflow). robots.txt first, 2 s between requests, a user agent naming this repository. It fetches the references never fetched first, then the oldest, at most 400 per run, and stops on HTTP 403 or 429; the next run resumes from the CSVs.
- Use the attribution: *Source: Bureau of Indian Standards (BIS), Know Your Standards, https://www.services.bis.gov.in, retrieved 2026-10-22, metadata republished in `india-import-compliance-data`.*

## Packages

Zero-dependency offline lookups with the same API, `lookup(hs)`, `measures(hs)`, `search(text)`. Not published to PyPI or npm.

    pip install "git+https://github.com/yashodhank/india-import-compliance-data.git#subdirectory=packages/python"
    git clone --depth 1 https://github.com/yashodhank/india-import-compliance-data.git && npm install ./india-import-compliance-data/packages/node

`packages/sync.py` copies `all.csv` and `measures.csv` into both packages; a test in each fails when the copy differs from `data/`.

## Licences

- **Data** (`data/`, `schemas/`): [CC BY 4.0](LICENSE-DATA). Attribute this repository and the original source named below.
- **HS6 table** (`data/hs6/`): redistributed from [datasets/harmonized-system](https://github.com/datasets/harmonized-system) under ODC-PDDL-1.0 (public domain dedication); source and hash in `data/hs6/PROVENANCE.csv`.
- **Code** (`pipeline/`, `tests/`, `.github/`): [MIT](LICENSE-CODE).

## Source acknowledgement

Use the line for each dataset you reuse.

- ITC(HS): *Source: Directorate General of Foreign Trade (DGFT), Ministry of Commerce and Industry, Government of India, ITC(HS) 2022 Schedule 1 (Import Policy), https://www.dgft.gov.in. Retrieved 2026-10-22, republished in `india-import-compliance-data`.*
- BIS lists and Option-2 list: *Source: Bureau of Indian Standards (BIS), https://www.bis.gov.in, products under compulsory certification and related lists.*
- CRS: *Source: Compulsory Registration Scheme portal, Ministry of Electronics and Information Technology and BIS, https://www.crsbis.in.*
- MTCTE: *Source: Telecommunication Engineering Centre (TEC), Department of Telecommunications, Government of India, https://mtcte.tec.gov.in.*
- BEE: *Source: Bureau of Energy Efficiency (BEE), Ministry of Power, Government of India, https://www.beestarlabel.com.*
- IS standards metadata: *Source: Bureau of Indian Standards (BIS), Know Your Standards, https://www.services.bis.gov.in. Metadata only; the standards themselves are BIS copyright.*
- QCO register: *Derived from the BIS lists above and the Gazette of India (https://egazette.gov.in) notifications they cite.*

## Legal basis for republication

The ITC(HS) chapters were acquired with permission from DGFT under ticket `DGFTCOMS-2026-24H4345L` (recorded as `permission_ref` in `data/itchs/2022/PROVENANCE.csv`). Policy text published in the Gazette of India is also covered by section 52(1)(q) of the Copyright Act, 1957 (reproduction of matter published in the Official Gazette). The other lists are public pages of the named authorities, read politely (see below). This repository is not an official publication of any of these bodies. For legal effect, consult the Gazette and the authority's own current page.

## Using the data

```python
import csv
rows = list(csv.DictReader(open("data/itchs/2022/all.csv", encoding="utf-8")))
hit = [r for r in rows if r["hs_code"] == "85171300"]
```

Every CSV is UTF-8, LF line endings, comma separated, with a header row. `schemas/*.json` holds a Table Schema for each shape and `schemas/index.json` maps each file to its schema. `datapackage.json` at the root is a [Frictionless Data Package](https://datapackage.org) describing every CSV (regenerate with `python -m pipeline.datapackage`; a test fails when it is stale). To join on the international code, use `hs6`: 24 of the 5,629 distinct `hs6` values are India-specific splits or chapters 98/99 with no WCO line and a blank `hs6_description`; `BUILD-REPORT.json` lists them. Releases (`vYYYY.MM.DD`) carry the main CSVs as assets, and `CHANGELOG.md` says what changed.

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
- **PDFs.** A refused PDF is tried from the Internet Archive first (verbatim bytes). The scraping API returns only extracted text for a PDF, never the file, so that copy is never archived or parsed as a list; it is used only by the change monitor, and the refresh fails loudly if a list PDF can only be had that way. Verbatim original bytes come only from the origin or the Internet Archive.
- **Ceiling.** `ALTERLAB_MAX_USD` (default 0.25) is the most one run may spend; when it is reached the fallback is not used for the rest of the run and the run summary says so. Each refresh entry in `CHANGELOG.md` ends with `Fallback fetches: N, cost USD x.xxxx`.
- **Change detection.** `.github/workflows/monitor.yml` runs every 6 hours: it fetches each of the 10 source pages by the cheapest route, normalises the body (whitespace, scripts, styles, CSRF tokens, cache-busting query values, copyright year), compares its SHA-256 with `state/monitor.json`, and starts the refresh workflow when one differs. The weekly refresh stays as the safety net.
- **Cost model.** Direct fetch: free. Fallback: only for a refused source, a fraction of a cent per page. Monitor: at most 12 sources x 4 runs a day, direct unless refused, so zero in the normal case and bounded by its own `ALTERLAB_MAX_USD` (0.10) per run otherwise.

```
python -m pipeline.refresh --offline    # rebuild every file from the archived raw copies, no network
python -m pipeline.refresh              # fetch and rebuild
python -m pytest tests                  # golden tests, schema validation of every CSV, pipeline behaviour
```

## Contributing

Corrections are welcome: see `CORRECTIONS.md` and the issue forms. Include a pointer to the official page or Gazette that shows the right value. Files under `data/` are generated: fix the parser or the archived input, not the CSV.

## Raw archive

`raw/<source>/<date>/` holds the bytes each source returned, **verbatim**: nothing is rewritten, so `raw_sha256` in `PROVENANCE.csv` verifies against what the server sent. Third-party links inside an archived page are that page's own content.

## Glossary

- **Compulsory Registration (in ITC(HS) condition text)**: registration on a DGFT import-monitoring system, not BIS certification. Named systems: SIMS (steel), CHIMS (chips), NFMIMS (non-ferrous metals), PIMS (paper). In `hs-scheme-candidates.csv` these appear as `SIMS`, `CHIMS`, `NFMIMS`, `PIMS`, or `import_monitoring` when the text does not name the system.
- **CRS**: BIS Compulsory Registration Scheme for electronics (Scheme II; list in `data/bis/crs.csv`). A candidate is labelled `CRS` only when the condition text says "Compulsory Registration Order", "CRO", "MeitY" or "Electronics and Information Technology Goods".
- **QCO**: Quality Control Order. **MTCTE**: Mandatory Testing and Certification of Telecom Equipment.
