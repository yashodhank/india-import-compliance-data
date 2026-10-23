# Contributing

## Report a data error

Open an issue with the **Data correction** form. Give:

1. the file and the row key (HS code, IS code or product name);
2. what the file says and what it should say;
3. a link to the **official page or Gazette notification** that shows the right value. A third-party copy is not evidence.

If an official page moved, changed layout or was replaced, use the **Source change** form. What happens next is in `CORRECTIONS.md`.

## How a refresh works

Files under `data/` are generated; never edit them by hand. A correction is made in the parser (`pipeline/`) or in an archived input, and the files are rebuilt.

- Weekly (Monday 02:00 IST) and whenever the 6-hourly monitor sees a source page change, the `refresh` workflow fetches the sources, archives the bytes under `raw/`, parses, asserts that each parsed row count equals the source's own count, and runs the tests. If everything passes it commits, adds a `CHANGELOG.md` entry and publishes a release; otherwise it opens or updates an issue and publishes nothing.
- ITC(HS) and the TEC MTCTE list are refreshed from an operator machine, not the runner: see "Freshness" in `README.md`.
- Locally: `python -m pipeline.refresh --offline` rebuilds everything from the archived raw copies with no network; `python -m pytest tests` runs the golden, schema and pipeline tests. Python 3.12, standard library only for the pipeline; `pdftohtml` (poppler) for the two PDF lists; `pip install -r requirements-dev.txt` for the tests.

## Pull requests

- One logical change per commit; say what changed in the data (counts) and name the official instrument.
- Never add a standard's text, a Gazette PDF over the size limit, or a source whose `robots.txt` disallows fetching.
- Docs that quote a count or a date are checked by `tests/test_public_face.py`; regenerate `docs/data-dictionary.md` with `python docs/build_data_dictionary.py` when a schema changes.
- By contributing you agree your contribution is licensed as the repository is: CC BY 4.0 for data, MIT for code.

Conduct: `CODE_OF_CONDUCT.md`. Security: `SECURITY.md`.
