# Data dictionary

Generated from `schemas/*.json` by `python docs/build_data_dictionary.py`; do not edit by hand. A test fails when this file is stale.
Every CSV is UTF-8, LF line endings, comma separated, with a header row. Each schema is a Frictionless Table Schema.

## appendix3-bis

DGFT Appendix III: IS numbers under mandatory BIS certification for import (no HS codes)

Files: `data/hs-links/appendix3-bis.csv`

| Field | Type | Required | Constraints | Meaning |
|---|---|---|---|---|
| `serial` | integer | yes |  | Serial in Appendix III |
| `is_code` | string | yes |  |  |
| `description` | string | no |  |  |
| `section` | string | no |  |  |
| `notes` | string | no |  |  |
| `source_page` | integer | no |  |  |

## crs

Compulsory Registration Scheme (CRS) product list

Files: `data/bis/crs.csv`

| Field | Type | Required | Constraints | Meaning |
|---|---|---|---|---|
| `product_name` | string | yes |  | Product or item as the official list words it |
| `is_codes` | string | no |  | Indian Standard (IS) codes as printed; blank where the list gives none |
| `scheme` | string | yes |  | Scheme or list the row belongs to |
| `authority` | string | yes |  | Administering authority as printed or inferred from the list page |
| `group` | string | no |  | Section or group title on the source page |
| `source_url` | string | yes | pattern: ^https?:// | URL of the source page or document |
| `retrieved_on` | date | yes | pattern: ^\d{4}-\d{2}-\d{2}$ | Date the source was fetched (or the archive copy was taken) |
| `status` | string | yes | enum: active, upcoming, withdrawn, de-notified, discontinued | Status taken from the source page's own words |
| `notes` | string | no |  | Remaining source text: notification, dates, requirement; verbatim where quoted |
| `enforcement_date` | date | no | pattern: ^\d{4}-\d{2}-\d{2}$ | Date of implementation of the QCO, ISO 8601 |

## hs-scheme-candidates

8-digit ITC(HS) codes whose condition text names a scheme or regulator (candidates only)

Files: `data/derived/hs-scheme-candidates.csv`

| Field | Type | Required | Constraints | Meaning |
|---|---|---|---|---|
| `hs_code` | string | yes | pattern: ^\d{8}$ |  |
| `chapter` | string | yes | pattern: ^\d{2}$ |  |
| `scheme_hint` | string | yes | pattern: ^(BIS\|IS\|CRS\|QCO\|WPC\|TEC\|BEE\|LegalMetrology\|EPR\|CDSCO\|FSSAI\|SIMS\|CHIMS\|NFMIMS\|PIMS\|import_monitoring)(;(BIS\|IS\|CRS\|QCO\|WPC\|TEC\|BEE\|LegalMetrology\|EPR\|CDSCO\|FSSAI\|SIMS\|CHIMS\|NFMIMS\|PIMS\|import_monitoring))*$ | Semicolon-separated hints, each one of: BIS, IS, CRS, QCO, WPC, TEC, BEE, LegalMetrology, EPR, CDSCO, FSSAI, SIMS, CHIMS, NFMIMS, PIMS, import_monitoring |
| `matched_terms` | string | yes |  |  |
| `condition_text` | string | yes |  |  |
| `as_of` | date | yes | pattern: ^\d{4}-\d{2}-\d{2}$ |  |
| `method` | string | yes |  |  |

## hs6

WCO Harmonized System 2022, 6-digit subheadings

Files: `data/hs6/harmonized-system.csv`

| Field | Type | Required | Constraints | Meaning |
|---|---|---|---|---|
| `section` | string | yes |  | HS section (Roman numeral) |
| `hs6` | string | yes | pattern: ^\d{6}$ | Six-digit HS subheading |
| `description` | string | yes |  | WCO description as carried by the source table |
| `parent` | string | yes | pattern: ^\d{4}$ | Four-digit heading |
| `level` | integer | yes | enum: 6 | Always 6 in this table |

Primary key: `hs6`

## is-standards

IS standards metadata from BIS Know Your Standards (no standard texts)

