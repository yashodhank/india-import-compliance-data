# Changelog

Newest first, one entry per release tag, each naming the data delta and the official instrument behind it. Row counts per list are in each data directory's `PROVENANCE.csv`. Refresh entries are written by the workflow.

Tag names after `v2026.10.22` carry the date they were planned for; every tag up to `v2026.10.25` was cut on 2026-10-22, and the dates below are the dates the releases were actually published. The same feed is published as `feed.xml` on the project site.

## Unreleased

Changes on `main` after `v2026.10.22.1643`; they ship in the next release.

- Fix: `data/bis/isi_qco.csv` notes are no longer cut at 600 characters and keep orders that only one of the Scheme-I page's table copies lists, so the Cookware and Utensils row notes now end with the Second Order, 2026, S.O. 5624(E), 13 October 2026. `data/qco` gains that event; the QCO register goes from 310 to 309 records (a spurious second Steel and Steel Products record, an artefact of the cut text, is merged into the main one).
- Pipeline: `refresh-report.json` `stale[]` entries carry `age_days` and `escalate` (true when stale for more than 30 days or of unknown age); schema in `pipeline/refresh-report.schema.json`. New `python -m pipeline.check` asserts the published data's consistency.
- Fix: the three Animal Feeds rows in `data/bis/isi_qco.csv` (IS 1664, IS 5470, IS 920) are grouped under "Animal Feeds and Feed Ingredients" (Animal Feeds and Feed Ingredients (Quality Control) Order, 2026, S.O. 5576(E)) instead of the section above them, and the three compregs rows (IS 3513 Parts 1-3) keep the section the first table copy gives them; `data/qco` and `data/measures` follow. No row added or removed.
- Pipeline: a robots.txt transport fault is retried once and then goes to the paid fallback; the fallback sends the project's User-Agent (the API edge refused urllib's default, so every runner fallback on 2026-10-22 failed). CRS and BEE lists may therefore refresh from the runner (not yet confirmed on a live run); ITC(HS) and TEC MTCTE remain operator-machine refreshes.
- Docs and site: this changelog, `feed.xml`, `api/index.json` with JSON Schemas, a data dictionary (`docs/data-dictionary.md`), SECURITY, CONTRIBUTING and CODE_OF_CONDUCT.

## v2026.10.22.1643, 2026-10-22

- Note: the three added `data/bis/isi_qco.csv` rows (IS 1664, IS 5470, IS 920) come from the Animal Feeds and Feed Ingredients (Quality Control) Order, 2026, S.O. 5576(E) dated 12 October 2026. 26 Foot Wear rows (IS 5557, 5676, 6664, 6719 and others) are active again: the 2020 order was rescinded on 3 June 2022 and the same rows list the fresh 2022 order and later amendments, so the last order decides.
- `data/bis/isi_qco.csv`: 799 -> 802 rows; 3 added, 0 removed, 0 status changed, 0 date changed, 3 wording changed.
  - added: Mineral mixtures for supplementing cattle feeds (IS 1664)
  - added: Dicalcium Phosphate, animal feed grade (IS 5470)
  - added: Common salt and cattle licks for animal consumption (IS 920)
- `data/bis/qco_upcoming.csv`: 122 -> 120 rows; 1 added, 3 removed, 0 status changed, 2 date changed, 117 wording changed.
  - added: Combination Side Cutting Pliers (3650:1981) [serial 26]
  - removed: Wrought Aluminium Utensils (IS 1660:2024)
  - removed: Combination Side Cutting Pliers (3650:1981) [serial 28]
  - removed: Combination Side Cutting Pliers (3650:1981) [serial 31]
  - `data/bis/qco_upcoming.csv`: Combination Side Cutting Pliers (3650:1981): listed 2 times before, 1 now (BIS de-duplicated its own list); one row kept
  - `data/bis/qco_upcoming.csv`: Wrought Aluminium Utensils (IS 1660:2024): now in force, listed in Scheme-I
- `data/bis/crs.csv`: STALE since 2026-10-01, last good data kept: robots.txt of www.crsbis.in could not be read (<urlopen error [Errno -3] Temporary failure in name resolution>): nothing is fetched from it
- `data/tec/mtcte.csv`: STALE since 2026-10-21, last good data kept: the origin served an older edition of the PDF (created 2022-07-14, 411917 bytes; the archived copy was created 2023-06-26)
- `data/bee/mandatory.csv`: STALE since 2026-10-22, last good data kept: robots.txt of www.beestarlabel.com could not be read (<urlopen error timed out>): nothing is fetched from it
- `data/bee/voluntary.csv`: STALE since 2026-10-21, last good data kept: robots.txt of www.beestarlabel.com could not be read (<urlopen error timed out>): nothing is fetched from it
- `data/itchs/2022`: STALE since 2026-10-22, last good data kept: HTTP 403 from https://www.dgft.gov.in/CP/?opt=itchs-import-export
Fallback fetches: 0, cost USD 0.0000
- `data/qco`: 310 register records, 912 events.

## v2026.10.25, 2026-10-22

IS-standards metadata added and joined to the measures. No source list changed. Instrument: BIS Know Your Standards (metadata only).

- `data/is-standards/` (new): `standards.csv` 1,187 rows (title, year, status, supersession, amendments, reaffirmation year, QCO label, classification), `unmatched.csv` 64, `PROVENANCE.csv`, `BUILD-REPORT.json`. From BIS Know Your Standards, metadata only; 1,187 detail pages archived under `raw/is-standards/2026-10-22/`. 21 references are not yet fetched. All 1,187 are `current` or `unknown`; none is withdrawn or superseded (latest edition is matched; see `DATA-QUALITY.md`).
- `pipeline/adapter_kys.py` (new): polite (2 s), login-free, resumable; stops on 403 or 429. `refresh.yml` runs it monthly.
- `data/measures/`: three new columns `is_title`, `is_status`, `is_superseded_by`; 227 of 830 rows that name an IS number gained a title and status (430 name a multi-part standard without a part and are not guessed). Row count unchanged at 16,900. No measure `status` changed.

