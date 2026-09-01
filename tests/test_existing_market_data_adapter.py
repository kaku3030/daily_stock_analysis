from datetime import datetime, timezone
from types import SimpleNamespace

import pandas as pd
import pytest

from data_provider.existing_market_data_adapter import ExistingMarketDataAdapter
from data_provider.market_data_adapter import HealthGrade, SignalPermission


NOW = datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc)


class FakeManager:
    def __init__(self, quote=None, frame=None):
        self.quote = quote
        self.frame = frame

    def get_realtime_quote(self, symbol, *, log_final_failure=True):
        assert log_final_failure is False
        return self.quote

    def get_daily_data(self, symbol, start_date=None, end_date=None, days=30):
        return self.frame, "fake-provider"


def test_existing_quote_is_normalized_with_source_timestamp() -> None:
    manager = FakeManager(
        quote=SimpleNamespace(
            price=181.5,
            volume=100,
            amount=18150,
            source=SimpleNamespace(value="fake"),
            market="us",
            fetched_at="2026-09-01T12:00:00Z",
            provider_timestamp="2026-09-01T11:59:59Z",
            is_stale=False,
            missing_fields=[],
            fallback_from=None,
        )
    )
    adapter = ExistingMarketDataAdapter(manager, now=lambda: NOW, session_resolver=lambda _: "regular")

    quote = adapter.get_latest_quote("NVDA")

    assert quote.price == 181.5
    assert quote.provider == "fake"
    assert quote.source_timestamp.isoformat() == "2026-09-01T11:59:59+00:00"
    assert quote.session == "regular"
    assert quote.health.signal_permission is SignalPermission.NORMAL


def test_stale_quote_cannot_produce_normal_signal() -> None:
    manager = FakeManager(
        quote=SimpleNamespace(
            price=10,
            source="fallback",
            market="cn",
            fetched_at="2026-09-01T12:00:00Z",
            provider_timestamp="2026-09-01T11:00:00Z",
            is_stale=True,
            missing_fields=[],
            fallback_from="primary",
        )
    )
    adapter = ExistingMarketDataAdapter(manager, now=lambda: NOW)

    quote = adapter.get_latest_quote("600519")

    assert "STALE" in quote.quality_flags
    assert quote.health.signal_permission is SignalPermission.WATCH_ONLY


def test_daily_bars_preserve_dates_and_reject_invalid_ohlc_for_signals() -> None:
    frame = pd.DataFrame(
        [
            {"date": "2026-08-31", "open": 10, "high": 12, "low": 9, "close": 11, "volume": 100},
            {"date": "2026-09-01", "open": 15, "high": 12, "low": 9, "close": 11, "volume": 100},
        ]
    )
    adapter = ExistingMarketDataAdapter(FakeManager(frame=frame), now=lambda: NOW)

    bars = adapter.get_bars("600519", "1d", limit=2)

    assert [bar.bar_start.date().isoformat() for bar in bars] == ["2026-08-31", "2026-09-01"]
    assert bars[0].health.grade is HealthGrade.EXCELLENT
    assert bars[1].health.signal_permission is SignalPermission.BLOCKED
    assert "INVALID_OHLC" in bars[1].quality_flags


def test_bridge_does_not_fake_intraday_or_streaming_support() -> None:
    adapter = ExistingMarketDataAdapter(FakeManager(frame=pd.DataFrame()), now=lambda: NOW)

    with pytest.raises(NotImplementedError, match="daily bars only"):
        adapter.get_bars("NVDA", "15m")
    with pytest.raises(NotImplementedError, match="does not emulate streaming"):
        adapter.subscribe(["NVDA"])


def test_suffix_markets_use_canonical_market_names() -> None:
    frame = pd.DataFrame(
        [{"date": "2026-09-01", "open": 10, "high": 12, "low": 9, "close": 11, "volume": 100}]
    )
    adapter = ExistingMarketDataAdapter(FakeManager(frame=frame), now=lambda: NOW)

    assert adapter.get_bars("7203.T", "1d")[0].market == "jp"
    assert adapter.get_bars("005930.KS", "1d")[0].market == "kr"
    assert adapter.get_bars("2330.TW", "1d")[0].market == "tw"
