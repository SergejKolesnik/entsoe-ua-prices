# Ukraine Energy Market Forecast — Project Context

Last updated: 2026-08-18

## Purpose

Build an independent decision-support system for Ukrainian day-ahead market data, historical analysis, walk-forward evaluation, and eventually price forecasting for D+1 through D+7.

## Current phase

Phase 4: transparent forecasting baseline. Durable ingestion, automated refresh, analytics UI, and leakage-safe walk-forward evaluation exist; no production-grade forecast, Supabase integration, or Solar Monitoring System integration exists yet.

## Architecture decisions

- This repository is independent from `Solar-Monitoring-System`; failures here must not affect the daily solar forecast.
- Market Operator and ENTSO-E are separate source adapters behind a raw-response boundary.
- Domain timestamps are timezone-aware and normalized to UTC.
- Missing settlement periods are validation errors, not zero-valued observations.
- Git-tracked CSV is retired as operational storage.
- The old prototype is preserved by Git history and the `prototype-v0` tag.
- The research PDF in `docs/references/` is retained as a theoretical reference. Its reported monthly statistics are not considered reproduced until the underlying dataset and analysis code are available.
- Effective-dated price-cap regimes and forecast feature `available_at` timestamps are mandatory parts of the future data model.
- Raw source artifacts are immutable, content-addressed files; SQLite stores their provenance and normalized price rows.
- Normalized rows use a source/market/zone/delivery-start uniqueness contract so retries are idempotent.
- Market Operator results are legacy XLS files despite the endpoint name. The verified layout has one worksheet, one header row, and hourly rows with the DAM price in column 2.
- The operator-generated OLE sector chain is malformed; tolerant loading is allowed only before strict row-count and numeric validation.
- Historical backfill is sequential, bounded, delay-controlled, and preserves a per-day outcome instead of hiding failures.
- Quality reporting compares each Kyiv delivery date against its expected 23/24/25 hourly periods and returns non-zero for incomplete coverage.
- ENTSO-E HTTP errors are sanitized before logging so request URLs cannot expose the security token.
- The Streamlit dashboard reads the same SQLite repository and is presentation-only: it does not collect data or mutate the database.
- The forecast tab compares a same-weekday median against previous-day persistence on identical chronological cutoffs and displays only the lower-MAE baseline.
- Forecast timestamps always start after the latest published DAM delivery day. The P80 absolute-error band is an empirical diagnostic, not a guaranteed confidence interval.
- A local staged backfill validated 366/366 delivery days from 2025-08-19 through 2026-08-19 with 8,784/8,784 expected periods, including the real 25-hour and 23-hour DST days. The SQLite/raw dataset remains local and Git-ignored.
- Page views never trigger source requests. `refresh_operator.py` is the scheduler-safe one-shot entry point and defaults to tomorrow in the Kyiv calendar.
- Windows Task Scheduler runs the refresh at 14:15, 15:00, 16:00, and 17:00 local time; retries remain idempotent and missed runs start when the computer becomes available.
- Every automatic attempt is stored as `collected`, `unpublished`, or `failed`; the dashboard exposes freshness without storing raw exception text that could contain sensitive URLs.

## Security note

The historical public repository tracked an `.env` file containing an ENTSO-E token. The token must be revoked and replaced. Removing the file in the current branch does not remove it from old commits; history rewriting requires separate explicit approval.

## Next priorities

1. Accumulate a wider history and monitor baseline stability by rolling evaluation window.
2. Add cross-source comparison without silently selecting a winner.
3. Add effective-dated price caps and calendar features before testing any ML candidate.
4. Add regression fixtures for documented 23/25-period operator days when available.
5. Design and review optional PostgreSQL/Supabase migrations, including feature publication timestamps.
