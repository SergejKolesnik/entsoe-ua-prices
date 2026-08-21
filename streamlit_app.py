"""Streamlit dashboard for independently collected Ukrainian DAM prices."""

from __future__ import annotations

import sys
import math
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
from market_forecast.analysis import (  # noqa: E402
    build_price_driver_comparison,
    neighbor_daily_change,
)
from market_forecast.forecasting import build_day_forecast, walk_forward_backtest  # noqa: E402
from market_forecast.neighbor_markets import NEIGHBOR_MARKETS  # noqa: E402
from market_forecast.persistence import (  # noqa: E402
    SQLiteMarketRepository,
    create_market_repository,
)
from market_forecast.services import aggregate_price_rows_hourly, build_quality_report  # noqa: E402


KYIV = ZoneInfo("Europe/Kyiv")
SOURCE = "operator_market"
AMBER = "#ffb800"
BLUE = "#378add"
RED = "#ef6a5b"
MUTED = "#7f8a9a"
MARKET_COLORS = {
    "UA": "#b58cff",
    "PL": AMBER,
    "SK": "#58c68d",
    "HU": RED,
    "RO": BLUE,
}


def _repository(database_path: Path | str) -> SQLiteMarketRepository:
    """Return Neon storage when configured, otherwise the local SQLite database."""

    settings = Settings.from_environment()
    return create_market_repository(Path(database_path), settings.database_url)


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
        [data-testid="stMultiSelect"] [data-tag][aria-label="Україна"] {
            background: #b58cff !important; color: #101621 !important;
        }
        [data-testid="stMultiSelect"] [data-tag][aria-label="Польща"] {
            background: #ffb800 !important; color: #101621 !important;
        }
        [data-testid="stMultiSelect"] [data-tag][aria-label="Словаччина"] {
            background: #58c68d !important; color: #101621 !important;
        }
        [data-testid="stMultiSelect"] [data-tag][aria-label="Угорщина"] {
            background: #ef6a5b !important; color: #101621 !important;
        }
        [data-testid="stMultiSelect"] [data-tag][aria-label="Румунія"] {
            background: #378add !important; color: #ffffff !important;
        }
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
    repository = _repository(database_path)
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


@st.cache_data(ttl=60)
def _load_price_volumes(
    database_path: str, date_from: date, date_to: date
) -> pd.DataFrame:
    repository = _repository(database_path)
    start = datetime.combine(date_from, time.min, KYIV).astimezone(timezone.utc)
    end = datetime.combine(date_to + timedelta(days=1), time.min, KYIV).astimezone(
        timezone.utc
    )
    rows = repository.list_price_volumes(SOURCE, start, end)
    frame = pd.DataFrame(rows, columns=["delivery_start_utc", "volume_mwh"])
    if frame.empty:
        return frame
    frame["delivery_start"] = pd.to_datetime(
        frame["delivery_start_utc"], utc=True
    ).dt.tz_convert("Europe/Kyiv")
    frame["delivery_date"] = frame["delivery_start"].dt.date
    frame["hour"] = frame["delivery_start"].dt.hour
    frame["volume_mwh"] = pd.to_numeric(frame["volume_mwh"], errors="coerce")
    return frame


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

    weekday_labels = {
        0: "Понеділок",
        1: "Вівторок",
        2: "Середа",
        3: "Четвер",
        4: "Пʼятниця",
        5: "Субота",
        6: "Неділя",
    }
    weekly = frame.copy()
    weekly["weekday"] = weekly["delivery_start"].dt.weekday
    matrix = weekly.pivot_table(
        index="weekday", columns="hour", values="price", aggfunc="mean"
    ).reindex(index=range(7), columns=range(24))
    st.markdown("#### Типовий тижневий профіль")
    st.caption(
        "Середня ціна для кожної години та дня тижня у вибраному періоді. "
        "Тепліші кольори означають дорожчі години."
    )
    heatmap = go.Figure(
        go.Heatmap(
            z=matrix.values,
            x=list(matrix.columns),
            y=[weekday_labels[item] for item in matrix.index],
            colorscale=[[0, "#10243b"], [0.45, BLUE], [0.72, AMBER], [1, RED]],
            colorbar=dict(title="грн/МВт·год"),
            hovertemplate="%{y} · %{x}:00<br>Середня: %{z:,.0f} грн/МВт·год<extra></extra>",
        )
    )
    heatmap.update_layout(**_chart_layout(390, "День тижня"))
    heatmap.update_xaxes(title="Година", dtick=2)
    st.plotly_chart(heatmap, width="stretch")


