# Ukraine Energy Market Forecast — Project Context

Last updated: 2026-08-18

## Purpose

Build an independent decision-support system for Ukrainian day-ahead market data, historical analysis, walk-forward evaluation, and eventually price forecasting for D+1 through D+7.

## Current phase

Phase 1: market data foundation. No production forecast, Streamlit UI, Supabase integration, or Solar Monitoring System integration exists yet.

## Architecture decisions

- This repository is independent from `Solar-Monitoring-System`; failures here must not affect the daily solar forecast.
- Market Operator and ENTSO-E are separate source adapters behind a raw-response boundary.
- Domain timestamps are timezone-aware and normalized to UTC.
- Missing settlement periods are validation errors, not zero-valued observations.
- Git-tracked CSV is retired as operational storage.
- The old prototype is preserved by Git history and the `prototype-v0` tag.
- The research PDF in `docs/references/` is retained as a theoretical reference. Its reported monthly statistics are not considered reproduced until the underlying dataset and analysis code are available.
- Effective-dated price-cap regimes and forecast feature `available_at` timestamps are mandatory parts of the future data model.

## Security note

The historical public repository tracked an `.env` file containing an ENTSO-E token. The token must be revoked and replaced. Removing the file in the current branch does not remove it from old commits; history rewriting requires separate explicit approval.

## Next priorities

1. Complete Market Operator hourly Excel parsing with real sanitized fixtures.
2. Add raw artifact checksums and filesystem landing storage.
3. Design and review Supabase migrations, including market price caps and feature publication timestamps.
4. Perform controlled historical backfill and data-quality reporting.
5. Only then implement the naive comparable-day baseline and walk-forward backtesting.
