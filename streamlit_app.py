"""Streamlit dashboard for independently collected Ukrainian DAM prices."""

from __future__ import annotations

import sys
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import plotly.graph_objects as go
import streamlit as st


PROJECT_ROOT = Path(__file__).resolve().parent
SOURCE_ROOT = PROJECT_ROOT / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from market_forecast.config import Settings  # noqa: E402
from market_forecast.forecasting import build_day_forecast, walk_forward_backtest  # noqa: E402
from market_forecast.persistence import SQLiteMarketRepository  # noqa: E402
from market_forecast.services import build_quality_report  # noqa: E402


KYIV = ZoneInfo("Europe/Kyiv")
SOURCE = "operator_market"
AMBER = "#ffb800"
BLUE = "#378add"
RED = "#ef6a5b"
MUTED = "#7f8a9a"


def _inject_styles() -> None:
    st.markdown(
        """
        <style>
        .block-container { padding-top: 1.1rem; padding-bottom: 2rem; max-width: 1500px; }
        div[data-testid="stMetric"] {
            background: linear-gradient(135deg, rgba(17,23,34,.98), rgba(10,16,25,.98));
            border: 1px solid rgba(255,255,255,.08);
            border-radius: 8px;
            padding: 14px 16px;
        }
        div[data-testid="stMetricValue"] { color: #f4f6f8; }
        div[data-testid="stTabs"] [role="tablist"] { gap: 12px; }
        div[data-testid="stTabs"] button[role="tab"] {
            color: #8a94a6; font-weight: 650; font-size: 15px;
        }
        div[data-testid="stTabs"] button[role="tab"][aria-selected="true"] {
            color: #ffffff; border-bottom: 2px solid #ffb800;
        }
        .rdn-header {
            background: linear-gradient(135deg, rgba(17,22,34,.98), rgba(11,17,26,.98));
            border: 1px solid rgba(255,255,255,.08); border-radius: 8px;
            padding: 18px 22px; margin: 6px 0 18px;
            display: flex; align-items: center; justify-content: space-between; gap: 18px;
        }
        .rdn-brand { display: flex; align-items: center; gap: 14px; }
        .rdn-mark {
            width: 44px; height: 44px; border-radius: 8px; display: flex;
            align-items: center; justify-content: center; font-size: 25px;
            background: rgba(255,184,0,.14); color: #ffb800;
        }
        .rdn-title { font-size: 27px; font-weight: 800; color: #ffffff; }
        .rdn-title span { color: #ffb800; }
        .rdn-subtitle { color: rgba(255,255,255,.46); font-size: 11px; text-transform: uppercase; }
        .rdn-status { color: #aeb7c5; font-size: 12px; text-align: right; }
        .rdn-status strong { color: #ffb800; }
        @media (max-width: 760px) {
            .rdn-header { align-items: flex-start; flex-direction: column; }
            .rdn-title { font-size: 23px; }
            .rdn-status { text-align: left; }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _header(
    latest_date: date,
    latest_attempt: tuple[date, datetime, str, int, str | None] | None,
) -> None:
    expected_date = datetime.now(KYIV).date() + timedelta(days=1)
    if latest_date >= expected_date:
        status_text = "Дані актуальні"
        status_color = "#58c68d"
    elif latest_attempt is not None and latest_attempt[2] == "unpublished":
        status_text = "Нові ціни ще не опубліковані"
        status_color = AMBER
    elif latest_attempt is not None and latest_attempt[2] == "failed":
        status_text = "Помилка останнього оновлення"
        status_color = RED
    else:
        status_text = "Очікується оновлення"
        status_color = AMBER
    attempt_line = "Автоматичних спроб ще не було"
    if latest_attempt is not None:
        attempted_local = latest_attempt[1].astimezone(KYIV)
        attempt_line = f"Остання спроба: {attempted_local.strftime('%d.%m.%Y %H:%M')}"
    st.markdown(
        f"""
        <div class="rdn-header">
          <div class="rdn-brand">
            <div class="rdn-mark">⚡</div>
            <div>
              <div class="rdn-title">RDN <span>Market Intelligence</span></div>
              <div class="rdn-subtitle">Україна · ринок на добу наперед · незалежна система</div>
            </div>
          </div>
          <div class="rdn-status">
            <span style="color:{status_color};font-weight:700">● {status_text}</span><br>
            Останні ціни: <strong>{latest_date.strftime('%d.%m.%Y')}</strong><br>
            {attempt_line}
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


@st.cache_data(ttl=60)
def _load_prices(database_path: str, date_from: date, date_to: date) -> pd.DataFrame:
    repository = SQLiteMarketRepository(Path(database_path))
    start = datetime.combine(date_from, time.min, KYIV).astimezone(timezone.utc)
    end = datetime.combine(date_to + timedelta(days=1), time.min, KYIV).astimezone(
        timezone.utc
    )
    rows = repository.list_prices(SOURCE, start, end)
    frame = pd.DataFrame(rows, columns=["delivery_start_utc", "price"])
    if frame.empty:
        return frame
    frame["delivery_start"] = pd.to_datetime(frame["delivery_start_utc"], utc=True).dt.tz_convert(
        "Europe/Kyiv"
    )
    frame["delivery_date"] = frame["delivery_start"].dt.date
    frame["hour"] = frame["delivery_start"].dt.hour
    frame["price"] = pd.to_numeric(frame["price"], errors="coerce")
    return frame.dropna(subset=["price"])


def _daily_summary(frame: pd.DataFrame) -> pd.DataFrame:
    return (
        frame.groupby("delivery_date", as_index=False)["price"]
        .agg(minimum="min", average="mean", maximum="max")
        .sort_values("delivery_date")
    )


def _chart_layout(height: int, y_title: str) -> dict:
    return dict(
        height=height,
        margin=dict(l=12, r=12, t=24, b=12),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#dfe4ea"),
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
        xaxis=dict(gridcolor="rgba(255,255,255,.06)"),
        yaxis=dict(title=y_title, gridcolor="rgba(255,255,255,.07)"),
    )


def _draw_overview(frame: pd.DataFrame, selected_date: date) -> None:
    selected = frame[frame["delivery_date"] == selected_date].sort_values("hour")
    if selected.empty:
        st.warning("Для вибраної дати немає погодинних даних.")
        return
    previous_date = selected_date - timedelta(days=1)
    previous = frame[frame["delivery_date"] == previous_date].sort_values("hour")
    average = selected["price"].mean()
    minimum_row = selected.loc[selected["price"].idxmin()]
    maximum_row = selected.loc[selected["price"].idxmax()]
    previous_average = previous["price"].mean() if not previous.empty else None

    columns = st.columns(4)
    delta = average - previous_average if previous_average is not None else None
    columns[0].metric(
        "Середня ціна",
        f"{average:,.0f} грн/МВт·год",
        f"{delta:+,.0f} до попереднього дня" if delta is not None else None,
    )
    columns[1].metric("Мінімум", f"{minimum_row['price']:,.0f}", f"{int(minimum_row['hour']):02d}:00")
    columns[2].metric("Максимум", f"{maximum_row['price']:,.0f}", f"{int(maximum_row['hour']):02d}:00")
    columns[3].metric("Періоди", f"{len(selected)}/24", "повний день" if len(selected) == 24 else "перевірити")

    fig = go.Figure()
    if not previous.empty:
        fig.add_trace(
            go.Scatter(
                x=previous["hour"], y=previous["price"], name=previous_date.strftime("%d.%m"),
                mode="lines", line=dict(color=MUTED, width=1.5, dash="dot"),
            )
        )
    fig.add_trace(
        go.Scatter(
            x=selected["hour"], y=selected["price"], name=selected_date.strftime("%d.%m"),
            mode="lines+markers", line=dict(color=AMBER, width=3),
            marker=dict(size=6), fill="tozeroy", fillcolor="rgba(255,184,0,.08)",
        )
    )
    fig.update_layout(**_chart_layout(410, "грн/МВт·год"))
    fig.update_xaxes(title="Година", dtick=2, range=[0, 23])
    st.plotly_chart(fig, width="stretch")


def _draw_history(frame: pd.DataFrame) -> None:
    daily = _daily_summary(frame)
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=daily["delivery_date"], y=daily["maximum"], mode="lines",
            line=dict(width=0), showlegend=False, hoverinfo="skip",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=daily["delivery_date"], y=daily["minimum"], mode="lines",
            line=dict(width=0), fill="tonexty", fillcolor="rgba(55,138,221,.15)",
            name="Мін–макс",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=daily["delivery_date"], y=daily["average"], mode="lines+markers",
            line=dict(color=AMBER, width=2.5), marker=dict(size=5), name="Середня",
        )
    )
    fig.update_layout(**_chart_layout(390, "грн/МВт·год"))
    fig.update_xaxes(title="Дата постачання")
    st.plotly_chart(fig, width="stretch")

    matrix = frame.pivot_table(index="delivery_date", columns="hour", values="price", aggfunc="first")
    matrix = matrix.reindex(columns=range(24))
    heatmap = go.Figure(
        go.Heatmap(
            z=matrix.values,
            x=list(matrix.columns),
            y=[item.strftime("%d.%m") for item in matrix.index],
            colorscale=[[0, "#10243b"], [0.45, BLUE], [0.72, AMBER], [1, RED]],
            colorbar=dict(title="грн/МВт·год"),
            hovertemplate="%{y} · %{x}:00<br>%{z:,.0f} грн/МВт·год<extra></extra>",
        )
    )
    heatmap.update_layout(**_chart_layout(max(430, len(matrix) * 18), "Дата"))
    heatmap.update_xaxes(title="Година", dtick=2)
    st.plotly_chart(heatmap, width="stretch")


