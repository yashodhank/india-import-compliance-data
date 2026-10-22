# india-import-compliance (Node)

Offline lookup over the tables of [india-import-compliance-data](https://github.com/yashodhank/india-import-compliance-data). No dependencies; ESM and CommonJS; the data (`all.csv`, `measures.csv`) is bundled. Not legal advice: every row carries an `as_of` date, and the official source prevails.

The package lives in a subdirectory, and npm cannot install a subdirectory of a git repository, so `npm install github:yashodhank/india-import-compliance-data` would not give you this package. Clone and install the folder:

    git clone --depth 1 https://github.com/yashodhank/india-import-compliance-data.git
    npm install ./india-import-compliance-data/packages/node

```js
import { lookup, measures, search } from 'india-import-compliance';   // or: const { lookup } = require('india-import-compliance')

lookup('8517.13.00');   // the ITC(HS) line (object) or null; 4, 6 or 8 digits
measures('85171300');   // array of measures; a 4 or 6 digit prefix returns every measure beneath it
search('smartphone');   // 8-digit lines whose description contains every word, best first
```
