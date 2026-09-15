"""Raw external-source adapters."""

from .entsoe import EntsoeSource
from .operator_market import OperatorMarketSource
from .operator_intraday import OperatorIntradaySource
from .nbu import NbuExchangeRateSource
from .open_meteo import OpenMeteoSource, parse_open_meteo_forecast
from .google_sheets_gas import GoogleSheetsGasSource

__all__ = [
    "EntsoeSource",
    "NbuExchangeRateSource",
    "OpenMeteoSource",
    "OperatorMarketSource",
    "OperatorIntradaySource",
    "GoogleSheetsGasSource",
    "parse_open_meteo_forecast",
]