def _draw_quality(database_path: Path, date_from: date, date_to: date) -> None:
    repository = SQLiteMarketRepository(database_path)
    report = build_quality_report(repository, date_from, date_to, SOURCE)
    complete = sum(item.status == "complete" for item in report)
    expected = sum(item.expected_periods for item in report)
    actual = sum(item.actual_periods for item in report)
    cols = st.columns(3)
    cols[0].metric("Повні дні", f"{complete}/{len(report)}")
    cols[1].metric("Погодинні періоди", f"{actual}/{expected}")
    cols[2].metric("Пропуски", f"{expected - actual}")
    table = pd.DataFrame(
        {
            "Дата": [item.delivery_date for item in report],
            "Статус": ["Повний" if item.status == "complete" else "Пропуск" for item in report],
            "Періоди": [f"{item.actual_periods}/{item.expected_periods}" for item in report],
            "Мінімум": [float(item.minimum_price) if item.minimum_price is not None else None for item in report],
            "Середня": [float(item.average_price) if item.average_price is not None else None for item in report],
            "Максимум": [float(item.maximum_price) if item.maximum_price is not None else None for item in report],
        }
    )
    st.dataframe(
        table,
        width="stretch",
        hide_index=True,
        column_config={
            "Мінімум": st.column_config.NumberColumn(format="%.2f"),
            "Середня": st.column_config.NumberColumn(format="%.2f"),
            "Максимум": st.column_config.NumberColumn(format="%.2f"),
        },
    )


