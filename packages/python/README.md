# india-import-compliance (Python)

Offline lookup over the tables of [india-import-compliance-data](https://github.com/yashodhank/india-import-compliance-data). No dependencies; the data (`all.csv`, `measures.csv`) is bundled. Not legal advice: every row carries an `as_of` date, and the official source prevails.

    pip install "git+https://github.com/yashodhank/india-import-compliance-data.git#subdirectory=packages/python"

Not yet on PyPI. The installed version is the repository's release tag (`india_import_compliance.__version__`, for example `2026.10.22.1643`; a checkout past a tag shows `.postN`).

```python
from india_import_compliance import lookup, measures, search

lookup("8517.13.00")      # the ITC(HS) line (dict) or None; accepts 4, 6 or 8 digits, dots and spaces ignored
measures("85171300")      # list of measure dicts; for a 4 or 6 digit prefix, every measure beneath it
search("smartphone")      # 8-digit lines whose description contains every word, best first
```
