"""Transparent day-over-day diagnostics for Ukrainian DAM prices."""

from __future__ import annotations

from datetime import date
from typing import Any

import pandas as pd


PRICE_SEGMENTS = (
    ("Ніч", 0, 5),
    ("Ранок", 6, 9),
    ("Сонячні години", 10, 16),
    ("Вечірній пік", 17, 22),
    ("Пізній вечір", 23, 23),
)


def build_price_driver_comparison(
    prices: pd.DataFrame,
    volumes: pd.DataFrame,
    selected_date: date,
) -> dict[str, Any] | None:
    """Compare a delivery day with the latest earlier observed day.

    The result deliberately contains observations only. It does not assign causal
    weights to weather, generation, or market behaviour that are not in the input.
    """

    required_price_columns = {"delivery_date", "hour", "price"}
    if prices.empty or not required_price_columns.issubset(prices.columns):
        return None
    current = prices[prices["delivery_date"] == selected_date].copy()
    previous_dates = sorted(
        day for day in prices["delivery_date"].dropna().unique() if day < selected_date
    )
    if current.empty or not previous_dates:
        return None
    previous_date = previous_dates[-1]
    previous = prices[prices["delivery_date"] == previous_date].copy()

    current_average = float(current["price"].mean())
    previous_average = float(previous["price"].mean())
    absolute_change = current_average - previous_average
    percent_change = (
        absolute_change / previous_average * 100 if previous_average else None
    )

    segment_rows: list[dict[str, Any]] = []
    for label, start_hour, end_hour in PRICE_SEGMENTS:
        current_segment = current[current["hour"].between(start_hour, end_hour)]
        previous_segment = previous[previous["hour"].between(start_hour, end_hour)]
        if current_segment.empty or previous_segment.empty:
            continue
        current_value = float(current_segment["price"].mean())
        previous_value = float(previous_segment["price"].mean())
        segment_rows.append(
            {
                "Період": label,
                "Години": f"{start_hour:02d}:00–{end_hour:02d}:59",
                "Поточна ціна": current_value,
                "Попередня ціна": previous_value,
                "Зміна": current_value - previous_value,
                "Зміна, %": (
                    (current_value - previous_value) / previous_value * 100
                    if previous_value
                    else None
                ),
            }
        )

    current_volume = _daily_volume(volumes, selected_date)
    previous_volume = _daily_volume(volumes, previous_date)
    volume_change_percent = None
    if current_volume is not None and previous_volume:
        volume_change_percent = (current_volume - previous_volume) / previous_volume * 100

    earlier = prices[prices["delivery_date"] < selected_date].copy()
    reference_dates = sorted(earlier["delivery_date"].dropna().unique())[-7:]
    seven_day_average = None
    seven_day_change_percent = None
    if reference_dates:
        daily_averages = (
            earlier[earlier["delivery_date"].isin(reference_dates)]
            .groupby("delivery_date")["price"]
            .mean()
        )
        if not daily_averages.empty:
            seven_day_average = float(daily_averages.mean())
            if seven_day_average:
                seven_day_change_percent = (
                    (current_average - seven_day_average) / seven_day_average * 100
                )

    return {
        "selected_date": selected_date,
        "previous_date": previous_date,
        "current_average": current_average,
        "previous_average": previous_average,
        "absolute_change": absolute_change,
        "percent_change": percent_change,
        "current_volume": current_volume,
        "previous_volume": previous_volume,
        "volume_change_percent": volume_change_percent,
        "seven_day_average": seven_day_average,
        "seven_day_change_percent": seven_day_change_percent,
        "seven_day_count": len(reference_dates),
        "low_price_hours": int((current["price"] <= 1_000).sum()),
        "segments": pd.DataFrame(segment_rows),
    }


def daily_net_import_comparison(
    flows: pd.DataFrame, selected_date: date, previous_date: date
) -> dict[str, float] | None:
    """Compare validated net cross-border energy for two complete delivery days."""

    required_columns = {"delivery_date", "net_import_mwh"}
    if flows.empty or not required_columns.issubset(flows.columns):
        return None
    daily = flows.groupby("delivery_date")["net_import_mwh"].sum()
    if selected_date not in daily.index or previous_date not in daily.index:
        return None
    current = float(daily.loc[selected_date])
    previous = float(daily.loc[previous_date])
    return {
        "current_net_import_mwh": current,
        "previous_net_import_mwh": previous,
        "absolute_change_mwh": current - previous,
    }


