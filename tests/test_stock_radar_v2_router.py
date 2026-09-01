from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from data_provider.market_data_adapter import Quote, evaluate_health
from src.services.stock_radar_v2.health import FallbackStateMachine, ProviderMode
from src.services.stock_radar_v2.router import DebouncedMarketDataRouter


NOW = datetime(2026, 9, 1, tzinfo=timezone.utc)
HEALTH = evaluate_health(
    freshness=1,
    completeness=1,
    timestamp=1,
    provider=1,
    continuity=1,
    cross_check=1,
)


def _quote(provider: str) -> Quote:
    return Quote(
        symbol="NVDA",
        market="us",
        asset_type="stock",
        price=100,
        provider=provider,
        source_timestamp=NOW,
        received_at=NOW,
        session="regular",
        health=HEALTH,
    )


def _adapter(quote) -> MagicMock:
    adapter = MagicMock()
    if isinstance(quote, list):
        adapter.get_latest_quote.side_effect = quote
    else:
        adapter.get_latest_quote.return_value = quote
    adapter.get_provider_health.return_value = HEALTH
    adapter.get_session_status.return_value = "regular"
    return adapter


def test_router_does_not_fallback_before_third_failure() -> None:
    primary = _adapter([LookupError("empty"), LookupError("empty"), LookupError("empty")])
    fallback = _adapter(_quote("fallback"))
    state = FallbackStateMachine()
    router = DebouncedMarketDataRouter(primary, fallback, state, now=lambda: NOW)

    with pytest.raises(LookupError):
        router.get_latest_quote("NVDA")
    with pytest.raises(LookupError):
        router.get_latest_quote("NVDA")
    result = router.get_latest_quote("NVDA")

    assert result.provider == "fallback"
    assert result.fallback_from == "primary"
    assert result.fallback_reason == "empty_or_parse_count=3"
    assert "FALLBACK_PROVIDER" in result.quality_flags
    assert state.mode is ProviderMode.FALLBACK
    assert fallback.get_latest_quote.call_count == 1


def test_router_fails_back_immediately_on_connection_error() -> None:
    primary = _adapter([ConnectionError("offline")])
    fallback = _adapter(_quote("fallback"))
    state = FallbackStateMachine()
    router = DebouncedMarketDataRouter(primary, fallback, state, now=lambda: NOW)

    assert router.get_latest_quote("NVDA").provider == "fallback"
    assert state.critical is True


def test_router_returns_to_primary_after_three_recovery_probes() -> None:
    current = [NOW]
    primary = _adapter(
        [
            LookupError("empty"),
            LookupError("empty"),
            LookupError("empty"),
            _quote("primary"),
            _quote("primary"),
            _quote("primary"),
        ]
    )
    fallback = _adapter(_quote("fallback"))
    state = FallbackStateMachine()
    router = DebouncedMarketDataRouter(primary, fallback, state, now=lambda: current[0])
    for _ in range(2):
        with pytest.raises(LookupError):
            router.get_latest_quote("NVDA")
    assert router.get_latest_quote("NVDA").provider == "fallback"

    for offset in (300, 360):
        current[0] = NOW + timedelta(seconds=offset)
        assert router.get_latest_quote("NVDA").provider == "fallback"
    current[0] = NOW + timedelta(seconds=420)

    assert router.get_latest_quote("NVDA").provider == "primary"
    assert state.mode is ProviderMode.PRIMARY


def test_stream_subscription_error_is_visible_and_never_polls_fallback() -> None:
    primary = _adapter(_quote("primary"))
    fallback = _adapter(_quote("fallback"))
    primary.subscribe.side_effect = RuntimeError("subscription rejected")
    state = FallbackStateMachine()
    router = DebouncedMarketDataRouter(primary, fallback, state, now=lambda: NOW)

    with pytest.raises(RuntimeError, match="subscription rejected"):
        router.subscribe(["NVDA"], callback=lambda bar: None)

    assert state.critical is True
    fallback.subscribe.assert_not_called()
