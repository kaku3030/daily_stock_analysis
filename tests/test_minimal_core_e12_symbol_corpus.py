"""Shadow evidence for Minimal Core E12 symbol-semantics simplification.

The tests intentionally record current behavior at three separate layers:
canonical/normalization, market classification, and provider wire formatting.
They do not authorize a production refactor or declare every current behavior
as the final desired contract.
"""

from __future__ import annotations

import pytest

from data_provider.base import canonical_stock_code, normalize_stock_code
from data_provider.futu_fetcher import _hk_symbol
from data_provider.tencent_fetcher import _to_tencent_symbol
from data_provider.yfinance_fetcher import YfinanceFetcher
from src.services.market_symbol_utils import get_suffix_market


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("600519", "600519"),
        ("SH600519", "600519"),
        ("SH.600519", "600519"),
        ("600519.SH", "600519"),
        ("SZ000001", "000001"),
        ("BJ920748", "920748"),
        ("920748.BJ", "920748"),
        ("hk1810", "HK01810"),
        ("1810.HK", "HK01810"),
        ("7203.T", "7203.T"),
        ("005930.KS", "005930.KS"),
        ("035720.KQ", "035720.KQ"),
        ("2330.TW", "2330.TW"),
        ("6505.TWO", "6505.TWO"),
        ("AAPL", "AAPL"),
    ],
)
def test_e12_current_normalize_stock_code_corpus(raw: str, expected: str) -> None:
    assert normalize_stock_code(raw) == expected


def test_e12_case_canonicalization_is_a_distinct_current_layer() -> None:
    assert canonical_stock_code("aapl") == "AAPL"
    # Record the current distinction rather than silently pretending the two
    # helpers already have one canonical contract.
    assert normalize_stock_code("aapl") == "aapl"


@pytest.mark.parametrize(
    ("symbol", "expected_market"),
    [
        ("7203.T", "jp"),
        ("005930.KS", "kr"),
        ("035720.KQ", "kr"),
        ("2330.TW", "tw"),
        ("6505.TWO", "tw"),
        ("7203.X", None),
        ("AAPL", None),
        ("123.KS", None),
    ],
)
def test_e12_suffix_market_table_current_behavior(
    symbol: str,
    expected_market: str | None,
) -> None:
    assert get_suffix_market(symbol) == expected_market


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("600519", "sh600519"),
        ("000001", "sz000001"),
        ("BJ920748", "bj920748"),
    ],
)
def test_e12_tencent_wire_symbols_remain_provider_specific(raw: str, expected: str) -> None:
    assert _to_tencent_symbol(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("600519", "600519.SS"),
        ("000001", "000001.SZ"),
        ("HK00700", "0700.HK"),
        ("AAPL", "AAPL"),
        ("7203.T", "7203.T"),
        ("2330.TW", "2330.TW"),
    ],
)
def test_e12_yfinance_wire_symbols_remain_provider_specific(raw: str, expected: str) -> None:
    assert YfinanceFetcher()._convert_stock_code(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("HK00700", "HK.00700"),
        ("00700", "HK.00700"),
        ("700.HK", "HK.00700"),
    ],
)
def test_e12_futu_wire_symbols_remain_provider_specific(raw: str, expected: str) -> None:
    assert _hk_symbol(raw) == expected


def test_e12_canonical_identity_is_not_provider_wire_identity() -> None:
    canonical = normalize_stock_code("HK00700")
    assert canonical == "HK00700"
    assert YfinanceFetcher()._convert_stock_code(canonical) == "0700.HK"
    assert _hk_symbol(canonical) == "HK.00700"