Files: `data/is-standards/standards.csv`

| Field | Type | Required | Constraints | Meaning |
|---|---|---|---|---|
| `is_no` | string | yes | pattern: ^IS \d+( \(Part \d+\))?$ | IS number and part as this repository names it, e.g. IS 302 (Part 1); the key |
| `is_base` | string | yes | pattern: ^\d+$ | Number without part |
| `part` | string | no | pattern: ^\d+$ | Part number, blank when the standard has none |
| `title` | string | yes |  | Title as the portal prints it (portal mojibake repaired where detectable) |
| `year` | string | no | pattern: ^\d{4}$ | Year of the latest edition the portal lists |
| `status` | string | yes | enum: current, withdrawn, superseded, unknown | current, withdrawn, superseded or unknown; read from the portal result list, not the details page |
| `superseded_by` | string | no |  | Text after "Superceded by" in the result list |
| `supersedes` | string | no |  | The portal's "Superseding IS" field: the older edition this one replaces |
| `amendments` | string | no |  | JSON list of {number, year, file}; file names only, no download followed |
| `reaffirmed_year` | string | no |  | Reaffirmation year as printed |
| `qco_status_label` | string | no |  | The QCO label printed on the details page; the QCO document list itself is gated and not fetched |
| `classification` | string | no |  | JSON object: group, sub group, aspect, certification, ministries, ITC-HS code as printed. No ICS: the public page has none |
| `committee` | string | no |  | Technical committee |
| `list_flags` | string | no |  | The result-list row text for the chosen edition, verbatim |
| `match_note` | string | no |  | How the edition was chosen |
| `pk_is_id` | integer | yes |  | Portal internal id of the chosen edition; names the archived page raw/is-standards/<date>/<pk>.html |
| `source_url` | string | yes |  | The BIS details page the record was read from (a POST form; pk_is_id selects the standard) |
| `fetched_at` | string | yes | pattern: ^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$ | UTC timestamp of the fetch |
| `sha256_detail` | string | yes | pattern: ^[0-9a-f]{64}$ | SHA-256 of the details page bytes as received |

## is-standards-unmatched

IS numbers named in this repository that the BIS portal search did not match exactly

Files: `data/is-standards/unmatched.csv`

| Field | Type | Required | Constraints | Meaning |
|---|---|---|---|---|
| `is_no` | string | yes |  |  |
| `is_base` | string | yes | pattern: ^\d+$ |  |
| `part` | string | no | pattern: ^\d+$ |  |
| `reason` | string | yes |  | Why there is no match |
| `candidate_1` | string | no |  | Nearest portal hits, shown and never guessed |
| `candidate_2` | string | no |  |  |
| `candidate_3` | string | no |  |  |
| `fetched_at` | string | yes | pattern: ^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$ |  |

## itchs-chapter-conditions

ITC(HS) 2022 chapter policy conditions and notes

Files: `data/itchs/2022/chapter-conditions.csv`

| Field | Type | Required | Constraints | Meaning |
|---|---|---|---|---|
| `chapter` | string | yes | pattern: ^\d{2}$ |  |
| `note_type` | string | yes |  | Main, Policy Condition, Supplementary Notes or Sub-Heading |
| `serial_no` | string | no |  |  |
| `section` | string | no |  | Roman-numeral section |
| `text` | string | yes |  | Note text, HTML stripped |
| `notification_no` | string | no |  |  |
| `notification_date` | string | no |  |  |
| `as_of` | date | yes | pattern: ^\d{4}-\d{2}-\d{2}$ |  |

## itchs-provenance

Acquisition record of each ITC(HS) chapter export

Files: `data/itchs/2022/PROVENANCE.csv`

| Field | Type | Required | Constraints | Meaning |
|---|---|---|---|---|
| `chapter` | string | yes | pattern: ^\d{2}$ |  |
| `url` | string | yes |  |  |
| `method` | string | yes |  |  |
| `retrieved_at_utc` | string | yes | pattern: ^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$ |  |
| `sha256` | string | yes | pattern: ^[0-9a-f]{64}$ |  |
| `bytes` | integer | yes |  |  |
| `permission_ref` | string | yes |  |  |
| `rows_in_json` | integer | yes |  | 8-digit rows in the export |

