from contextlib import contextmanager
from datetime import datetime, timezone

import pandas as pd
import pytest

from data_provider.market_data_adapter import SignalPermission
from data_provider.pytdx_market_data_adapter import PYTDX_1MIN_CATEGORY, PytdxMarketDataAdapter


NOW = datetime(2026, 9, 1, 2, 0, tzinfo=timezone.utc)  # 10:00 Asia/Shanghai


class FakeApi:
    def __init__(self, rows):
        self.rows = rows
        self.calls = []

    def get_security_bars(self, category, market, code, start, count):
        self.calls.append((category, market, code, start, count))
        return self.rows

    def to_df(self, rows):
        return pd.DataFrame(rows)


class FakeFetcher:
    def __init__(self, rows=None, quote=None):
        self.api = FakeApi(rows or [])
        self.quote = quote

    def _get_market_code(self, symbol):
        return 1, symbol

    @contextmanager
    def _pytdx_session(self):
        yield self.api

    def get_realtime_quote(self, symbol):
        return self.quote


def test_pytdx_adapter_preserves_minute_timestamp_and_category() -> None:
    fetcher = FakeFetcher(
        rows=[
            {"datetime": "2026-09-01 09:59", "open": 10, "high": 11, "low": 9, "close": 10.5, "vol": 100, "amount": 1050},
            {"datetime": "2026-09-01 09:58", "open": 9, "high": 10, "low": 8, "close": 9.5, "vol": 80, "amount": 760},
        ]
    )
    adapter = PytdxMarketDataAdapter(fetcher, now=lambda: NOW)

    bars = adapter.get_bars("600519", "1m", limit=100)

    assert fetcher.api.calls == [(PYTDX_1MIN_CATEGORY, 1, "600519", 0, 100)]
    assert [bar.bar_start.strftime("%H:%M") for bar in bars] == ["09:58", "09:59"]
    assert bars[0].bar_start.utcoffset().total_seconds() == 8 * 3600
    assert all(bar.is_closed for bar in bars)


def test_current_minute_is_forming_and_watch_only() -> None:
    fetcher = FakeFetcher(
        rows=[{"datetime": "2026-09-01 10:00", "open": 10, "high": 11, "low": 9, "close": 10.5, "vol": 100}]
    )
    adapter = PytdxMarketDataAdapter(fetcher, now=lambda: NOW)

    bar = adapter.get_bars("600519", "1m")[0]

    assert bar.is_closed is False
    assert bar.is_complete is False
    assert "PARTIAL_BAR" in bar.quality_flags
    assert bar.health.signal_permission is SignalPermission.WATCH_ONLY


def test_pytdx_quote_without_provider_timestamp_is_watch_only() -> None:
    fetcher = FakeFetcher(
        quote={"price": 10, "volume": 100, "amount": 1000, "bid_prices": [9.9], "ask_prices": [10.1]}
    )
    adapter = PytdxMarketDataAdapter(fetcher, now=lambda: NOW, session_resolver=lambda _: "regular")

    quote = adapter.get_latest_quote("600519")

    assert quote.bid == 9.9
    assert quote.ask == 10.1
    assert "MISSING_SOURCE_TIMESTAMP" in quote.quality_flags
    assert quote.health.signal_permission is SignalPermission.WATCH_ONLY


def test_pytdx_adapter_does_not_claim_native_higher_timeframes_or_streaming() -> None:
    adapter = PytdxMarketDataAdapter(FakeFetcher(), now=lambda: NOW)

    with pytest.raises(NotImplementedError, match="raw 1m"):
        adapter.get_bars("600519", "15m")
    with pytest.raises(NotImplementedError, match="does not provide streaming"):
        adapter.subscribe(["600519"])
