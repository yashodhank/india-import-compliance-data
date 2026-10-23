# Security policy

## Reporting

Report a vulnerability privately: use **Security > Report a vulnerability** on the repository page (GitHub private vulnerability reporting). Do not open a public issue for it. This is a small, volunteer-run project and no response time is promised.

## In scope

- The pipeline code (`pipeline/`), the workflows (`.github/workflows/`) and the packages (`packages/`): for example a way to make a refresh write unverified data, leak the repository's secrets, or run attacker-supplied code.
- The published site (GitHub Pages) and the release assets: for example a file that does not match the hash recorded in `PROVENANCE.csv`.
- A secret committed to the repository or its history.

## Out of scope

- A wrong or stale row in a table: that is a data correction, use the **Data correction** issue form (see `CORRECTIONS.md`).
- A change on an official source page: use the **Source change** form.
- Findings about the government sites the data comes from, and denial of service by high-volume use of GitHub itself.

## Supported versions

Only the latest release and `main`. Earlier releases are kept for the record and are not patched; `CHANGELOG.md` marks releases that were wrong.

## What the project does not hold

No user accounts, no personal data and no service: the site is static files. The only secret the refresh workflow can use is an optional fetch-fallback API key, stored as a repository secret and never written to a log or a file.