def _draw_quality(database_path: Path, date_from: date, date_to: date) -> None:
    repository = _repository(database_path)
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


def _draw_forecast_monitoring(database_path: Path) -> None:
    repository = _repository(database_path)
    _draw_collection_health(repository)
    st.divider()
    st.markdown("#### Контроль зафіксованих прогнозів")
    runs = repository.list_forecast_runs(limit=30)
    if not runs:
        st.info(
            "Ще немає зафіксованих прогнозів. Перший snapshot буде створено "
            "автоматично після успішного оновлення РДН."
        )
        return

    run_by_id = {item[0]: item for item in runs}
    selected_run_id = st.selectbox(
        "Зафіксований прогноз",
        options=list(run_by_id),
        format_func=lambda run_id: (
            f"{run_by_id[run_id][1].strftime('%d.%m.%Y')} · "
            f"{run_by_id[run_id][4]}@{run_by_id[run_id][5]}"
        ),
    )
    run = run_by_id[selected_run_id]
    points = repository.list_forecast_points(selected_run_id)
    if not points:
        st.error("Прогнозний запуск не містить погодинних значень.")
        return
    actual_rows = repository.list_prices(
        SOURCE,
        points[0][0],
        points[-1][0] + timedelta(hours=1),
    )
    actual_by_time = dict(actual_rows)
    matched = [
        (timestamp, predicted, actual_by_time[timestamp])
        for timestamp, predicted, *_ in points
        if timestamp in actual_by_time
    ]
    complete = len(matched) == len(points)
    mae = None
    rmse = None
    if complete:
        absolute_errors = [abs(actual - predicted) for _, predicted, actual in matched]
        mae = sum(absolute_errors, Decimal(0)) / len(absolute_errors)
        mse = sum(
            (actual - predicted) ** 2 for _, predicted, actual in matched
        ) / len(matched)
        rmse = Decimal(str(math.sqrt(float(mse))))

    issued_local = run[2].astimezone(KYIV)
    columns = st.columns(4)
    columns[0].metric("Дата прогнозу", run[1].strftime("%d.%m.%Y"))
    columns[1].metric("Зафіксовано", issued_local.strftime("%d.%m %H:%M"))
    columns[2].metric("Факт отримано", f"{len(matched)}/{len(points)} год")
    columns[3].metric(
        "Фактичний MAE",
        f"{float(mae):,.0f} грн/МВт·год" if mae is not None else "Очікуємо",
    )

    starts = [item[0].astimezone(KYIV) for item in points]
    predicted = [float(item[1]) for item in points]
    lower = [float(item[2]) for item in points]
    upper = [float(item[3]) for item in points]
    figure = go.Figure()
    figure.add_trace(
        go.Scatter(
            x=starts,
            y=upper,
            mode="lines",
            line=dict(width=0),
            showlegend=False,
            hoverinfo="skip",
        )
    )
    figure.add_trace(
        go.Scatter(
            x=starts,
            y=lower,
            mode="lines",
            line=dict(width=0),
            fill="tonexty",
            fillcolor="rgba(55,138,221,.18)",
            name="Зафіксований P80-коридор",
        )
    )
    figure.add_trace(
        go.Scatter(
            x=starts,
            y=predicted,
            mode="lines+markers",
            line=dict(color=AMBER, width=3),
            marker=dict(size=5),
            name="Зафіксований прогноз",
        )
    )
    if actual_rows:
        figure.add_trace(
            go.Scatter(
                x=[timestamp.astimezone(KYIV) for timestamp, _ in actual_rows],
                y=[float(value) for _, value in actual_rows],
                mode="lines+markers",
                line=dict(color="#58c68d", width=2.5),
                marker=dict(size=5),
                name="Фактична ціна",
            )
        )
    figure.update_layout(**_chart_layout(410, "грн/МВт·год"))
    figure.update_xaxes(title="Година постачання", dtick=2 * 60 * 60 * 1000)
    st.plotly_chart(figure, width="stretch")

    summary_rows = []
    for item in runs:
        run_points = repository.list_forecast_points(item[0])
        run_actual = dict(
            repository.list_prices(
                SOURCE,
                run_points[0][0],
                run_points[-1][0] + timedelta(hours=1),
            )
        )
        errors = [
            abs(run_actual[timestamp] - prediction)
            for timestamp, prediction, *_ in run_points
            if timestamp in run_actual
        ]
        observed_mae = (
            float(sum(errors, Decimal(0)) / len(errors))
            if len(errors) == len(run_points)
            else None
        )
        summary_rows.append(
            {
                "Дата": item[1],
                "Модель": f"{item[4]}@{item[5]}",
                "Створено": item[2].astimezone(KYIV),
                "Факт": f"{len(errors)}/{len(run_points)}",
                "MAE": observed_mae,
                "Статус": "Оцінено" if observed_mae is not None else "Очікує факт",
            }
        )
    st.markdown("#### Журнал незмінних прогнозів")
    st.dataframe(
        pd.DataFrame(summary_rows),
        width="stretch",
        hide_index=True,
        column_config={"MAE": st.column_config.NumberColumn(format="%.0f грн/МВт·год")},
    )
    if complete and rmse is not None:
        st.caption(f"RMSE вибраного прогнозу: {float(rmse):,.0f} грн/МВт·год.")


