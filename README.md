# Ukraine Energy Market Forecast

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
- Explore stored prices in a dark Streamlit dashboard with daily metrics, hourly profiles, history, a calendar heatmap, and data-quality reporting.

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

Streamlit prints the local browser address, normally `http://localhost:8501`. The dashboard reads `data/market_forecast.sqlite3` and does not contact or modify SkyGrid Solar. Its **Прогноз** tab shows a transparent one-step baseline for the first delivery day after the latest published DAM prices.

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

The task runs at 14:15, 15:00, 16:00, and 17:00 in the computer's local timezone. Keep Windows configured for the Kyiv timezone. If the computer is off, `StartWhenAvailable` runs the missed task after startup. Each attempt is shown in the dashboard as current, unpublished, or failed; failures store only the exception type, never a response URL or token. Repeated successful runs are safe and do not duplicate hourly prices.

After every successful refresh, the same finite job also freezes the first still-unknown delivery day as an immutable `baseline-v1` snapshot. Manual snapshot generation is available for diagnostics:

```powershell
$env:PYTHONPATH = "src"
python -m market_forecast.cli snapshot-baseline
```

The **Моніторинг** tab compares each frozen hourly vintage with facts only after they arrive. It shows forecast coverage, observed MAE/RMSE, the original P80 band, and a permanent run journal. Repeated scheduler attempts return the existing identical snapshot; they never rewrite a forecast after the fact.

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
```

The comparison tab converts the Ukrainian DAM price to EUR only for analytics; the stored
Operator Market price remains in UAH. Physical flows are stored as directed average MW and
converted to MWh using each record's actual interval duration. The Operator workbook's
accepted sale volume is stored in `volume_mwh` only after validating that accepted purchase
and sale volumes are equal.

Individual market codes are `PL`, `SK`, `HU`, and `RO`. ENTSO-E raw documents remain immutable and normalized rows remain isolated by bidding zone. Since European SDAC moved to a 15-minute market time unit for delivery from 1 October 2025, the parser accepts validated 15/30/60-minute intervals; the UI averages complete sub-hourly groups into aligned UTC hours for comparison with Ukraine. See the official [ENTSO-E SDAC implementation timeline](https://www.entsoe.eu/network_codes/cacm/implementation/sdac/) and [Transparency Platform extraction guide](https://transparency.entsoe.eu/content/static_content/download?path=%2FStatic+content%2Fweb+api%2FIG-for-TP-data-extraction-process.pdf).

Neighbor prices remain in EUR/MWh. The Ukrainian curve and cross-border spread are intentionally not converted until an effective-dated official NBU exchange-rate source is implemented. Moldova is also excluded from this first adapter because a stable ENTSO-E day-ahead bidding-zone price feed has not yet been verified.

## Data-source responsibilities

- `OperatorMarketSource` discovers published results and returns raw source metadata.
- `EntsoeSource` downloads raw XML and does not parse or persist it.
- `parse_price_document` converts ENTSO-E XML to immutable hourly records.
- `validate_delivery_periods` verifies completeness and continuity.
- `RawArtifactStore` preserves source bytes under a content hash.
- `SQLiteMarketRepository` owns the transactional and idempotent database contract.

No source adapter writes files or database rows; application services coordinate those side effects.

## Research reference

`docs/references/RDN_Deep_Analysis_and_Forecast_UA.pdf` documents prior monthly analysis for 2019-2025 with an external 2026 check. Its strongest result is negative but valuable: on the monthly dataset, more complex lagged-factor models did not beat the persistence baseline. We therefore use the report to define hypotheses and validation constraints, not as proof that a production hourly model will work.

The engineering interpretation and reproducibility limits are recorded in `docs/references/README.md`.

## Repository history

The original prototype fetched ENTSO-E or data.gov.ua data directly from one `main.py` and appended a tracked CSV. That implementation is retained in Git history and tagged as `prototype-v0`; it is not part of the new runtime.