def analyze_flow_price_relationship(
    aligned: pd.DataFrame,
    *,
    max_lag_hours: int = 24,
    min_observations: int = 24,
) -> pd.DataFrame:
    """Measure contemporaneous and lagged associations between flows and price.

    A positive lag means that the flow observation precedes the price observation
    by that many hours. Results are descriptive and must not be interpreted as
    evidence of causality.
    """

    factors = {
        "import_mwh": "Імпорт",
        "export_mwh": "Експорт",
        "net_import_mwh": "Чистий імпорт",
    }
    required = {"price_eur", *factors}
    if (
        aligned.empty
        or not required.issubset(aligned.columns)
        or max_lag_hours < 0
        or min_observations < 2
    ):
        return pd.DataFrame()

    ordered = aligned.sort_values("delivery_start") if "delivery_start" in aligned else aligned
    rows: list[dict[str, float | int | str]] = []
    for column, label in factors.items():
        lag_results: list[tuple[int, float, int]] = []
        for lag in range(max_lag_hours + 1):
            pairs = pd.DataFrame(
                {
                    "price": pd.to_numeric(ordered["price_eur"], errors="coerce"),
                    "factor": pd.to_numeric(ordered[column], errors="coerce").shift(lag),
                }
            ).dropna()
            if (
                len(pairs) < min_observations
                or pairs["price"].nunique() < 2
                or pairs["factor"].nunique() < 2
            ):
                continue
            correlation = float(pairs["price"].corr(pairs["factor"]))
            if pd.notna(correlation):
                lag_results.append((lag, correlation, len(pairs)))
        if not lag_results:
            continue
        strongest = max(lag_results, key=lambda item: abs(item[1]))
        contemporaneous = next((item for item in lag_results if item[0] == 0), None)
        rows.append(
            {
                "factor": label,
                "correlation_lag_0": contemporaneous[1] if contemporaneous else float("nan"),
                "strongest_correlation": strongest[1],
                "strongest_lag_hours": strongest[0],
                "observations": strongest[2],
            }
        )
    return pd.DataFrame(rows)


def align_hourly_flow_prices(
    prices: pd.DataFrame, flows: pd.DataFrame
) -> pd.DataFrame:
    """Align prices and directed flow energy on unambiguous UTC hours."""

    if (
        prices.empty
        or flows.empty
        or not {"delivery_start", "price_eur"}.issubset(prices.columns)
        or not {"delivery_start", "direction", "energy_mwh"}.issubset(flows.columns)
    ):
        return pd.DataFrame()

    hourly_prices = prices.copy()
    hourly_flows = flows.copy()
    try:
        price_times = pd.to_datetime(hourly_prices["delivery_start"])
        flow_times = pd.to_datetime(hourly_flows["delivery_start"])
        if price_times.dt.tz is None or flow_times.dt.tz is None:
            return pd.DataFrame()
        hourly_prices["delivery_start"] = price_times.dt.tz_convert("UTC").dt.floor("h")
        hourly_flows["delivery_start"] = flow_times.dt.tz_convert("UTC").dt.floor("h")
    except (AttributeError, TypeError, ValueError):
        return pd.DataFrame()

    hourly_prices = hourly_prices.groupby("delivery_start", as_index=False)[
        "price_eur"
    ].mean()
    hourly_flows = hourly_flows.groupby(
        ["delivery_start", "direction"], as_index=False
    )["energy_mwh"].sum().pivot(
        index="delivery_start", columns="direction", values="energy_mwh"
    ).reset_index()
    if not {"Імпорт", "Експорт"}.issubset(hourly_flows.columns):
        return pd.DataFrame()
    hourly_flows = hourly_flows.rename(
        columns={"Імпорт": "import_mwh", "Експорт": "export_mwh"}
    )
    hourly_flows["net_import_mwh"] = (
        hourly_flows["import_mwh"] - hourly_flows["export_mwh"]
    )
    return hourly_prices.merge(hourly_flows, on="delivery_start", how="inner")


def describe_flow_price_relationship(results: pd.DataFrame) -> str | None:
    """Return a cautious Ukrainian interpretation of the net-import signal."""

    required = {"factor", "strongest_correlation", "strongest_lag_hours", "observations"}
    if results.empty or not required.issubset(results.columns):
        return None
    net_rows = results[results["factor"] == "Чистий імпорт"]
    if net_rows.empty:
        return None
    row = net_rows.iloc[0]
    correlation = float(row["strongest_correlation"])
    magnitude = abs(correlation)
    strength = "слабкий" if magnitude < 0.2 else "помірний" if magnitude < 0.5 else "сильний"
    direction = "вищою" if correlation > 0 else "нижчою"
    lag = int(row["strongest_lag_hours"])
    timing = "в ту саму годину" if lag == 0 else f"через {lag} год після зміни перетоку"
    return (
        f"У вибраному періоді зв’язок між чистим імпортом і ціною {strength} "
        f"(r={correlation:+.2f}, {timing}, n={int(row['observations'])}). "
        f"Більший чистий імпорт частіше збігався з {direction} ціною. "
        "Це статистичний збіг, а не доказ впливу; сезонність і добовий профіль "
        "можуть пояснювати частину зв’язку."
    )