def _draw_collection_health(repository: SQLiteMarketRepository) -> None:
    """Render a compact operational view of every scheduled data family."""

    today = datetime.now(KYIV).date()
    country_names = {market.code: market.name_uk for market in NEIGHBOR_MARKETS}
    groups = [
        ("Український РДН", (SOURCE,), today + timedelta(days=1)),
        ("Курс НБУ EUR", ("nbu_fx",), today + timedelta(days=1)),
        ("Обсяги РДН України", ("operator_volume",), today),
    ]
    groups.extend(
        (f"Ціни · {country_names[code]}", (f"entsoe_price_{code}",), today)
        for code in country_names
    )
    groups.extend(
        (
            f"Перетоки · {country_names[code]}",
            (f"entsoe_flow_{code}_import", f"entsoe_flow_{code}_export"),
            today - timedelta(days=1),
        )
        for code in country_names
    )
    source_names = [source for _, sources, _ in groups for source in sources]
    attempts = repository.latest_collection_attempts(source_names)
    rows = []
    needs_attention = 0
    for label, sources, expected_date in groups:
        entries = [attempts.get(source) for source in sources]
        present = [entry for entry in entries if entry is not None]
        if len(present) != len(sources):
            status = "⚪ Немає запуску"
            needs_attention += 1
        elif any(entry[2] == "failed" for entry in present):
            status = "🔴 Помилка"
            needs_attention += 1
        elif any(entry[2] == "unpublished" for entry in present):
            status = "🟡 Очікуються дані"
        elif any(entry[0] < expected_date for entry in present):
            status = "🟠 Застаріло"
            needs_attention += 1
        else:
            status = "🟢 Актуально"
        newest_attempt = max((entry[1] for entry in present), default=None)
        oldest_delivery = min((entry[0] for entry in present), default=None)
        rows.append(
            {
                "Джерело": label,
                "Статус": status,
                "Дані за": oldest_delivery,
                "Остання спроба": newest_attempt.astimezone(KYIV) if newest_attempt else None,
                "Записів у спробі": sum(entry[3] for entry in present),
            }
        )

    if needs_attention:
        st.warning(f"Потрібна увага: {needs_attention} із {len(groups)} джерел.")
    else:
        st.success("Автоматичне оновлення працює: критичних проблем немає.")
    st.dataframe(
        pd.DataFrame(rows),
        width="stretch",
        hide_index=True,
        column_config={
            "Дані за": st.column_config.DateColumn(format="DD.MM.YYYY"),
            "Остання спроба": st.column_config.DatetimeColumn(format="DD.MM.YYYY HH:mm"),
            "Записів у спробі": st.column_config.NumberColumn(format="%d"),
        },
    )
    st.caption(
        "Нуль записів у спробі може означати, що дані вже були в базі; повторні запуски "
        "не створюють дублів. Перетоки показуються одним рядком для імпорту й експорту."
    )


@st.cache_data(ttl=60)
def _load_neighbor_prices(
    database_path: str, date_from: date, date_to: date
) -> pd.DataFrame:
    repository = _repository(database_path)
    repository.initialize()
    start = datetime.combine(date_from, time.min, KYIV).astimezone(timezone.utc)
    end = datetime.combine(date_to + timedelta(days=1), time.min, KYIV).astimezone(
        timezone.utc
    )
    records = []
    rates = repository.list_exchange_rates(date_from, date_to)
    ukrainian_rows = repository.list_prices("operator_market", start, end)
    for timestamp, price in ukrainian_rows:
        local = timestamp.astimezone(KYIV)
        rate = rates.get(local.date())
        if rate is None:
            continue
        records.append(
            {
                "delivery_start": local,
                "delivery_date": local.date(),
                "hour": local.hour,
                "market_code": "UA",
                "market_name": "Україна",
                "price_eur": float(price / rate),
            }
        )
    for market in NEIGHBOR_MARKETS:
        raw_rows = repository.list_prices(
            "entsoe", start, end, bidding_zone=market.bidding_zone_eic
        )
        if not raw_rows:
            continue
        for timestamp, price in aggregate_price_rows_hourly(raw_rows):
            local = timestamp.astimezone(KYIV)
            records.append(
                {
                    "delivery_start": local,
                    "delivery_date": local.date(),
                    "hour": local.hour,
                    "market_code": market.code,
                    "market_name": market.name_uk,
                    "price_eur": float(price),
                }
            )
    return pd.DataFrame(records)


