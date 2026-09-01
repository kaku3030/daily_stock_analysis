from datetime import datetime, timezone

import pandas as pd
import pytest

from data_provider.market_data_adapter import SignalPermission
from data_provider.xtquant_market_data_adapter import XtquantMarketDataAdapter, normalize_xtquant_symbol


NOW = datetime(2026, 9, 1, 2, 0, tzinfo=timezone.utc)


class FakeXtdata:
    def __init__(self):
        self.history = {}
        self.tick = {}
        self.subscriptions = []
        self.unsubscribed = []
        self.next_ids = [1]

    def get_market_data_ex(self, *args, **kwargs):
        self.history_call = (args, kwargs)
        return self.history

    def get_full_tick(self, codes):
        return self.tick

    def subscribe_quote(self, code, period="1d", count=0, callback=None):
        subscription_id = self.next_ids.pop(0)
        self.subscriptions.append((code, period, count, callback))
        return subscription_id

    def unsubscribe_quote(self, subscription_id):
        self.unsubscribed.append(subscription_id)


def test_xtquant_symbol_normalization() -> None:
    assert normalize_xtquant_symbol("600519") == "600519.SH"
    assert normalize_xtquant_symbol("SZ000001") == "000001.SZ"
    assert normalize_xtquant_symbol("000001.SZ") == "000001.SZ"
    with pytest.raises(ValueError):
        normalize_xtquant_symbol("NVDA")


def test_xtquant_history_preserves_epoch_timestamp_and_requests_raw_1m() -> None:
    xtdata = FakeXtdata()
    xtdata.history = {
        "600519.SH": pd.DataFrame(
            [{"time": 1788227940000, "open": 10, "high": 11, "low": 9, "close": 10.5, "volume": 100, "amount": 1050}]
        )
    }
    adapter = XtquantMarketDataAdapter(xtdata, now=lambda: NOW)

    bars = adapter.get_bars("600519", "1m", limit=20)

    assert len(bars) == 1
    assert bars[0].bar_start.tzinfo is not None
    args, kwargs = xtdata.history_call
    assert args[:2] == ([], ["600519.SH"])
    assert kwargs["period"] == "1m"
    assert kwargs["fill_data"] is False
    assert kwargs["count"] == 20


def test_xtquant_quote_uses_provider_timestamp() -> None:
    xtdata = FakeXtdata()
    xtdata.tick = {
        "600519.SH": {
            "time": 1788227999000,
            "lastPrice": 10,
            "bidPrice": [9.9],
            "askPrice": [10.1],
            "volume": 100,
        }
    }
    adapter = XtquantMarketDataAdapter(xtdata, now=lambda: NOW, session_resolver=lambda _: "regular")

    quote = adapter.get_latest_quote("600519")

    assert quote.provider == "xtquant"
    assert quote.bid == 9.9
    assert "MISSING_SOURCE_TIMESTAMP" not in quote.quality_flags
    assert quote.health.signal_permission is SignalPermission.NORMAL


def test_xtquant_subscription_normalizes_callback_rows() -> None:
    xtdata = FakeXtdata()
    adapter = XtquantMarketDataAdapter(xtdata, now=lambda: NOW)
    received = []

    adapter.subscribe(["600519"], callback=received.append)
    callback = xtdata.subscriptions[0][3]
    callback(
        {
            "600519.SH": [
                {"time": 1788227940000, "open": 10, "high": 11, "low": 9, "close": 10.5, "volume": 100}
            ]
        }
    )

    assert xtdata.subscriptions[0][:3] == ("600519.SH", "1m", 0)
    assert len(received) == 1
    assert received[0].symbol == "600519.SH"
    assert received[0].timeframe == "1m"


def test_partial_subscription_failure_unsubscribes_created_ids() -> None:
    xtdata = FakeXtdata()
    xtdata.next_ids = [11, -1]
    adapter = XtquantMarketDataAdapter(xtdata, now=lambda: NOW)

    with pytest.raises(RuntimeError, match="subscription failed"):
        adapter.subscribe(["600519", "000001"], callback=lambda _: None)

    assert xtdata.unsubscribed == [11]
