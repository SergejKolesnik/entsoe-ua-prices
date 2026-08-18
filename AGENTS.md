# Repository instructions

## Purpose

This repository collects, validates, stores, and later forecasts Ukrainian day-ahead electricity market data. It is independent from Solar Monitoring System.

## Safety

- Never commit `.env`, API tokens, database credentials, raw production exports, or service-account files.
- Invalid, incomplete, stale, or unexpected source data must fail visibly. Never replace missing prices with zero.
- Preserve raw source responses before normalization when ingestion persistence is implemented.
- Do not rewrite Git history or force-push without explicit user approval.
- Direct pushes to `main` require explicit user confirmation. Use a feature branch and pull request by default.

## Architecture

- `sources/` fetches raw source responses and does not persist or interpret market values.
- `parsers/` converts raw source formats into domain records.
- `validation/` checks completeness and invariants without repairing data.
- `persistence/` owns database access when added.
- Forecasting must not be added before the ingestion history passes data-quality review.

## Commands

```bash
python -m unittest discover -s tests -v
python -m compileall -q src tests
python -m market_forecast.cli --help
```

Set `PYTHONPATH=src` when running directly from a checkout that has not been installed.

## Definition of done

- Add or update tests for behavior changes.
- Run the full unit-test suite and compile check.
- Update README and PROJECT_CONTEXT when architecture, configuration, or data contracts change.
- Report uncommitted or unpushed work explicitly.
