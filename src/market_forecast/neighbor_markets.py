"""Verified ENTSO-E bidding-zone registry for EU markets bordering Ukraine."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class NeighborMarket:
    """Stable display and ENTSO-E identity for one neighboring bidding zone."""

    code: str
    name_uk: str
    bidding_zone_eic: str


NEIGHBOR_MARKETS = (
    NeighborMarket("PL", "Польща", "10YPL-AREA-----S"),
    NeighborMarket("SK", "Словаччина", "10YSK-SEPS-----K"),
    NeighborMarket("HU", "Угорщина", "10YHU-MAVIR----U"),
    NeighborMarket("RO", "Румунія", "10YRO-TEL------P"),
)

MARKET_BY_CODE = {market.code: market for market in NEIGHBOR_MARKETS}
MARKET_BY_EIC = {market.bidding_zone_eic: market for market in NEIGHBOR_MARKETS}