@st.cache_data(ttl=60)
def _load_cross_border_flows(
    database_path: str, date_from: date, date_to: date
) -> pd.DataFrame:
    repository = _repository(database_path)
    repository.initialize()
    start = datetime.combine(date_from, time.min, KYIV).astimezone(timezone.utc)
    end = datetime.combine(date_to + timedelta(days=1), time.min, KYIV).astimezone(timezone.utc)
    ukraine_zone = "10Y1001C--00003F"
    market_by_eic = {market.bidding_zone_eic: market for market in NEIGHBOR_MARKETS}
    records = []
    for timestamp, interval_end, source_zone, target_zone, power_mw in repository.list_flows(start, end):
        if target_zone == ukraine_zone and source_zone in market_by_eic:
            direction = "Імпорт"
            market = market_by_eic[source_zone]
            signed_power = float(power_mw)
        elif source_zone == ukraine_zone and target_zone in market_by_eic:
            direction = "Експорт"
            market = market_by_eic[target_zone]
            signed_power = -float(power_mw)
        else:
            continue
        local = timestamp.astimezone(KYIV)
        interval_hours = (interval_end - timestamp).total_seconds() / 3600
        records.append({
            "delivery_start": local,
            "delivery_date": local.date(),
            "market_name": market.name_uk,
            "direction": direction,
            "power_mw": abs(float(power_mw)),
            "energy_mwh": abs(float(power_mw)) * interval_hours,
            "interval_hours": interval_hours,
            "net_import_mw": signed_power,
            "net_import_mwh": signed_power * interval_hours,
        })
    return pd.DataFrame(records)


def _draw_market_volume(database_path: Path, selected_date: date) -> None:
    repository = _repository(database_path)
    start = datetime.combine(selected_date, time.min, KYIV).astimezone(timezone.utc)
    end = datetime.combine(selected_date + timedelta(days=1), time.min, KYIV).astimezone(timezone.utc)
    volume_rows = repository.list_price_volumes(SOURCE, start, end)
    available = [(timestamp, value) for timestamp, value in volume_rows if value is not None]
    if not available:
        st.caption("Обсяг продажу РДН для цього дня ще не завантажено.")
        return
    prices = dict(repository.list_prices(SOURCE, start, end))
    figure = go.Figure()
    figure.add_trace(go.Bar(
        x=[timestamp.astimezone(KYIV) for timestamp, _ in available],
        y=[float(value) for _, value in available],
        name="Обсяг продажу",
        marker_color=BLUE,
        opacity=0.55,
        yaxis="y",
    ))
    figure.add_trace(go.Scatter(
        x=[timestamp.astimezone(KYIV) for timestamp, _ in available],
        y=[float(prices[timestamp]) for timestamp, _ in available],
        name="Ціна РДН",
        line=dict(color=AMBER, width=3),
        yaxis="y2",
    ))
    layout = _chart_layout(360, "МВт·год")
    layout.update(
        yaxis2=dict(title="грн/МВт·год", overlaying="y", side="right", showgrid=False),
        legend=dict(orientation="h", y=1.12),
    )
    figure.update_layout(**layout)
    figure.update_xaxes(title="Година за Києвом")
    st.markdown("#### Ціна та обсяг продажу РДН")
    st.plotly_chart(figure, width="stretch")


