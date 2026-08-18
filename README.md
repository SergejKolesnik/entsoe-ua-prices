# Ukraine Energy Market Forecast

Independent Python foundation for collecting and validating Ukrainian day-ahead electricity-market data.

The project is intentionally separate from SkyGrid Solar. It currently provides source adapters, normalized domain models, raw artifact landing, SQLite persistence, ENTSO-E XML parsing, and settlement-period validation. Forecasting and UI are not implemented yet.

## Current capabilities

- Discover official Market Operator DAM results for a requested delivery date.
- Build the official Excel download URL only from a validated `hdata_link`.
- Fetch ENTSO-E Transparency Platform documents with explicit query parameters.
- Parse ENTSO-E price XML using interval timestamps and resolution.
- Reject duplicate, missing, overlapping, naive, or inconsistent hourly observations.
- Test 23-, 24-, and 25-period trading days without inventing missing values.
- Store immutable raw responses by SHA-256 and normalized prices idempotently in SQLite.
- Parse official Market Operator legacy XLS workbooks using their verified hourly layout.

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
