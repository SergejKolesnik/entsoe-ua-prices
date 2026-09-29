"""Raw external-source adapters."""

from .entsoe import EntsoeSource
from .operator_market import OperatorMarketSource
from .operator_intraday import OperatorIntradaySource
from .nbu import NbuExchangeRateSource
from .open_meteo import OpenMeteoSource, parse_open_meteo_forecast
from .google_sheets_gas import GoogleSheetsGasSource
from .self_generation import load_self_generation_source
from .system_status import SystemStatusItem, fetch_telegram_channel

__all__ = [
    "EntsoeSource",
    "NbuExchangeRateSource",
    "OpenMeteoSource",
    "OperatorMarketSource",
    "OperatorIntradaySource",
    "GoogleSheetsGasSource",
    "parse_open_meteo_forecast",
    "load_self_generation_source",
    "SystemStatusItem",
    "fetch_telegram_channel",
]
