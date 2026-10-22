# Data quality: known gaps

Honest list. Open an issue if you find another.

## Not in this repository yet

- ITC(HS) 2017 edition and DGFT notifications since 2022 (the 2022 export carries a notification number and date per line, but not the notification texts).
- CBIC customs instructions index.
- Export policy (Schedule 2); only the import policy is published.
- EPR producer lists: the issuing portal's `robots.txt` disallows fetching, so they are not published.
- CDSCO and FSSAI customs-tariff-heading lists, and any WPC list (there is no published list to parse).
- Gazette PDFs themselves (large). The QCO register links to them and records their SHA-256.

## ITC(HS) 2022

- Source of truth is the DGFT web app export, taken on 2026-10-22. It can lag or differ from the Gazette; for legal effect use the Gazette.
- Only 8-digit lines are import-policy leaves, but the export also lists 4 and 6-digit heading lines (`level` column). 59 of the 12,587 8-digit lines have a blank policy in the export.
- The export lists 17 codes twice (e.g. `85241290`, `85249910`); both lines are kept and reported in `BUILD-REPORT.json`.
- About 1,359 8-digit lines carry a substantive condition text; the rest are blank or a placeholder such as `.` or `-` (kept verbatim).
- `condition_text` is the export's HTML with tags removed and whitespace collapsed; a doubly encoded no-break space is read as a space. The words are otherwise unchanged, including the source's spelling errors.
- `condition_ref` is extracted by pattern from the text ("Policy Condition 3 ...") and can miss unusual wording.
- Policy values are as exported: `Free`, `Restricted`, `Prohibited`, two spellings of State Trading Enterprise, and 5 lines marked `Free*`.
- Notification dates arrive in three formats; they are normalised to ISO 8601 where they parse (2 values hold two dates and are kept as printed).

## BIS, TEC, BEE lists

- Releases before v2026.10.23 under-counted Scheme I (710 rows instead of 799): a rowspan layout was misread. Do not cite the earlier Scheme-I counts. Since v2026.10.23 the expected count is taken from the page's `<tr>` rows independently of the row builder.

- Statuses (`active`, `withdrawn`, `de-notified`, `upcoming`) are read from the page's own words (section titles, "Withdrawal of", "Rescind"); nothing is computed from today's date.
- The BIS Option-2 PDF has gaps in its own serial numbers (403, 468, 515 are absent in the source); no row is invented.
- The BEE pages give no IS codes. The MTCTE list uses TEC essential requirements, not IS codes.
- Tables are keyed on IS code plus product name, never on the serial, because a serial-keyed scraper once dropped a row that shared a serial cell.
- Layout changes on a source page make the parser fail loudly (the run stops and an issue is opened); they do not produce a partial list.

## QCO register

- Built by reading the QCO text on the BIS Scheme-I page: events are stretches of text that end in a printed date; the kind (notified, amended, extended, rescinded, superseded) comes from words in that stretch only. Treat it as a reading aid, not a legal chronology.
- 31 of the 316 linked Gazette PDFs could not be fetched when hashed (`status` in `data/qco/gazette-pdf-hashes.csv`); their hash is blank.
- The Scheme-I page does not state the administering ministry, so `ministry` is blank for those records.

## Derived candidates

- A keyword match, in capitals for acronyms. It will miss a rule that is described in other words, and it can match a text that mentions a scheme without imposing it. Use it to find where to look.

## Live fetching

- The weekly workflow fetches with a user agent that names this repository. The first live run of each adapter is the real test that a host accepts that agent; a refused or changed page stops the run and opens an issue.

- A page or PDF fetched through the paid fallback is recorded in `PROVENANCE.csv` (`fetch_method`). A PDF obtained that way is extracted text, not the original bytes, and is never archived as the raw copy; only the origin and the Internet Archive give verbatim PDFs.