## v2026.10.24.1, 2026-10-22

Two official HS-linked inputs added to the measures table. No source list changed. Instruments: the 2020 Steel QCO notifications (S.O. 756(E), S.O. 574(E), S.O. 3716(E)) and DGFT Appendix III.

- `data/hs-links/` (new, static inputs with `PROVENANCE.csv`; PDFs archived under `raw/hs-links/`, the two over 2 MB by URL and hash only): the HS column printed in the three 2020 Steel QCO gazette PDFs (812 code-per-order rows from 2,584 page-level rows; 460 codes in ITC(HS) 2022, 22 are not and are listed in `BUILD-REPORT.json`), and DGFT Appendix III (83 IS numbers, no HS codes).
- `data/measures/`: 16,900 rows (was 15,996). `bis_isi_qco` 437 -> 1,341: 784 from the steel HS columns (basis "QCO S.O. ... HS column, page N", legal_ref the S.O. printed on that PDF) and 120 where the ITC(HS) text names an IS number that Appendix III lists (document code `BIS-APP3`, basis "Appendix III serial N"). Codes with an official BIS row 185 -> 548.
- QCO register records mapped to an HS code: 116 of 311 before and after. The steel order was already mapped through IS numbers; the three PDFs add codes to it, not new records. 195 remain unmapped.

## v2026.10.24, 2026-10-22

Measures, a static API and lookup packages. No source list changed. Instruments: DGFT notification 54/2015-2020 and the other notifications printed on each ITC(HS) line (`legal_ref`).

- `data/measures/` (new): 15,996 rows, one per (8-digit code, measure), in the shape of a tariff measure. `import_policy` 12,587 (every 8-digit line), `policy_condition` 2,211, `import_monitoring` 435, `bis_isi_qco` 437, `bis_upcoming_qco` 273, `bis_crs` 32, `other_condition` 21 (11 of them keyword candidates). BIS measures are attached only where the ITC(HS) text names an IS number carried by a BIS list; 116 of 311 QCO register records are mapped to an HS code, 195 are listed as unmapped in `BUILD-REPORT.json`. The TEC, BEE and whole-CRS lists carry no official HS link here and are not joined. Document codes: `docs/document-codes.md`.
- Static JSON API and per-chapter HTML pages (`pipeline/site.py`), `openapi.yaml`, and a GitHub Pages workflow.
- `packages/python` and `packages/node`: offline `lookup`, `measures`, `search`; not published.

## v2026.10.23, 2026-10-22

Adapter fixes. `v2026.10.22` and `v2026.10.22.1` under-counted Scheme I by 89 rows. Instrument: the BIS Scheme-I page (IS 302 household appliances).

- `data/bis/isi_qco.csv`: 710 -> 799 rows. The BIS Scheme-I page lets the serial, IS code and notification cells span several product rows (rowspans); 89 household-appliance rows (IS 302) were read as section titles and dropped. Tables are now read by column with rowspans honoured, and the expected row count comes from the page's own `<tr>` rows by elimination, so a mismatch fails the run. One row previously carried a stray digit from a neighbouring cell and was re-read.
- `data/qco/*`: register 310 -> 311 records, products 906 -> 995, events 904 -> 909, as a consequence.
- Other adapter hardening, no change in the other lists' rows: PDF serial-band count check; case-insensitive status words including "rescinded"; 2 s wait counted from the end of the previous response; strict robots.txt handling (404/410 or HTML means no rules, any other answer refuses the host); BEE discontinued-section detection; machinery table counted per `<tr>`; HTTP timeout plumbing; diff keyed on scheme and serial for legitimately repeated keys.

## v2026.10.22.1, 2026-10-22

Corrections to v2026.10.22. Do not cite the earlier release for `hs-scheme-candidates.csv`. Instrument: ITC(HS) 2022 condition text; CRS list (MeitY/BIS).

- Wrong label: `hs-scheme-candidates.csv` mapped 200 codes to `CRS` because their condition text says "Compulsory Registration". In ITC(HS) that phrase means registration on an import-monitoring system (PIMS for paper in all 200 cases), not BIS CRS. Rows are now labelled `PIMS`, `SIMS`, `CHIMS`, `NFMIMS` or `import_monitoring`; `CRS` is used only where the text names the Compulsory Registration Order, CRO, MeitY or Electronics and Information Technology Goods. The `scheme_hint` column is now schema-checked and a test forbids the old mapping.
- The archived CRS page in `raw/` had been altered (one third-party stylesheet host rewritten). It is restored to the bytes received, and the pipeline no longer rewrites archived pages.

## v2026.10.22, 2026-10-22

Initial release. Instruments: ITC(HS) 2022 Schedule 1 (DGFT) and the BIS Scheme-I, II, IV, X, upcoming-QCO and Option-2 lists; QCO orders as printed on the Scheme-I page.

- `data/itchs/2022`: ITC(HS) 2022 Schedule 1 (Import Policy), 97 chapters, 15,943 lines (12,587 at 8 digits), chapter policy conditions.
- `data/bis`: Scheme I (710), CRS (74), Scheme II other (9), Scheme IV (2), Scheme X (52), upcoming QCOs (122), Option-2 (1,085).
- `data/tec/mtcte.csv` (200); `data/bee` mandatory (19) and voluntary (23).
- `data/qco`: register (310 records), events, products, Gazette PDF hashes.
- `data/derived/hs-scheme-candidates.csv` (393).