def _draw_price_drivers(
    database_path: Path,
    frame: pd.DataFrame,
    date_from: date,
    date_to: date,
    selected_date: date,
) -> None:
    """Explain observed price movement without presenting correlation as causation."""

    volumes = _load_price_volumes(str(database_path), date_from, date_to)
    comparison = build_price_driver_comparison(frame, volumes, selected_date)
    st.markdown("### Що змінило ціну")
    st.caption(
        "Перший діагностичний рівень: підтверджені ціни та обсяги. "
        "Погодні й генераційні фактори будуть додані окремо з часом доступності даних."
    )
    if comparison is None:
        st.info("Для порівняння потрібні вибрана доба та хоча б одна попередня доба.")
        return

    percent_change = comparison["percent_change"]
    volume_change = comparison["volume_change_percent"]
    metrics = st.columns(4)
    metrics[0].metric(
        "Середня ціна",
        f"{comparison['current_average']:,.0f} грн/МВт·год",
        f"{percent_change:+.1f}% до {comparison['previous_date'].strftime('%d.%m')}",
    )
    metrics[1].metric(
        "Зміна ціни",
        f"{comparison['absolute_change']:+,.0f} грн/МВт·год",
    )
    metrics[2].metric(
        "Обсяг РДН",
        (
            f"{comparison['current_volume']:,.0f} МВт·год"
            if comparison["current_volume"] is not None
            else "Немає даних"
        ),
        f"{volume_change:+.1f}%" if volume_change is not None else None,
    )
    metrics[3].metric(
        "Години ≤ 1 000 грн",
        str(comparison["low_price_hours"]),
        "ціновий надлишок" if comparison["low_price_hours"] else "не зафіксовано",
    )

    st.markdown("#### Де саме відбулася зміна")
    segments = comparison["segments"]
    if not segments.empty:
        segment_figure = go.Figure()
        segment_figure.add_trace(
            go.Bar(
                x=segments["Період"],
                y=segments["Попередня ціна"],
                name=comparison["previous_date"].strftime("%d.%m"),
                marker_color=MUTED,
            )
        )
        segment_figure.add_trace(
            go.Bar(
                x=segments["Період"],
                y=segments["Поточна ціна"],
                name=selected_date.strftime("%d.%m"),
                marker_color=AMBER,
            )
        )
        segment_figure.update_layout(
            **_chart_layout(340, "грн/МВт·год"), barmode="group"
        )
        st.plotly_chart(segment_figure, width="stretch")
        st.dataframe(
            segments,
            width="stretch",
            hide_index=True,
            column_config={
                "Поточна ціна": st.column_config.NumberColumn(format="%.0f грн/МВт·год"),
                "Попередня ціна": st.column_config.NumberColumn(format="%.0f грн/МВт·год"),
                "Зміна": st.column_config.NumberColumn(format="%+.0f грн/МВт·год"),
                "Зміна, %": st.column_config.NumberColumn(format="%+.1f%%"),
            },
        )

    evidence: list[dict[str, str]] = []
    if volume_change is not None:
        evidence.append(
            {
                "Сигнал": "Обсяг торгів РДН",
                "Що бачимо": f"{volume_change:+.1f}% до попередньої доступної доби",
                "Статус": "Підтверджено",
                "Інтерпретація": (
                    "Менше закуплено саме на РДН; це не дорівнює зміні загального "
                    "споживання енергосистеми."
                ),
            }
        )

    neighbor_frame = _load_neighbor_prices(str(database_path), date_from, date_to)
    neighbor_change = neighbor_daily_change(
        neighbor_frame, selected_date, comparison["previous_date"]
    )
    if neighbor_change is not None:
        direction = "зросли" if neighbor_change > 0 else "знизилися"
        evidence.append(
            {
                "Сигнал": "Сусідні ринки",
                "Що бачимо": f"Медіанна зміна {neighbor_change:+.1f}%",
                "Статус": "Підтверджено",
                "Інтерпретація": (
                    f"Ціни сусідів у середньому {direction}; це допомагає відрізнити "
                    "внутрішню українську подію від загальнорегіонального руху."
                ),
            }
        )
    evidence.extend(
        [
            {
                "Сигнал": "Сонячна та вітрова генерація",
                "Що бачимо": "Ще не завантажено",
                "Статус": "Гіпотеза",
                "Інтерпретація": "Не робимо причинного висновку лише з форми цінового графіка.",
            },
            {
                "Сигнал": "Доступність блоків і прогноз навантаження",
                "Що бачимо": "Ще не завантажено",
                "Статус": "Гіпотеза",
                "Інтерпретація": "Потрібні дані, відомі учасникам до закриття торгів.",
            },
        ]
    )
    st.markdown("#### Таблиця доказів")
    st.dataframe(pd.DataFrame(evidence), width="stretch", hide_index=True)
    st.caption(
        "Підтверджено — значення є в нашій базі. Гіпотеза — можливий фактор, "
        "якому ще бракує окремого надійного джерела."
    )