def _draw_forecast(frame: pd.DataFrame, latest_date: date) -> None:
    rows = [
        (
            item.delivery_start_utc.to_pydatetime()
            if hasattr(item.delivery_start_utc, "to_pydatetime")
            else item.delivery_start_utc,
            Decimal(str(item.price)),
        )
        for item in frame.itertuples()
    ]
    try:
        comparison = walk_forward_backtest(rows)
    except ValueError as exc:
        st.info(f"Прогноз ще не активований: {exc}")
        return
    champion = comparison.champion_method
    metrics = (
        comparison.comparable_day
        if champion == "comparable_day"
        else comparison.previous_day
    )
    target_date = latest_date + timedelta(days=1)
    forecast = build_day_forecast(rows, target_date, champion)
    if not forecast:
        st.warning("Не вдалося сформувати повний погодинний прогноз.")
        return

    method_label = {
        "comparable_day": "Медіана порівнянних днів",
        "previous_day": "Попередня доба",
    }
    columns = st.columns(4)
    columns[0].metric("Прогноз на", target_date.strftime("%d.%m.%Y"))
    columns[1].metric("Обрана модель", method_label[champion])
    columns[2].metric("Backtest MAE", f"{float(metrics.mae):,.0f} грн/МВт·год")
    columns[3].metric("Контрольна вибірка", f"{metrics.evaluated_days} днів")

    starts = [item.delivery_start_utc.astimezone(KYIV) for item in forecast]
    values = [float(item.predicted_price) for item in forecast]
    interval = float(metrics.absolute_error_p80)
    lower = [max(0.0, value - interval) for value in values]
    upper = [value + interval for value in values]
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=starts,
            y=upper,
            mode="lines",
            line=dict(width=0),
            showlegend=False,
            hoverinfo="skip",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=starts,
            y=lower,
            mode="lines",
            line=dict(width=0),
            fill="tonexty",
            fillcolor="rgba(55,138,221,.18)",
            name=f"Коридор ±{interval:,.0f} (P80 помилки)",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=starts,
            y=values,
            mode="lines+markers",
            line=dict(color=AMBER, width=3),
            marker=dict(size=6),
            name="Наступна невідома доба",
        )
    )
    fig.update_layout(**_chart_layout(420, "грн/МВт·год"))
    fig.update_xaxes(title="Година постачання", dtick=2 * 60 * 60 * 1000)
    st.plotly_chart(fig, width="stretch")

    comparison_table = pd.DataFrame(
        {
            "Модель": ["Порівнянні дні", "Попередня доба"],
            "MAE": [
                float(comparison.comparable_day.mae),
                float(comparison.previous_day.mae),
            ],
            "RMSE": [
                float(comparison.comparable_day.rmse),
                float(comparison.previous_day.rmse),
            ],
            "Годин у backtest": [
                comparison.comparable_day.observations,
                comparison.previous_day.observations,
            ],
            "Статус": [
                "Обрана" if champion == "comparable_day" else "Гірша",
                "Обрана" if champion == "previous_day" else "Гірша",
            ],
        }
    )
    st.dataframe(
        comparison_table,
        width="stretch",
        hide_index=True,
        column_config={
            "MAE": st.column_config.NumberColumn(format="%.0f грн/МВт·год"),
            "RMSE": st.column_config.NumberColumn(format="%.0f грн/МВт·год"),
        },
    )
    st.caption(
        "Це прозорий історичний baseline, а не фінальна виробнича модель. "
        "Дата прогнозу — перша доба після останніх уже опублікованих цін РДН. "
        "Коридор показує 80-й перцентиль абсолютної помилки backtest і не є "
        "гарантованим довірчим інтервалом."
    )


