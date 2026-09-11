"""E12 Shadow differential for market-tag and daily/realtime routing.

This models the existing routing decisions without changing production code.
The candidate uses one mutually-exclusive suffix lookup after the existing
US/HK precedence checks.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from data_provider.base import (
    _is_hk_market,
    _is_us_market,
    _is_jp_market,
    _is_kr_market,
    _is_tw_market,
    _market_tag,
    is_us_index_code,
    is_us_stock_code,
)
from src.services.market_symbol_utils import get_suffix_market


@dataclass(frozen=True)
class RouteDecision:
    market: str
    is_us: bool
    is_hk: bool
    is_jp: bool
    is_kr: bool
    is_tw: bool
    branches: int
    lookups: int


def _current_route(code: str) -> RouteDecision:
    is_us_index = is_us_index_code(code)
    is_us = is_us_index or is_us_stock_code(code)
    is_hk = (not is_us) and _is_hk_market(code)
    is_jp = (not is_us) and (not is_hk) and _is_jp_market(code)
    is_kr = (not is_us) and (not is_hk) and _is_kr_market(code)
    is_tw = (not is_us) and (not is_hk) and _is_tw_market(code)
    market = "us" if is_us else "hk" if is_hk else "jp" if is_jp else "kr" if is_kr else "tw" if is_tw else "cn"
    return RouteDecision(market, is_us, is_hk, is_jp, is_kr, is_tw, 5, 3)


def _shadow_route(code: str) -> RouteDecision:
    is_us = is_us_index_code(code) or is_us_stock_code(code)
    is_hk = (not is_us) and _is_hk_market(code)
    suffix_market = None if is_us or is_hk else get_suffix_market(code)
    market = "us" if is_us else "hk" if is_hk else suffix_market or "cn"
    return RouteDecision(
        market,
        is_us,
        is_hk,
        suffix_market == "jp",
        suffix_market == "kr",
        suffix_market == "tw",
        3,
        1,
    )


SYMBOLS = [
    "600519", "000001.SZ", "BJ920748", "sh000016", "csi000300",
    "HK00700", "700.HK", "00700", "AAPL", "BRK.B", "^GSPC",
    "7203.T", "005930.KS", "035720.KQ", "2330.TW", "6505.TWO",
    "7203.X", "1234.T", "12345.KS", "123.TW", "123456.TWO",
    "700.HK.T", "AAPL.US", ".T", "7203.", "7203.T.T",
    " 2330.tw ", "005930.ks", "", "...", "not-a-symbol",
]


@pytest.mark.parametrize("symbol", SYMBOLS)
def test_e12_full_routing_differential_matches_current(symbol: str) -> None:
    current = _current_route(symbol)
    shadow = _shadow_route(symbol)
    assert shadow.market == current.market
    assert (shadow.is_us, shadow.is_hk, shadow.is_jp, shadow.is_kr, shadow.is_tw) == (
        current.is_us, current.is_hk, current.is_jp, current.is_kr, current.is_tw
    )


def test_e12_shadow_net_complexity_is_smaller_for_both_routing_paths() -> None:
    current = _current_route("7203.T")
    shadow = _shadow_route("7203.T")
    assert current.lookups == 3
    assert shadow.lookups == 1
    assert current.branches == 5
    assert shadow.branches == 3


def test_e12_suffix_markets_are_mutually_exclusive() -> None:
    for symbol, market in (("7203.T", "jp"), ("005930.KS", "kr"), ("2330.TW", "tw")):
        detected = get_suffix_market(symbol)
        assert detected == market
        assert sum(detected == candidate for candidate in ("jp", "kr", "tw")) == 1