Primary key: `chapter`

## itchs-rows

ITC(HS) 2022 Schedule 1 (Import Policy) lines

Files: `data/itchs/2022/all.csv`, `data/itchs/2022/ch01.csv`, `data/itchs/2022/ch02.csv` and 95 more of the same shape

| Field | Type | Required | Constraints | Meaning |
|---|---|---|---|---|
| `hs_code` | string | yes | pattern: ^\d{4}(\d{2}(\d{2})?)?$ | 4, 6 or 8-digit ITC(HS) code |
| `hs6` | string | no | pattern: ^\d{6}$ | First six digits of hs_code (the WCO Harmonized System subheading); blank on 4-digit heading lines. Join key to data/hs6/harmonized-system.csv |
| `hs6_description` | string | no |  | WCO HS 2022 description of hs6, from data/hs6/harmonized-system.csv; blank where hs6 is not in that table (listed in BUILD-REPORT.json hs6_not_in_wco_table) |
| `level` | integer | yes | enum: 4, 6, 8 | Digits in hs_code |
| `chapter` | string | yes | pattern: ^\d{2}$ | Two-digit chapter |
| `description` | string | no |  | Description as printed, HTML removed |
| `policy` | string | no |  | Import policy: Free, Restricted, Prohibited, STE, or blank for non-leaf lines |
| `condition_text` | string | no |  | Policy condition text, HTML stripped, otherwise verbatim |
| `condition_ref` | string | no |  | Policy-condition numbers the text refers to, semicolon separated (extracted, may be incomplete) |
| `notification_no` | string | no |  | DGFT notification number as printed |
| `notification_date` | string | no |  | Notification date, ISO 8601 where it parses, else as printed |
| `as_of` | date | yes | pattern: ^\d{4}-\d{2}-\d{2}$ | Date the chapter was acquired |

## itchs-section-notes

ITC(HS) 2022 section notes (deduplicated across chapters)

Files: `data/itchs/2022/section-notes.csv`

| Field | Type | Required | Constraints | Meaning |
|---|---|---|---|---|
| `section` | string | yes |  |  |
| `section_name` | string | no |  |  |
| `note_type` | string | no |  |  |
| `serial_no` | string | no |  |  |
| `text` | string | yes |  |  |
| `notification_no` | string | no |  |  |
| `notification_date` | string | no |  |  |
| `as_of` | date | yes | pattern: ^\d{4}-\d{2}-\d{2}$ |  |

## list

Official list row (BIS, TEC, BEE)

Files: `data/bee/mandatory.csv`, `data/bee/voluntary.csv`, `data/bis/isi_qco.csv` and 6 more of the same shape

| Field | Type | Required | Constraints | Meaning |
|---|---|---|---|---|
| `product_name` | string | yes |  | Product or item as the official list words it |
| `is_codes` | string | no |  | Indian Standard (IS) codes as printed; blank where the list gives none |
| `scheme` | string | yes |  | Scheme or list the row belongs to |
| `authority` | string | yes |  | Administering authority as printed or inferred from the list page |
| `group` | string | no |  | Section or group title on the source page |
| `source_url` | string | yes | pattern: ^https?:// | URL of the source page or document |
| `retrieved_on` | date | yes | pattern: ^\d{4}-\d{2}-\d{2}$ | Date the source was fetched (or the archive copy was taken) |
| `status` | string | yes | enum: active, upcoming, withdrawn, de-notified, discontinued | Status taken from the source page's own words |
| `notes` | string | no |  | Remaining source text: notification, dates, requirement; verbatim where quoted |

## measures

Measures: one row per (8-digit ITC(HS) code, import-compliance measure)

Files: `data/measures/measures.csv`

