from datetime import datetime, timezone

from data_provider.market_data_adapter import (
    Bar,
    MarketDataAdapter,
    Quote,
    evaluate_health,
)
from data_provider.market_data_router import MarketDataRouter


NOW = datetime(2026, 9, 1, tzinfo=timezone.utc)
GOOD = evaluate_health(freshness=1, completeness=1, timestamp=1, provider=1, continuity=1, cross_check=1)
BLOCKED = evaluate_health(
    freshness=1,
    completeness=1,
    timestamp=1,
    provider=1,
    continuity=1,
    cross_check=1,
    quality_flags=["invalid_ohlc"],
)


def quote(provider, health=GOOD):
    return Quote(
        symbol="600519",
        market="cn",
        asset_type="stock",
        price=10,
        provider=provider,
        source_timestamp=NOW,
        received_at=NOW,
        session="regular",
        health=health,
        quality_flags=health.quality_flags,
    )


def bar(provider, health=GOOD):
    return Bar(
        symbol="600519",
        market="cn",
        asset_type="stock",
        timeframe="1m",
        bar_start=NOW,
        bar_end=NOW,
        open=10,
        high=11,
        low=9,
        close=10,
        volume=100,
        provider=provider,
        source_timestamp=NOW,
        received_at=NOW,
        session="regular",
        is_closed=True,
        is_complete=True,
        health=health,
        quality_flags=health.quality_flags,
    )


class FakeAdapter(MarketDataAdapter):
    def __init__(self, *, quote_value=None, bars_value=None, error=None, session="regular"):
        self.quote_value = quote_value
        self.bars_value = bars_value
        self.error = error
        self.session = session
        self.subscribe_calls = []

    def get_latest_quote(self, symbol):
        if self.error:
            raise self.error
        return self.quote_value

    def get_bars(self, symbol, timeframe, start=None, end=None, limit=None):
        if self.error:
            raise self.error
        return self.bars_value

    def subscribe(self, symbols, timeframe="1m", callback=None):
        if self.error:
            raise self.error
        self.subscribe_calls.append((symbols, timeframe, callback))

    def get_session_status(self, market):
        return self.session

    def get_provider_health(self):
        value = self.quote_value or (self.bars_value or [None])[-1]
        return value.health if value else BLOCKED

    def reconnect(self):
        return not bool(self.error)


def test_primary_is_used_when_health_allows_it() -> None:
    primary = FakeAdapter(quote_value=quote("qmt"))
    fallback = FakeAdapter(quote_value=quote("pytdx"))
    router = MarketDataRouter(primary, fallback, primary_name="qmt", fallback_name="pytdx")

    result = router.get_latest_quote("600519")

    assert result.provider == "qmt"
    assert result.fallback_from is None


def test_primary_error_falls_back_with_reason() -> None:
    primary = FakeAdapter(quote_value=quote("qmt"), error=ConnectionError("down"))
    fallback = FakeAdapter(quote_value=quote("pytdx"))
    router = MarketDataRouter(primary, fallback, primary_name="qmt", fallback_name="pytdx")

    result = router.get_latest_quote("600519")

    assert result.provider == "pytdx"
    assert result.fallback_from == "qmt"
    assert result.fallback_reason == "primary_error:ConnectionError"
    assert "FALLBACK_PROVIDER" in result.quality_flags


def test_blocked_primary_bars_fall_back() -> None:
    primary = FakeAdapter(bars_value=[bar("qmt", BLOCKED)])
    fallback = FakeAdapter(bars_value=[bar("pytdx")])
    router = MarketDataRouter(primary, fallback, primary_name="qmt", fallback_name="pytdx")

    result = router.get_bars("600519", "1m")

    assert result[0].provider == "pytdx"
    assert result[0].fallback_reason == "primary_health_blocked"


def test_subscription_never_silently_switches_to_polling_fallback() -> None:
    primary = FakeAdapter(quote_value=quote("qmt"), error=ConnectionError("down"))
    fallback = FakeAdapter(quote_value=quote("pytdx"))
    router = MarketDataRouter(primary, fallback)

    try:
        router.subscribe(["600519"], callback=lambda _: None)
    except ConnectionError:
        pass
    else:
        raise AssertionError("primary subscription failure must remain visible")
    assert fallback.subscribe_calls == []


def test_contract_error_is_not_hidden_by_fallback() -> None:
    primary = FakeAdapter(quote_value=quote("qmt"), error=ValueError("bad normalization"))
    fallback = FakeAdapter(quote_value=quote("pytdx"))
    router = MarketDataRouter(primary, fallback)

    try:
        router.get_latest_quote("600519")
    except ValueError as exc:
        assert "bad normalization" in str(exc)
    else:
        raise AssertionError("contract errors must remain visible")