def _draw_neighbor_markets(
    database_path: Path,
    date_from: date,
    date_to: date,
    selected_date: date,
) -> None:
    frame = _load_neighbor_prices(str(database_path), date_from, date_to)
    if frame.empty:
        st.info(
            "Даних сусідніх ринків у локальній базі ще немає. Код збору готовий, "
            "але для ENTSO-E потрібен новий персональний API-токен."
        )
        st.code(
            "$env:ENTSOE_TOKEN = \"new-token\"\n"
            "python -m market_forecast.cli backfill-neighbors "
            "--market all --from 2025-08-19 --to 2026-08-20",
            language="powershell",
        )
        st.caption(
            "Старий токен із Git-історії не використовується. Після налаштування "
            "живі дані зʼявляться тут без змін українського контуру."
        )
        return

    market_names = {"UA": "Україна"} | {
        market.code: market.name_uk for market in NEIGHBOR_MARKETS
    }
    available_codes = [
        "UA",
        *[
        market.code
        for market in NEIGHBOR_MARKETS
        if market.code in set(frame["market_code"])
        ],
    ] if "UA" in set(frame["market_code"]) else [
        market.code for market in NEIGHBOR_MARKETS
        if market.code in set(frame["market_code"])
    ]
    selected_codes = st.multiselect(
        "Ринки",
        options=available_codes,
        default=available_codes,
        format_func=lambda code: market_names[code],
    )
    if not selected_codes:
        st.info("Виберіть хоча б один ринок.")
        return
    selected = frame[frame["market_code"].isin(selected_codes)]

    st.markdown("#### Середня ціна за добу")
    daily = (
        selected.groupby(
            ["delivery_date", "market_code", "market_name"], as_index=False
        )["price_eur"]
        .mean()
        .sort_values("delivery_date")
    )
    daily_figure = go.Figure()
    for market_code in selected_codes:
        values = daily[daily["market_code"] == market_code]
        if values.empty:
            continue
        daily_figure.add_trace(
            go.Scatter(
                x=values["delivery_date"],
                y=values["price_eur"],
                mode="lines",
                line=dict(color=MARKET_COLORS[market_code], width=2),
                name=market_names[market_code],
            )
        )
    daily_figure.update_layout(**_chart_layout(350, "EUR/МВт·год"))
    daily_figure.update_xaxes(title="Дата постачання")
    st.plotly_chart(daily_figure, width="stretch")

    dates_by_market = {
        code: set(selected.loc[selected["market_code"] == code, "delivery_date"])
        for code in selected_codes
    }
    common_dates = sorted(
        set.intersection(*(dates for dates in dates_by_market.values() if dates))
    ) if all(dates_by_market.values()) else []
    comparison_dates = [day for day in common_dates if day <= selected_date][-2:]
    if not comparison_dates:
        comparison_dates = common_dates[-2:]

    st.markdown("#### Погодинне порівняння · останні спільні доби")
    if not comparison_dates:
        st.warning("Немає доби зі спільними погодинними даними вибраних ринків.")
    else:
        chart_columns = st.columns(len(comparison_dates))
        for column, comparison_date in zip(chart_columns, comparison_dates):
            column.markdown(f"**{comparison_date.strftime('%d.%m.%Y')}**")
            hourly = selected[selected["delivery_date"] == comparison_date]
            hourly_figure = go.Figure()
            for market_code in selected_codes:
                values = hourly[hourly["market_code"] == market_code].sort_values(
                    "delivery_start"
                )
                if values.empty:
                    continue
                hourly_figure.add_trace(
                    go.Scatter(
                        x=values["hour"],
                        y=values["price_eur"],
                        mode="lines+markers",
                        line=dict(color=MARKET_COLORS[market_code], width=2.5),
                        marker=dict(size=4),
                        name=market_names[market_code],
                    )
                )
            layout = _chart_layout(360, "EUR/МВт·год")
            layout.update(
                legend=dict(orientation="h", y=1.18, font=dict(size=10)),
            )
            hourly_figure.update_layout(**layout)
            hourly_figure.update_xaxes(
                title="Година за Києвом", tickmode="linear", dtick=3, range=[0, 23]
            )
            column.plotly_chart(hourly_figure, width="stretch")
        if selected_date not in comparison_dates:
            st.caption(
                f"За {selected_date.strftime('%d.%m.%Y')} ще немає повного набору "
                "сусідніх ринків, тому показано дві останні спільні доби."
            )

    if "UA" in set(selected_codes):
        st.markdown("#### Зв’язок з українською ціною")
        pivot = selected.pivot_table(
            index="delivery_start", columns="market_code", values="price_eur", aggfunc="mean"
        )
        relationship_rows = []
        for code in selected_codes:
            if code == "UA" or code not in pivot.columns:
                continue
            aligned = pivot[["UA", code]].dropna()
            relationship_rows.append({
                "Ринок": market_names[code],
                "Спільних годин": len(aligned),
                "Кореляція цін": aligned["UA"].corr(aligned[code]) if len(aligned) >= 24 else None,
                "Середній спред Україна − ринок": (aligned["UA"] - aligned[code]).mean() if not aligned.empty else None,
            })
        if relationship_rows:
            st.dataframe(
                pd.DataFrame(relationship_rows),
                width="stretch",
                hide_index=True,
                column_config={
                    "Кореляція цін": st.column_config.NumberColumn(format="%.3f"),
                    "Середній спред Україна − ринок": st.column_config.NumberColumn(format="%.2f EUR/МВт·год"),
                },
            )
            st.caption(
                "Кореляція показує спільний рух цін, але сама по собі не доводить причинний вплив. "
                "Для стійкого висновку потрібна довша історія та контроль перетоків, попиту й сезонності."
            )

    flow_frame = _load_cross_border_flows(str(database_path), date_from, date_to)
    st.markdown("#### Фізичний імпорт та експорт")
    if flow_frame.empty:
        st.info("Дані фізичних перетоків ще не завантажено.")
    else:
        coverage = flow_frame.groupby(
            ["delivery_date", "market_name", "direction"], as_index=False
        )["interval_hours"].sum()
        complete_dates = coverage.groupby("delivery_date").filter(
            lambda group: len(group) == len(NEIGHBOR_MARKETS) * 2
            and (group["interval_hours"] >= 23.99).all()
        )["delivery_date"].unique()
        excluded_dates = sorted(set(flow_frame["delivery_date"]) - set(complete_dates))
        daily_flows = flow_frame[flow_frame["delivery_date"].isin(complete_dates)].copy()
        if excluded_dates:
            st.warning(
                "Не показано неповні доби перетоків: "
                + ", ".join(day.strftime("%d.%m.%Y") for day in excluded_dates)
                + ". ENTSO-E має пропуски хоча б на одному кордоні або напрямку."
            )
        if daily_flows.empty:
            st.info("Немає жодної доби з повним покриттям усіх напрямків.")
            return
        complete_flow_rows = daily_flows.copy()
        daily_flows = daily_flows.groupby(
            ["delivery_date", "direction"], as_index=False
        )["energy_mwh"].sum()
        flow_figure = go.Figure()
        for direction, color, sign in (("Імпорт", "#58c68d", 1), ("Експорт", RED, -1)):
            values = daily_flows[daily_flows["direction"] == direction]
            flow_figure.add_trace(go.Bar(
                x=values["delivery_date"],
                y=values["energy_mwh"] * sign,
                name=direction,
                marker_color=color,
            ))
        flow_figure.update_layout(**_chart_layout(330, "МВт·год"), barmode="relative")
        flow_figure.update_xaxes(title="Дата постачання")
        st.plotly_chart(flow_figure, width="stretch")

        complete_date_list = sorted(complete_dates)
        eligible_flow_dates = [day for day in complete_date_list if day <= selected_date]
        hourly_flow_date = (
            eligible_flow_dates[-1] if eligible_flow_dates else complete_date_list[-1]
        )
        hourly_flows = complete_flow_rows[
            complete_flow_rows["delivery_date"] == hourly_flow_date
        ].copy()
        hourly_flows["hour"] = hourly_flows["delivery_start"].dt.hour
        hourly_flows = hourly_flows.groupby(
            ["hour", "direction"], as_index=False
        )["energy_mwh"].sum()
        flow_profile = hourly_flows.pivot_table(
            index="hour", columns="direction", values="energy_mwh", fill_value=0
        ).reindex(range(24), fill_value=0)
        imports = flow_profile.get("Імпорт", pd.Series(0, index=flow_profile.index))
        exports = flow_profile.get("Експорт", pd.Series(0, index=flow_profile.index))
        net_import = imports - exports

        st.markdown(
            f"#### Погодинний профіль перетоків · "
            f"{hourly_flow_date.strftime('%d.%m.%Y')}"
        )
        hourly_flow_figure = go.Figure()
        hourly_flow_figure.add_trace(
            go.Bar(
                x=flow_profile.index,
                y=imports,
                name="Імпорт",
                marker_color="#58c68d",
                hovertemplate="%{x}:00 · імпорт %{y:,.0f} МВт·год<extra></extra>",
            )
        )
        hourly_flow_figure.add_trace(
            go.Bar(
                x=flow_profile.index,
                y=-exports,
                name="Експорт",
                marker_color=RED,
                hovertemplate="%{x}:00 · експорт %{customdata:,.0f} МВт·год<extra></extra>",
                customdata=exports,
            )
        )
        hourly_flow_figure.add_trace(
            go.Scatter(
                x=flow_profile.index,
                y=net_import,
                name="Чистий імпорт",
                mode="lines+markers",
                line=dict(color=AMBER, width=2.5),
                marker=dict(size=4),
                hovertemplate="%{x}:00 · баланс %{y:,.0f} МВт·год<extra></extra>",
            )
        )
        hourly_layout = _chart_layout(360, "МВт·год")
        hourly_layout.update(
            barmode="relative",
            legend=dict(orientation="h", y=1.12),
        )
        hourly_flow_figure.update_layout(**hourly_layout)
        hourly_flow_figure.update_xaxes(
            title="Година за Києвом", tickmode="linear", dtick=2, range=[-0.5, 23.5]
        )
        st.plotly_chart(hourly_flow_figure, width="stretch")
        if hourly_flow_date != selected_date:
            st.caption(
                f"За {selected_date.strftime('%d.%m.%Y')} повні перетоки ще не "
                f"опубліковані, тому показано останню повну добу — "
                f"{hourly_flow_date.strftime('%d.%m.%Y')}."
            )
        st.caption(
            "Зелений стовпчик — сумарний імпорт, червоний нижче нуля — експорт, "
            "жовта лінія — погодинний баланс. 15-хвилинні значення Польщі "
            "підсумовуються до відповідної години."
        )

        ukrainian_hourly = frame[frame["market_code"] == "UA"][
            ["delivery_start", "price_eur"]
        ].copy()
        flow_hourly = complete_flow_rows.copy()
        flow_hourly["delivery_start"] = flow_hourly["delivery_start"].dt.floor("h")
        flow_hourly = flow_hourly.groupby("delivery_start", as_index=False)[
            "net_import_mwh"
        ].sum()
        aligned_flow = ukrainian_hourly.merge(flow_hourly, on="delivery_start", how="inner")
        if len(aligned_flow) >= 24:
            price_flow_correlation = aligned_flow["price_eur"].corr(
                aligned_flow["net_import_mwh"]
            )
            metric_columns = st.columns(2)
            metric_columns[0].metric(
                "Кореляція ціна ↔ чистий імпорт",
                f"{price_flow_correlation:.3f}",
            )
            metric_columns[1].metric("Спільних годин", f"{len(aligned_flow)}")
            st.caption(
                "Додатне значення означає, що в цій вибірці вища ціна частіше "
                "співпадала з більшим чистим імпортом; це не доводить напрям причинності."
            )

    st.caption(
        "Європейські 15-хвилинні MTU агрегуються у погодинне середнє та "
        "вирівнюються за UTC. Українська ціна переведена в EUR за офіційним "
        "курсом НБУ для відповідної дати; первинні ціни в грн у базі не змінюються."
    )