| Field | Type | Required | Constraints | Meaning |
|---|---|---|---|---|
| `hs8` | string | yes | pattern: ^\d{8}$ | 8-digit ITC(HS) 2022 code |
| `hs6` | string | yes | pattern: ^\d{6}$ | 6-digit HS prefix (join key to data/hs6) |
| `measure_type` | string | yes | enum: import_policy, policy_condition, bis_isi_qco, bis_crs, bis_scheme_x, bis_upcoming_qco, tec_mtcte, bee_label, import_monitoring, other_condition | import_policy, policy_condition, bis_isi_qco, bis_crs, bis_scheme_x, bis_upcoming_qco, tec_mtcte, bee_label, import_monitoring, other_condition |
| `measure_value` | string | no |  | Free, Restricted, Prohibited or STE for import_policy (blank if the source line has no policy); otherwise the IS number, monitoring system or keyword |
| `condition_text` | string | no |  | Verbatim condition text from the source, HTML stripped |
| `document_code` | string | no |  | Short stable code for the certificate or registration; defined in docs/document-codes.md |
| `legal_ref` | string | no |  | S.O. number, DGFT notification number or list entry as printed; never blank for bis_* types |
| `valid_from` | date | no | pattern: ^\d{4}-\d{2}-\d{2}$ | Notification or enforcement date, when the source gives one |
| `valid_to` | date | no | pattern: ^\d{4}-\d{2}-\d{2}$ | Rescission date; blank means open |
| `status` | string | yes | enum: in_force, upcoming, withdrawn | in_force, upcoming or withdrawn |
| `confidence` | string | yes | enum: official, candidate | official: stated in official text for this code; candidate: keyword match, not a determination |
| `basis` | string | yes |  | How the row was derived (row condition, chapter condition N, candidate: keyword ...) |
| `qco_slug` | string | no |  | Key into data/qco/register.csv when the measure is tied to a QCO register record |
| `source_file` | string | yes |  | Repository file(s) the row was derived from, semicolon-separated |
| `source_sha256` | string | yes |  | SHA-256 of each source_file as published here, same order, semicolon-separated |
| `as_of` | date | yes | pattern: ^\d{4}-\d{2}-\d{2}$ | Date the ITC(HS) source was retrieved |
| `is_title` | string | no |  | Title of the standard named in measure_value, from data/is-standards (BIS Know Your Standards, latest edition); blank when not joined |
| `is_status` | string | no | enum: current, withdrawn, superseded, unknown | current, withdrawn, superseded or unknown, as the BIS portal result list shows it; a data-quality signal only, never a change to this measure's own status |
| `is_superseded_by` | string | no |  | The IS number the portal names as superseding it, when is_status is superseded or withdrawn |

## provenance

Provenance of a published CSV

Files: `data/bee/PROVENANCE.csv`, `data/bis/PROVENANCE.csv`, `data/hs-links/PROVENANCE.csv` and 4 more of the same shape

| Field | Type | Required | Constraints | Meaning |
|---|---|---|---|---|
| `file` | string | yes |  |  |
| `source_url` | string | yes |  |  |
| `retrieved_on` | date | yes | pattern: ^\d{4}-\d{2}-\d{2}$ |  |
| `sha256` | string | yes | pattern: ^[0-9a-f]{64}$ | sha256 of the published CSV |
| `rows` | integer | yes |  |  |
| `source_rows` | integer | no |  | Rows the source itself counts; equals rows |
| `page_date` | string | no |  | "Last updated" date the page prints, if any |
| `parser` | string | no |  |  |
| `raw_file` | string | no |  | Path of the archived raw copy |
| `raw_sha256` | string | no |  | sha256 of the raw copy |
| `raw_bytes` | integer | no |  |  |
| `raw_committed` | string | no |  |  |
| `fetch_method` | string | no |  | direct, or alterlab when the origin refused the direct fetch; empty on rows written before this column existed |
| `fetch_tier` | string | no |  | scraping tier used by the fallback; empty for a direct fetch |
| `fetch_cost_usd` | number | no |  | cost of the fallback fetch in US dollars; empty for a direct fetch |

Primary key: `file`

## qco-events

QCO events (notification, amendment, extension, rescission) read from the order text

Files: `data/qco/events.csv`