def build_hourly_price_flow_comparison(
    prices: pd.DataFrame,
    flows: pd.DataFrame,
    selected_date: date,
    previous_date: date,
) -> pd.DataFrame:
    """Align hourly prices for two days with selected-day net imports."""

    if prices.empty or not {"delivery_date", "hour", "price"}.issubset(prices.columns):
        return pd.DataFrame()
    selected = (
        prices[prices["delivery_date"] == selected_date]
        .groupby("hour", as_index=False)["price"]
        .mean()
        .rename(columns={"price": "current_price"})
    )
    previous = (
        prices[prices["delivery_date"] == previous_date]
        .groupby("hour", as_index=False)["price"]
        .mean()
        .rename(columns={"price": "previous_price"})
    )
    result = selected.merge(previous, on="hour", how="outer").sort_values("hour")
    if flows.empty or not {"delivery_date", "delivery_start", "net_import_mwh"}.issubset(
        flows.columns
    ):
        result["net_import_mwh"] = pd.NA
        return result
    selected_flows = flows[flows["delivery_date"] == selected_date].copy()
    if selected_flows.empty:
        result["net_import_mwh"] = pd.NA
        return result
    selected_flows["hour"] = pd.to_datetime(selected_flows["delivery_start"]).dt.hour
    hourly_flows = selected_flows.groupby("hour", as_index=False)["net_import_mwh"].sum()
    return result.merge(hourly_flows, on="hour", how="left")


def build_daily_explanation(
    comparison: dict[str, Any],
    neighbor_change_percent: float | None = None,
    flow_comparison: dict[str, float] | None = None,
) -> str:
    """Build a cautious Ukrainian summary of observed, non-causal signals."""

    absolute_change = comparison["absolute_change"]
    percent_change = comparison.get("percent_change")
    if absolute_change == 0:
        opening = (
            "Середня ціна не змінилася проти "
            f"{comparison['previous_date'].strftime('%d.%m')}."
        )
    elif percent_change is None:
        direction = "зросла" if absolute_change > 0 else "знизилася"
        opening = (
            f"Середня ціна {direction} на {abs(absolute_change):,.0f} грн/МВт·год "
            f"проти {comparison['previous_date'].strftime('%d.%m')}; відсоток "
            "не розраховується через нульову базу порівняння."
        )
    else:
        direction = "зросла" if absolute_change > 0 else "знизилася"
        opening = (
            f"Середня ціна {direction} на {abs(percent_change):.1f}% "
            f"проти {comparison['previous_date'].strftime('%d.%m')}."
        )
    parts = [opening]
    seven_day_change = comparison.get("seven_day_change_percent")
    if seven_day_change is not None:
        relation = "вище" if seven_day_change > 0 else "нижче"
        parts.append(
            f"Це на {abs(seven_day_change):.1f}% {relation} середнього рівня "
            f"за {comparison['seven_day_count']} попередніх доступних днів."
        )
    segments = comparison.get("segments")
    comparable_segments = (
        segments.dropna(subset=["Зміна, %"])
        if isinstance(segments, pd.DataFrame) and "Зміна, %" in segments.columns
        else pd.DataFrame()
    )
    if not comparable_segments.empty:
        strongest = comparable_segments.loc[
            comparable_segments["Зміна, %"].abs().idxmax()
        ]
        parts.append(
            f"Найбільше відхилення зафіксовано у періоді «{strongest['Період']}» "
            f"({strongest['Зміна, %']:+.1f}%)."
        )
    signals = []
    volume_change = comparison.get("volume_change_percent")
    if volume_change is not None:
        signals.append(f"обсяг РДН {volume_change:+.1f}%")
    if neighbor_change_percent is not None:
        signals.append(f"медіана сусідніх ринків {neighbor_change_percent:+.1f}%")
    if flow_comparison is not None:
        signals.append(
            "чистий імпорт змінився на "
            f"{flow_comparison['absolute_change_mwh']:+,.0f} МВт·год"
        )
    if signals:
        parts.append("Одночасно спостерігалися: " + "; ".join(signals) + ".")
    parts.append(
        "Це діагностичні збіги, а не доказ причинно-наслідкового зв’язку."
    )
    return " ".join(parts)


def neighbor_daily_change(
    frame: pd.DataFrame, selected_date: date, previous_date: date
) -> float | None:
    """Return the median neighboring-market daily price change in percent."""

    required_columns = {"delivery_date", "market_code", "price_eur"}
    if frame.empty or not required_columns.issubset(frame.columns):
        return None
    neighbors = frame[frame["market_code"] != "UA"]
    daily = neighbors.groupby(["delivery_date", "market_code"])["price_eur"].mean()
    changes = []
    for code in neighbors["market_code"].unique():
        current_key = (selected_date, code)
        previous_key = (previous_date, code)
        if current_key not in daily.index or previous_key not in daily.index:
            continue
        previous_value = float(daily.loc[previous_key])
        if previous_value:
            changes.append(
                (float(daily.loc[current_key]) - previous_value) / previous_value * 100
            )
    return float(pd.Series(changes).median()) if changes else None


def _daily_volume(volumes: pd.DataFrame, delivery_date: date) -> float | None:
    if volumes.empty or not {"delivery_date", "volume_mwh"}.issubset(volumes.columns):
        return None
    rows = volumes[volumes["delivery_date"] == delivery_date]["volume_mwh"].dropna()
    return float(rows.sum()) if not rows.empty else None
