# Corrections

If a row is wrong, stale or missing, tell us. This is a small, volunteer-run dataset and no response time is promised.

## How to report

- A wrong or missing value: open an issue with the **Data correction** form.
- An official page or list that moved, changed layout or was replaced: use the **Source change** form.
- Always give the file, the key (HS code, IS code or product name) and a link to the official page or Gazette that shows the right value.

## What happens

1. The report is checked against the official source, not against another third-party copy.
2. If the data is wrong because of this repository's parser, the parser or its test is fixed and the file is rebuilt. Files under `data/` are generated, so they are never edited by hand.
3. If the official source itself is wrong or unclear, the row is left as published and the issue is recorded in `DATA-QUALITY.md`.
4. A change that alters published rows goes out as a new release with an entry in `CHANGELOG.md` that names the correction. A release that was wrong is marked as such in the changelog; it is not deleted.

## Not accepted

Requests to give advice on a particular import, to reword official text, or to remove a row because it is inconvenient. Confirm any decision with the issuing authority.
