from datetime import datetime, timezone

import pytest

from data_provider.market_data_adapter import (
    Bar,
    HealthGrade,
    MarketDataAdapter,
    SignalPermission,
    evaluate_health,
)


def test_health_gate_maps_v1_thresholds() -> None:
    excellent = evaluate_health(
        freshness=1,
        completeness=1,
        timestamp=1,
        provider=1,
        continuity=1,
        cross_check=1,
    )
    degraded = evaluate_health(
        freshness=0.8,
        completeness=0.8,
        timestamp=0.8,
        provider=0.8,
        continuity=0.5,
        cross_check=0.5,
    )
    unstable = evaluate_health(
        freshness=0.6,
        completeness=0.6,
        timestamp=0.6,
        provider=0.6,
        continuity=0.6,
        cross_check=0.6,
    )

    assert (excellent.score, excellent.grade, excellent.signal_permission) == (
        100,
        HealthGrade.EXCELLENT,
        SignalPermission.NORMAL,
    )
    assert (degraded.score, degraded.grade, degraded.signal_permission) == (
        74,
        HealthGrade.DEGRADED,
        SignalPermission.WATCH_ONLY,
    )
    assert (unstable.score, unstable.grade, unstable.signal_permission) == (
        60,
        HealthGrade.UNSTABLE,
        SignalPermission.RECORD_ONLY,
    )


def test_severe_fact_integrity_flag_blocks_signals() -> None:
    health = evaluate_health(
        freshness=1,
        completeness=1,
        timestamp=1,
        provider=1,
        continuity=1,
        cross_check=1,
        quality_flags=["timestamp_mismatch", "timestamp_mismatch"],
    )

    assert health.score == 49
    assert health.grade is HealthGrade.INVALID
    assert health.signal_permission is SignalPermission.BLOCKED
    assert health.quality_flags == ("TIMESTAMP_MISMATCH",)


def test_incomplete_or_stale_fact_cannot_produce_normal_signal() -> None:
    health = evaluate_health(
        freshness=1,
        completeness=1,
        timestamp=1,
        provider=1,
        continuity=1,
        cross_check=1,
        quality_flags=["missing_bar"],
    )

    assert health.score == 79
    assert health.signal_permission is SignalPermission.WATCH_ONLY


def test_health_components_reject_out_of_range_values() -> None:
    with pytest.raises(ValueError, match="freshness"):
        evaluate_health(
            freshness=1.1,
            completeness=1,
            timestamp=1,
            provider=1,
            continuity=1,
            cross_check=1,
        )


def test_bar_keeps_facts_separate_from_indicator_features() -> None:
    timestamp = datetime(2026, 9, 1, 1, 30, tzinfo=timezone.utc)
    bar = Bar(
        symbol="NVDA",
        market="us",
        asset_type="stock",
        timeframe="15m",
        bar_start=timestamp,
        bar_end=timestamp,
        open=180.0,
        high=182.0,
        low=179.0,
        close=181.0,
        volume=1000,
        provider="alpaca",
        feed="iex",
        source_timestamp=timestamp,
        received_at=timestamp,
        session="regular",
        is_closed=True,
        is_complete=True,
    )

    assert bar.feed == "iex"
    assert not hasattr(bar, "macd")
    assert not hasattr(bar, "rsi")


def test_adapter_is_an_interface_not_a_provider_implementation() -> None:
    with pytest.raises(TypeError):
        MarketDataAdapter()
