"""Shadow equivalence for Minimal Core E12-B suffix-market wrapper deletion.

No production routing changes are made here. The test compares the existing
market tag with a smaller candidate that asks the suffix semantic owner once.
"""

from __future__ import annotations

import pytest

from data_provider.base import _is_hk_market, _is_us_market, _market_tag
from src.services.market_symbol_utils import get_suffix_market


def _shadow_market_tag(code: str) -> str:
    if _is_us_market(code):
        return "us"
    if _is_hk_market(code):
        return "hk"
    suffix_market = get_suffix_market(code)
    return suffix_market if suffix_market in {"jp", "kr", "tw"} else "cn"


@pytest.mark.parametrize(
    "symbol",
    [
        "600519",
        "BJ920748",
        "HK00700",
        "700.HK",
        "00700",
        "AAPL",
        "7203.T",
        "005930.KS",
        "035720.KQ",
        "2330.TW",
        "6505.TWO",
        "7203.X",
    ],
)
def test_e12b_single_suffix_lookup_matches_current_market_tag(symbol: str) -> None:
    assert _shadow_market_tag(symbol) == _market_tag(symbol)


def test_e12b_suffix_market_is_one_mutually_exclusive_fact() -> None:
    assert get_suffix_market("7203.T") == "jp"
    assert get_suffix_market("005930.KS") == "kr"
    assert get_suffix_market("2330.TW") == "tw"
    assert get_suffix_market("AAPL") is None
