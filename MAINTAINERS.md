# Maintainers

Maintained by Yashodhan Kulkarni ([@yashodhank](https://github.com/yashodhank)). Corrections: see `CORRECTIONS.md`.

## What maintenance means

The weekly workflow refreshes every list; the 6-hourly monitor starts a refresh when a source page changes. A person is needed only when a run fails (a layout change, a refused host, a count mismatch) and an issue is opened.

## Kill criteria

This repository is **archived** when either of these is true:

- maintenance exceeds the automation, meaning the failures need human repair more often than the pipeline saves work; or
- the issuing authority publishes an equivalent machine-readable dataset. In that case this repository becomes a **history mirror**: no further refreshes, the last release and the archived `raw/` copies stay available, and the README points to the official dataset.

Archiving is announced in the README and in `CHANGELOG.md` before the workflows are disabled.

## Succession

Anyone may fork under the licences in the README. A fork that wants to continue the data lineage should keep `PROVENANCE.csv` and the `raw/` hashes intact.