| Field | Type | Required | Constraints | Meaning |
|---|---|---|---|---|
| `slug` | string | yes |  |  |
| `seq` | integer | yes |  |  |
| `date` | string | no | pattern: ^\d{4}-\d{2}-\d{2}$ |  |
| `kind` | string | yes | enum: notified, amended, extended, rescinded, superseded, exemption, enforcement, order |  |
| `text` | string | yes |  |  |
| `source_file` | string | no |  |  |
| `source_row` | integer | no |  |  |
| `source_url` | string | no |  |  |
| `retrieved_on` | date | yes | pattern: ^\d{4}-\d{2}-\d{2}$ |  |

Primary key: `slug`, `seq`

## qco-gazette-hashes

SHA-256 of each Gazette PDF the register links to (the PDFs are not stored)

Files: `data/qco/gazette-pdf-hashes.csv`

| Field | Type | Required | Constraints | Meaning |
|---|---|---|---|---|
| `source_url` | string | yes | pattern: ^https?:// |  |
| `sha256` | string | no | pattern: ^[0-9a-f]{64}$ |  |
| `retrieved_on` | string | no | pattern: ^\d{4}-\d{2}-\d{2}$ |  |
| `status` | string | yes |  |  |

Primary key: `source_url`

## qco-products

Products covered by each QCO record

Files: `data/qco/products.csv`

| Field | Type | Required | Constraints | Meaning |
|---|---|---|---|---|
| `slug` | string | yes |  |  |
| `product_name` | string | yes |  |  |
| `is_codes` | string | no |  |  |
| `status` | string | yes |  |  |
| `sector` | string | no |  |  |
| `enforcement_date` | string | no | pattern: ^\d{4}-\d{2}-\d{2}$ |  |
| `source_file` | string | no |  |  |
| `source_row` | integer | no |  |  |

## qco-register

QCO register: one record per Quality Control Order (or list)

Files: `data/qco/register.csv`

| Field | Type | Required | Constraints | Meaning |
|---|---|---|---|---|
| `slug` | string | yes |  |  |
| `list` | string | yes | enum: isi_qco, qco_upcoming, crs |  |
| `list_serial` | string | no |  |  |
| `title` | string | yes |  |  |
| `ministry` | string | no |  |  |
| `sector` | string | no |  |  |
| `state` | string | yes | enum: in_force, notified, withdrawn, de_notified |  |
| `extended` | boolean | yes |  |  |
| `rescinded` | boolean | yes |  |  |
| `is_codes` | string | no |  |  |
| `history_truncated` | boolean | yes |  |  |
| `product_count` | integer | yes |  |  |
| `first_date` | string | no | pattern: ^\d{4}-\d{2}-\d{2}$ |  |
| `latest_date` | string | no | pattern: ^\d{4}-\d{2}-\d{2}$ |  |
| `source_file` | string | no |  |  |
| `source_url` | string | yes |  |  |
| `retrieved_on` | date | yes | pattern: ^\d{4}-\d{2}-\d{2}$ |  |
| `source_rows` | string | no |  |  |
| `pdf_urls` | string | no |  | Gazette PDF URLs, " ; " separated |
| `gazette_pdf_sha256` | string | no |  | sha256 of each Gazette PDF, " ; " separated, aligned with pdf_urls; empty where the file could not be fetched |

Primary key: `slug`

## steel-qco-hs-columns

HS codes printed in the HS column of the three 2020 Steel QCO gazette PDFs

Files: `data/hs-links/steel-qco-hs-columns.csv`

| Field | Type | Required | Constraints | Meaning |
|---|---|---|---|---|
| `hs_code` | string | yes | pattern: ^\d{8}$ | 8-digit code as printed |
| `qco_slug` | string | yes |  | Key into data/qco/register.csv |
| `so_number` | string | yes |  | S.O. number of the order the PDF carries |
| `order_date` | date | yes | pattern: ^\d{4}-\d{2}-\d{2}$ |  |
| `pages` | string | yes |  | PDF pages where the code is printed, semicolon-separated |
| `source_url` | string | yes |  |  |
| `raw_sha256` | string | yes | pattern: ^[0-9a-f]{64}$ | SHA-256 of the PDF |