def main() -> None:
    st.set_page_config(page_title="RDN Market Intelligence", page_icon="⚡", layout="wide")
    _inject_styles()
    settings = Settings.from_environment()
    repository = SQLiteMarketRepository(settings.database_path)
    repository.initialize()
    available = repository.available_period(SOURCE)
    if available is None:
        st.error(
            "У локальній базі ще немає даних Оператора ринку. "
            "Спочатку виконайте команду backfill."
        )
        return

    earliest = available[0].astimezone(KYIV).date()
    latest = available[1].astimezone(KYIV).date()
    latest_attempt = repository.latest_collection_attempt(SOURCE)
    _header(latest, latest_attempt)

    with st.sidebar:
        st.markdown("### Період аналізу")
        selected_range = st.date_input(
            "Дати",
            value=(earliest, latest),
            min_value=earliest,
            max_value=latest,
        )
        if not isinstance(selected_range, tuple) or len(selected_range) != 2:
            st.info("Виберіть початкову та кінцеву дату.")
            return
        date_from, date_to = selected_range
        selected_date = st.date_input(
            "День на огляді",
            value=date_to,
            min_value=date_from,
            max_value=date_to,
        )
        st.divider()
        st.caption("Джерело: Оператор ринку України")
        st.caption(f"База: {settings.database_path}")
        if st.button("Оновити екран", width="stretch"):
            st.cache_data.clear()
            st.rerun()

    frame = _load_prices(str(settings.database_path), date_from, date_to)
    if frame.empty:
        st.warning("У вибраному періоді немає даних.")
        return

    overview, history, quality, forecast = st.tabs(
        ["Огляд дня", "Історія", "Якість даних", "Прогноз"]
    )
    with overview:
        _draw_overview(frame, selected_date)
    with history:
        _draw_history(frame)
    with quality:
        _draw_quality(settings.database_path, date_from, date_to)
    with forecast:
        forecast_history = _load_prices(str(settings.database_path), earliest, latest)
        _draw_forecast(forecast_history, latest)


if __name__ == "__main__":
    main()