def main() -> None:
    st.set_page_config(page_title="RDN Market Intelligence", page_icon="⚡", layout="wide")
    _inject_styles()
    settings = Settings.from_environment()
    repository = create_market_repository(settings.database_path, settings.database_url)
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
        storage_label = "Neon PostgreSQL" if settings.database_url else str(settings.database_path)
        st.caption(f"База: {storage_label}")
        if st.button("Оновити екран", width="stretch"):
            st.cache_data.clear()
            st.rerun()

    frame = _load_prices(str(settings.database_path), date_from, date_to)
    if frame.empty:
        st.warning("У вибраному періоді немає даних.")
        return

    overview, history, drivers, quality, forecast, monitoring, neighbors = st.tabs(
        [
            "Огляд дня",
            "Історія",
            "Фактори ціни",
            "Якість даних",
            "Прогноз",
            "Моніторинг",
            "Сусідні ринки",
        ]
    )
    with overview:
        _draw_overview(frame, selected_date)
        _draw_market_volume(settings.database_path, selected_date)
    with history:
        _draw_history(frame)
    with drivers:
        _draw_price_drivers(
            settings.database_path, frame, date_from, date_to, selected_date
        )
    with quality:
        _draw_quality(settings.database_path, date_from, date_to)
    with forecast:
        forecast_history = _load_prices(str(settings.database_path), earliest, latest)
        _draw_forecast(forecast_history, latest)
    with monitoring:
        _draw_forecast_monitoring(settings.database_path)
    with neighbors:
        _draw_neighbor_markets(settings.database_path, date_from, date_to, selected_date)


if __name__ == "__main__":
    main()
