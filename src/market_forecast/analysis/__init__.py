"""Decision-support analytics built from validated market observations."""

from .price_drivers import (
    PRICE_SEGMENTS,
    build_price_driver_comparison,
    neighbor_daily_change,
)

__all__ = [
    "PRICE_SEGMENTS",
    "build_price_driver_comparison",
    "neighbor_daily_change",
]
