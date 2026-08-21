# Ukraine Energy Market Forecast — Project Context

Last updated: 2026-08-20

## Purpose

Build an independent decision-support system for Ukrainian day-ahead market data, historical analysis, walk-forward evaluation, and eventually price forecasting for D+1 through D+7.

## Current phase

Phase 5: publication foundation. Durable ingestion, automated refresh, analytics UI, leakage-safe walk-forward evaluation, and an optional dedicated Neon PostgreSQL backend exist; no production-grade forecast or Solar Monitoring System integration exists.

## Architecture decisions

- This repository is independent from `Solar-Monitoring-System`; failures here must not affect the daily solar forecast.
- Market Operator and ENTSO-E are separate source adapters behind a raw-response boundary.
- Domain timestamps are timezone-aware and normalized to UTC.
- Missing settlement periods are validation errors, not zero-valued observations.
- Git-tracked CSV is retired as operational storage.
- Storage selection is configuration-driven: Neon is used only when `DATABASE_URL` is present, while SQLite remains the local fallback.
- Database credentials are runtime secrets and must never be committed or displayed in the dashboard.
- Streamlit Community Cloud installs runtime packages from the explicit root `requirements.txt`; keep it aligned with `pyproject.toml`.
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
- Page views never trigger source requests. `refresh_operator.py` refreshes tomorrow's Ukrainian results; `refresh_context.py` independently refreshes neighbor prices, NBU rates, completed flows, and recent volumes.
- Windows Task Scheduler runs the Operator refresh at 14:15, 15:00, 16:00, and 17:00 and the context refresh at 17:20 local time. Retries remain idempotent and missed runs start when the computer becomes available.
- Every automatic attempt is stored as `collected`, `unpublished`, or `failed`; the dashboard exposes freshness without storing raw exception text that could contain sensitive URLs.
- Every successful scheduled refresh freezes an immutable `baseline-v1` forecast for the first unknown delivery day. A target/model/version uniqueness contract prevents hindsight rewrites.
- Forecast runs retain their issue time, training cutoff, model version, backtest metrics, hourly prediction, P80 bounds, method, and sample count.
- The Monitoring tab scores frozen points against actual prices only after those facts exist and reports operational MAE/RMSE separately from historical backtest metrics.
- Neighbor-market support is additive and uses explicit ENTSO-E bidding zones for PL, SK, HU, and RO. Database reads and uniqueness remain isolated by bidding zone.
- ENTSO-E day-ahead prices accept validated 15/30/60-minute intervals. The comparison UI aggregates only complete sub-hourly groups to UTC-aligned hourly averages because SDAC moved to 15-minute MTU from delivery day 2025-10-01.
- Neighbor prices remain in EUR/MWh; no Ukrainian spread is displayed until historical official NBU rates are implemented. Moldova remains pending source verification.

## Security note

The historical public repository tracked an `.env` file containing an ENTSO-E token. The token must be revoked and replaced. Removing the file in the current branch does not remove it from old commits; history rewriting requires separate explicit approval.

## Next priorities

1. Accumulate at least 14–30 real frozen forecasts and monitor operational stability.
2. Continue the staged history from the validated baseline: 30 days of neighbor prices,
   366 NBU EUR rates, 367 days of Ukrainian prices/volumes, and six fully covered flow days.
   One incomplete ENTSO-E Poland export day is intentionally excluded from aggregates.
3. Measure lagged relationships between Ukrainian prices, neighbor prices, flows, and volumes.
4. Extend physical-flow history in controlled batches.
5. Add effective-dated price caps and calendar features as a separate shadow candidate.
6. Add regression fixtures for documented 23/25-period operator days when available.
7. Validate the Neon adapter against migrated data, then deploy a read-only Streamlit staging application.
