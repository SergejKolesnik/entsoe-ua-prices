# Annual gas consumption history

The `2023` source is a verified annual worksheet with twelve monthly rows.
It is not compatible with the daily procurement sheet contract: it contains
VAT-inclusive prices, transportation and distribution charges, actual plant and
sanatorium volumes in thousands of cubic metres, and billed amounts. It has no
daily series or planned volumes. The user confirmed the small sanatorium and
December quantities; the importer must preserve them without heuristic corrections.

## Import and storage

`import-gas-year` accepts the explicitly versioned annual CSV layout, including
the verified Google gviz variant that collapses the title into the header.
It checks the year, labels/units/VAT, all twelve ordered months, price components,
volume components, billed amounts and annual totals. Missing is never zero.
Volumes alone are multiplied by 1,000 to obtain m3; prices remain VAT-inclusive
UAH/1000m3. The monthly amount tolerance is one kopeck; the annual amount tolerance
is six kopecks to allow twelve displayed monthly amounts rounded to cents.

Raw CSV is saved to the existing content-addressed `data/raw` store before parsing.
The new `gas_monthly_history` table retains all source components, the source URL,
sheet name, SHA256 and import timestamp. It does not mutate the existing
`gas_procurement_months` or `gas_consumption_days` records. PostgreSQL shares the
existing repository adapter; migration 004 adds only the new table.

The whole year's insert is transactional. Repeating identical normalized values
inserts zero rows. A conflicting existing month aborts the whole batch; there is
no silent overwrite or broad delete. Raw artifacts and local preview databases
remain ignored by Git and are not synchronized to another device.

```powershell
$env:PYTHONPATH='src'
$env:GAS_SPREADSHEET_ID='<the existing source spreadsheet id>'
python -m market_forecast.cli import-gas-year --year 2023 --sheet 2023
# Only after reviewing validation and choosing the intended database:
python -m market_forecast.cli import-gas-year --year 2023 --sheet 2023 --write
```

Without `--write`, no repository or database connection is created. SQLite uses
`DATABASE_PATH`; PostgreSQL uses `DATABASE_URL`. Do not expose these credentials
in logs. Apply `migrations/004_gas_monthly_history.sql` to the intended PostgreSQL
branch before running the writer or deploying the updated UI.

## Consumption presentation

The gas tab adds a monthly stacked chart and a table for plant and sanatorium
consumption. Confirmed monthly facts take precedence over overlapping daily
records, so the same consumption is never counted twice. Other months sum only
known plant daily values and are explicitly labelled complete or incomplete.
Unknown sanatorium quantities remain missing. No combined total is claimed for
plant-only daily sources. A month with no known daily actuals stays missing.

The selector includes historical months even without procurement-price records.
For a month with annual-sheet history and no daily data, the UI shows exact
monthly plant, sanatorium and total metrics, and explains that daily details and
plans are unavailable. Source prices are retained in storage but are not merged
into existing VAT-exclusive price charts. Those charts and daily collectors keep
their existing behavior.

## Verification and rollout boundary

- Live annual CSV validated as twelve monthly records; verified locally with an
  initial insert of twelve rows and an idempotent repeat of zero rows.
- Regression coverage includes malformed units/VAT, missing/duplicate months,
  component arithmetic, atomic rollback, overlap precedence, missing versus zero,
  leap-year daily completeness and Streamlit history-only month selection.
- The feature branch's full suite passed 127 tests, and compile checks passed for
  `src`, `tests` and `streamlit_app.py`. Streamlit AppTest passed; browser-based
  visual inspection was blocked by browser permission policy.
- Development Neon branch: `gas-2023-history-review` (`br-bitter-sea-ar9b9iv6`),
  project `aged-brook-00523142`, copied from `br-spring-cloud-arwg23j6`.
- After access was restored, migration 004 and all twelve records were validated
  on the development branch. The real PostgreSQL repository adapter verified an
  idempotent repeat and rejection of conflicting values. Streamlit AppTest against
  that branch verified the 2023 overview and December monthly metrics alongside
  the existing procurement/daily data.
- Migration 004 and the twelve verified 2023 records were then committed in one
  transaction on production branch `br-spring-cloud-arwg23j6`. Readback confirmed
  complete January–December coverage and source totals. Existing procurement and
  daily tables retained their 29 and 881 records respectively.
- Next: review the feature PR and publish/merge code only after the user's separate
  release confirmation. Production already contains the additive history table;
  the older deployed UI does not query it until the new code is published.
