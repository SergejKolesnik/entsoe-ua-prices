# Ukraine Energy Market Forecast

[Open RDN Market Intelligence](https://rdn-market-intelligence-ua-v2.streamlit.app/)

Independent Python foundation for collecting and validating Ukrainian day-ahead electricity-market data.

The project is intentionally separate from SkyGrid Solar. It provides source adapters, normalized domain models, raw artifact landing, SQLite persistence, settlement-period validation, and an independent Streamlit dashboard. Forecasting is not activated yet.

## Current capabilities

- Discover official Market Operator DAM results for a requested delivery date.
- Build the official Excel download URL only from a validated `hdata_link`.
- Fetch ENTSO-E Transparency Platform documents with explicit query parameters.
- Parse ENTSO-E price XML using interval timestamps and resolution.
- Reject duplicate, missing, overlapping, naive, or inconsistent hourly observations.
- Test 23-, 24-, and 25-period trading days without inventing missing values.
- Store immutable raw responses by SHA-256 and normalized prices idempotently in SQLite.
- Parse official Market Operator legacy XLS workbooks using their verified hourly layout.
- Explore stored prices in a dark Streamlit dashboard with five decision-oriented tabs: overview, trends, price drivers, forecast, and neighboring markets. Calendar-aligned year-over-year seasonality and the weekly heatmap live under Trends; quality and forecast monitoring remain available through an optional Technical status tab.

## Setup

Python 3.11+ is recommended.

```bash
python -m venv .venv
python -m pip install -r requirements.txt
```

Local `.env` example:

```env
ENTSOE_TOKEN=replace_with_new_token
```

The previous token was exposed in public Git history and must not be reused.

## Checks

PowerShell:

```powershell
$env:PYTHONPATH = "src"
python -m unittest discover -s tests -v
python -m compileall -q src tests
python -m market_forecast.cli --help
python -m market_forecast.cli init-db
```

One-day collection examples:

```powershell
python -m market_forecast.cli collect --source operator --date 2026-08-18
python -m market_forecast.cli collect --source entsoe --date 2026-08-18 --bidding-zone <EIC_CODE>
```

The ENTSO-E bidding-zone EIC is intentionally explicit; the application does not guess a market area. Repeating a collection does not duplicate normalized price rows, and byte-identical raw responses share one content-addressed file.

Despite the `downloadxlsx` endpoint name, the Market Operator currently returns a legacy OLE `.xls` file. The parser uses tolerant workbook loading because the generated container has a malformed sector chain, then validates the real hourly row count and localized price values before persistence.

Controlled historical collection and coverage reporting:

```powershell
python -m market_forecast.cli backfill --source operator --from 2026-08-01 --to 2026-08-18
python -m market_forecast.cli quality --source operator --from 2026-08-01 --to 2026-08-18
python -m market_forecast.cli quality --source operator --from 2026-08-01 --to 2026-08-18 --format json
```

Backfill is sequential, waits 0.5 seconds between requests by default, records each day as `collected`, `unpublished`, or `failed`, and refuses ranges above 366 days unless the safety limit is explicitly changed. Quality reporting exits non-zero when any requested delivery day is incomplete.

## Dashboard

Collect a historical range first, then start the local application:

```powershell
python -m market_forecast.cli backfill --source operator --from 2026-07-19 --to 2026-08-18
python -m streamlit run streamlit_app.py
```

Streamlit prints the local browser address, normally `http://localhost:8501`. The dashboard reads `data/market_forecast.sqlite3` by default and does not contact or modify SkyGrid Solar. When `DATABASE_URL` is configured, the dashboard and collectors use the dedicated Neon PostgreSQL database instead. Its **Прогноз** tab shows a transparent one-step baseline for the first delivery day after the latest published DAM prices.

The public Streamlit Community Cloud deployment is visited every six hours by
`.github/workflows/keep-streamlit-awake.yml`. The workflow also verifies the
Streamlit health endpoint and fails visibly if the app cannot be reached. It can
be started manually from GitHub Actions when an immediate wake-up check is needed.

`DATABASE_URL` is a secret. Configure it only in the Windows user environment, GitHub Actions secrets, or Streamlit secrets; never commit it to Git. SQLite remains the automatic local fallback when the variable is absent.

The one-time `scripts/migrate_sqlite_to_postgres.py` command defaults to a read-only plan. Its `--apply` mode refuses a non-empty destination, copies everything in one transaction, and verifies row counts and relationships before committing. If `DATABASE_URL` is absent, it requests the connection string through hidden terminal input.

The baseline is selected only by chronological walk-forward results. It compares the median of up to four prior matching weekdays against the previous-day hourly profile, uses no observation from or after a historical forecast cutoff, and displays the lower-MAE method. The uncertainty band is the 80th percentile of historical absolute errors, not a guaranteed confidence interval. This is an auditable research baseline rather than a claim of production-grade accuracy.

## Automatic daily refresh

The dashboard never downloads market data merely because somebody opened the page. A separate idempotent command requests tomorrow's Kyiv delivery day and records every outcome for the UI:

```powershell
python refresh_operator.py
```

On Windows, install the prepared Task Scheduler job from PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\install_windows_refresh_task.ps1
```

The installer creates two independent tasks. The Ukrainian Operator task runs at 14:15, 15:00, 16:00, and 17:00. A market-context task runs at 17:20 and refreshes the current Kyiv-aligned neighbor-price day, official NBU EUR rates, yesterday's completed border flows, and recent Operator volumes. Keeping them separate prevents an ENTSO-E failure from blocking the operational Ukrainian refresh.

Keep Windows configured for the Kyiv timezone. If the computer is off, `StartWhenAvailable` runs a missed task after startup. Collection outcomes are persisted per source; failures store only the exception type, never a response URL or token. Repeated successful runs are safe and do not duplicate records. The context task requires `ENTSOE_TOKEN` in the Windows user environment.

For the published dashboard, `.github/workflows/refresh-market-data.yml` runs the same finite jobs in GitHub Actions. It requests the Ukrainian DAM at 14:15, 15:00, 16:00, and 17:00, then refreshes market context at 17:20 in the `Europe/Kyiv` timezone. Scheduled workflows run only from GitHub's default branch and require repository secrets named `DATABASE_URL` and `ENTSOE_TOKEN`. The workflow can also be started manually for `operator`, `context`, or `all` without exposing either secret in logs.

After every successful refresh, the same finite job also freezes the first still-unknown delivery day as an immutable `baseline-v1` snapshot. Manual snapshot generation is available for diagnostics:

```powershell
$env:PYTHONPATH = "src"
python -m market_forecast.cli snapshot-baseline
```

The **Моніторинг** tab first shows freshness for the Ukrainian DAM, NBU rate, Operator volumes, four neighbor-price feeds, and four bidirectional border-flow groups. It then compares each frozen hourly vintage with facts only after they arrive, showing forecast coverage, observed MAE/RMSE, the original P80 band, and a permanent run journal. Repeated scheduler attempts return the existing identical snapshot; they never rewrite a forecast after the fact.

Scheduled Operator failures are stored as sanitized categories. Immutable price, volume, and source-revision conflicts are reported separately as `ValueError:price_conflict`, `ValueError:volume_conflict`, and `ValueError:source_revision_conflict`; invalid artifacts and other validation failures use separate categories. Raw exception messages, source payloads, prices, and connection details are never written to the monitoring journal.

An explicit read-only comparison can identify the affected Kyiv hours and field names without printing either the stored or newly published values:

```bash
python -m market_forecast.cli diagnose-operator-conflict --date 2026-08-25
```

GitHub Actions exposes the same operation as `Refresh market data` → `diagnose_operator` with an explicit `delivery_date`. This diagnostic performs no database writes and does not persist the downloaded workbook.

The **Фактори ціни** tab is a transparent diagnostic, not a causal model. It compares the selected day with the latest earlier observed day and with the mean of up to seven earlier available days, then separates night, morning, solar hours, evening peak, and late evening. A short Ukrainian summary ranks the largest time-of-day deviation and lists only observed co-movements: DAM volume, neighboring-market prices, and fully covered cross-border flows. The hourly chart overlays both price days with selected-day net imports only when every configured border and direction is complete. Weather, generation availability, and load remain explicitly marked as hypotheses until their decision-time vintages can be selected without future-data leakage.

The context refresh also collects an immutable three-day Open-Meteo forecast vintage for Kyiv, Lviv, Vinnytsia, Odesa, Dnipro, and Kharkiv. Each hourly row preserves its collection vintage, valid time, temperature, cloud cover, shortwave radiation, and 100-metre wind speed. These points are not yet assigned market weights; doing so without measured generation and demand coverage would create false precision. PostgreSQL deployments must apply `migrations/002_weather_forecasts.sql` before enabling this collector.

## Neighboring EU markets

The **Сусідні ринки** tab is prepared for Poland, Slovakia, Hungary, and Romania using their verified ENTSO-E bidding-zone identities. Configure a newly issued personal token, then run a controlled backfill:

```powershell
$env:ENTSOE_TOKEN = "new-token"
python -m market_forecast.cli backfill-neighbors --market all --from 2025-08-19 --to 2026-08-20
```

Load official NBU EUR rates and directed ENTSO-E physical flows for the same period:

```powershell
python -m market_forecast.cli backfill-fx --from 2025-08-19 --to 2026-08-20
python -m market_forecast.cli backfill-flows --market all --from 2025-08-19 --to 2026-08-20
python -m market_forecast.cli enrich-operator-volumes
```

The comparison tab converts the Ukrainian DAM price to EUR only for analytics; the stored
Operator Market price remains in UAH. Physical flows are stored as directed average MW and
converted to MWh using each record's actual interval duration. The Operator workbook's
accepted sale volume is stored in `volume_mwh` only after validating that accepted purchase
and sale volumes are equal.
Days with incomplete physical-flow coverage on any configured border or direction are
explicitly excluded from aggregate import/export and price-flow correlation metrics.

Individual market codes are `PL`, `SK`, `HU`, and `RO`. Each market keeps one stable color in the selector, daily trend, and hourly charts. The UI shows the two latest common hourly price days when the selected Ukrainian day is newer than the available neighbor publications. It also shows the latest complete hourly border-flow profile with import above zero, export below zero, and net import as a line; Polish quarter-hour flows are summed into hourly energy. ENTSO-E raw documents remain immutable and normalized rows remain isolated by bidding zone. Since European SDAC moved to a 15-minute market time unit for delivery from 1 October 2025, the parser accepts validated 15/30/60-minute intervals; the UI averages complete sub-hourly price groups into aligned UTC hours for comparison with Ukraine. See the official [ENTSO-E SDAC implementation timeline](https://www.entsoe.eu/network_codes/cacm/implementation/sdac/) and [Transparency Platform extraction guide](https://transparency.entsoe.eu/content/static_content/download?path=%2FStatic+content%2Fweb+api%2FIG-for-TP-data-extraction-process.pdf).

Neighbor prices remain in EUR/MWh. The Ukrainian curve and cross-border spread are intentionally not converted until an effective-dated official NBU exchange-rate source is implemented. Moldova is also excluded from this first adapter because a stable ENTSO-E day-ahead bidding-zone price feed has not yet been verified.

## Read-only JSON for Hermes

Hermes must not receive `DATABASE_URL` and must not scrape Streamlit. The additive
`export-hermes-report` command reads the established repository API and writes a
sanitized schema-versioned JSON document:

```powershell
$env:PYTHONPATH = "src"
python -m market_forecast.cli export-hermes-report `
  --date 2026-08-22 `
  --output data\exports\2026-08-22.json
```

Omit `--date` to export the latest stored Ukrainian delivery day. Exit code `0`
means the Ukrainian day is complete; exit code `2` means the file was still
written but its status is `incomplete`, `unavailable`, or `stale`. Missing values
remain JSON `null` and are never replaced with zero.

The `Publish Hermes report JSON` workflow runs after the daily context window and
publishes two files to the dedicated `hermes-report` branch:

- `latest.json` for the current consumer;
- `v1/YYYY-MM-DD/<generated-at>.json` as an immutable dated snapshot.

The repository and source market data are public, so this export is intentionally
public and contains no secrets, source URLs, database identifiers, raw errors, or
private metadata. GitHub's static file service supplies CDN/anti-abuse controls;
Hermes should fetch once per daily report, not poll continuously. If the repository
is made private later, use a fine-grained GitHub token with read-only Contents
permission instead of changing the database design.

After the workflow has published once, Hermes should read:

```text
https://raw.githubusercontent.com/SergejKolesnik/entsoe-ua-prices/hermes-report/latest.json
```

Hermes must reject unknown `schema_version` values, require `status == "complete"`
for confident numeric commentary, verify `delivery_date`, and treat every context
section according to its own `status`. Full field semantics are documented in
`docs/hermes-report-contract.md`.

## Data-source responsibilities

- `OperatorMarketSource` discovers published results and returns raw source metadata.
- `EntsoeSource` downloads raw XML and does not parse or persist it.
- `parse_price_document` converts ENTSO-E XML to immutable hourly records.
- `validate_delivery_periods` verifies completeness and continuity.
- `RawArtifactStore` preserves source bytes under a content hash.
- `SQLiteMarketRepository` owns the established transactional and idempotent contract.
- `PostgresMarketRepository` provides the same contract for the dedicated Neon database.

No source adapter writes files or database rows; application services coordinate those side effects.

## Research reference

`docs/references/RDN_Deep_Analysis_and_Forecast_UA.pdf` documents prior monthly analysis for 2019-2025 with an external 2026 check. Its strongest result is negative but valuable: on the monthly dataset, more complex lagged-factor models did not beat the persistence baseline. We therefore use the report to define hypotheses and validation constraints, not as proof that a production hourly model will work.

The engineering interpretation and reproducibility limits are recorded in `docs/references/README.md`.

## Repository history

The original prototype fetched ENTSO-E or data.gov.ua data directly from one `main.py` and appended a tracked CSV. That implementation is retained in Git history and tagged as `prototype-v0`; it is not part of the new runtime.
