# NYC vice map

Interactive map of every licensed liquor store, legal cannabis dispensary, and tobacco / e-cigarette retailer in the five boroughs of New York City. Built from regulator-maintained license rolls; rebuilt weekly.

**Live site:** https://vitalcity-nyc.github.io/nyc-vice-map/

## Sources

| Category | Agency | Dataset |
|---|---|---|
| Liquor stores | NYS Liquor Authority | [9s3h-dpkz](https://data.ny.gov/d/9s3h-dpkz) |
| Legal cannabis | NYS Office of Cannabis Management | [jskf-tt3q](https://data.ny.gov/d/jskf-tt3q) |
| Tobacco / vape | NYC Dept of Consumer and Worker Protection | [w7w3-xahh](https://data.cityofnewyork.us/d/w7w3-xahh) |

Geocoding via NYC Department of City Planning [GeoSearch](https://geosearch.planninglabs.nyc/).

See [methodology](docs/methodology.html) for filters, limitations, and what is *not* included.

## Build

```bash
python3 scripts/build_data.py
```

No dependencies beyond the Python 3 standard library. First run takes ~10 minutes (geocoding is the slow part); subsequent runs are fast because GeoSearch results are cached in `data/geocache.json`.

Outputs land in `docs/data/`:
- `locations.geojson` — every mapped point
- `locations.csv` — every record (including any that failed to geocode)
- `methodology.json` — refresh date, row counts, source filters

## Layout

```
nyc-vice-map/
├── docs/                       # GitHub Pages root
│   ├── index.html              # map + table
│   ├── methodology.html
│   ├── assets/{app.js,styles.css}
│   └── data/{*.geojson,*.csv,methodology.json}
├── scripts/build_data.py
├── data/
│   ├── raw/                    # untracked working files
│   └── geocache.json           # GeoSearch cache (committed)
└── .github/workflows/refresh.yml  # weekly cron
```

## License

Data: each agency's published terms. Code: MIT.
