# Research references

## RDN Deep Analysis and Forecast UA

Source artifact: `RDN_Deep_Analysis_and_Forecast_UA.pdf`

- Coverage described in the report: July 2019 through December 2025.
- External check described in the report: January through August 2026.
- PDF SHA-256: `2C87A8BD9B18B4F161DB6359BA1686B26EBA90AA8D6E75AD9FF712F9A47B4251`.
- Role in this repository: theoretical and empirical research reference, not executable specification and not a production dataset.

## Findings adopted as engineering constraints

1. A persistence baseline must be evaluated before any ML model. The report's monthly walk-forward experiment found that naive `t-1` beat both Ridge variants and the `t-12` seasonal baseline.
2. Random train/test splits are prohibited for forecast evaluation. Use walk-forward evaluation with information available at each historical cutoff.
3. Every forecast-time feature must carry an `available_at` or equivalent forecast-vintage timestamp.
4. Price-cap regimes must be stored as versioned effective-date data rather than inferred from observed prices.
5. D+1, D+2..D+7, and month-ahead products require separate targets, features, and evaluation.
6. Missing source values remain missing. They must not be silently replaced with zero.
7. Price-only and monthly-factor models are research baselines, not production candidates.

## Hypotheses to test on hourly data

- Residual load is a better price driver than raw load or raw renewable generation alone.
- Available import capacity, nominations, neighbor-market spreads, and recent physical flows improve D+1 forecasts.
- Hydro availability reduces peak-price pressure in otherwise comparable system states.
- Forecast solar/wind ramps improve morning and evening price-shape prediction.
- A deficit/cap-binding regime feature improves nonlinear model calibration.
- Regime-specific or conformal intervals provide better calibrated uncertainty than a single global residual band.

These are hypotheses, not accepted causal claims. Import, DAM volume, generation shares, and participant counts can be endogenous or trend-driven.

## Findings not reproducible from the PDF alone

The PDF reports correlations, OLS coefficients, walk-forward metrics, and 2026 out-of-sample errors, but the underlying source workbook/dataset and analysis code are not included in this repository. Therefore:

- reported statistics may be cited as prior research;
- they must not be treated as current verified metrics;
- they must not be encoded as fixed model weights;
- reproduction requires the original dataset, data dictionary, transformations, and analysis code.

## Backlog implications

- Add effective-dated `market_price_caps` storage.
- Include `available_at`, `published_at`, and source revision in fundamental observations.
- Add regime slices to evaluation: normal, deficit, cap-binding, outage, high-RES.
- Report MAE/RMSE plus peak/off-peak, cap-hit, directional, and interval metrics.
- Preserve a monthly regime-analysis track separately from the operational hourly model.
