from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from src.services.realtime_quote_currentness import (
    QuoteCurrentnessStatus,
    evaluate_quote_currentness,
)


NOW = datetime(2026, 9, 9, 6, 0, 0, tzinfo=timezone.utc)


def _quote(**overrides):
    fields = dict(
        price=100.0,
        change_pct=3.5,
        provider_timestamp=(NOW - timedelta(seconds=10)).isoformat(),
        fetched_at=NOW.isoformat(),
        is_stale=False,
        stale_seconds=10,
        data_quality="ok",
        source="test",
    )
    fields.update(overrides)
    return SimpleNamespace(**fields)


def test_fresh_quote_passes_currentness_only() -> None:
    decision = evaluate_quote_currentness(
        _quote(),
        now_utc=NOW,
        max_age_seconds=60,
    )

    assert decision.currentness_passed is True
    assert decision.status is QuoteCurrentnessStatus.FRESH
    assert decision.reason == "CURRENTNESS_OK"


def test_consumer_owned_max_age_changes_currentness_result() -> None:
    quote = _quote(
        provider_timestamp=(NOW - timedelta(seconds=30)).isoformat(),
        stale_seconds=30,
    )

    strict = evaluate_quote_currentness(quote, now_utc=NOW, max_age_seconds=20)
    lenient = evaluate_quote_currentness(quote, now_utc=NOW, max_age_seconds=60)

    assert strict.currentness_passed is False
    assert strict.status is QuoteCurrentnessStatus.STALE_QUOTE_BLOCKED
    assert lenient.currentness_passed is True
    assert lenient.status is QuoteCurrentnessStatus.FRESH


def test_max_age_policy_must_be_positive() -> None:
    with pytest.raises(ValueError, match="positive"):
        evaluate_quote_currentness(_quote(), now_utc=NOW, max_age_seconds=0)


def test_stale_numeric_quote_cannot_trigger() -> None:
    # Numeric price/change values remain present; currentness must still block.
    decision = evaluate_quote_currentness(
        _quote(
            provider_timestamp=(NOW - timedelta(minutes=5)).isoformat(),
            stale_seconds=300,
        ),
        now_utc=NOW,
        max_age_seconds=60,
    )

    assert decision.currentness_passed is False
    assert decision.status is QuoteCurrentnessStatus.STALE_QUOTE_BLOCKED
    assert decision.reason in {
        "UPSTREAM_STALE_SECONDS_EXCEEDED",
        "PROVIDER_TIMESTAMP_TOO_OLD",
    }


def test_missing_quote_time_cannot_be_promoted_to_fresh() -> None:
    decision = evaluate_quote_currentness(
        _quote(provider_timestamp=None, is_stale=False, stale_seconds=0),
        now_utc=NOW,
        max_age_seconds=60,
    )

    assert decision.currentness_passed is False
    assert decision.status is QuoteCurrentnessStatus.DATA_UNHEALTHY
    assert decision.reason == "MISSING_PROVIDER_TIMESTAMP"


def test_timezone_naive_provider_time_fails_closed() -> None:
    decision = evaluate_quote_currentness(
        _quote(provider_timestamp="2026-09-09T14:00:00"),
        now_utc=NOW,
        max_age_seconds=60,
    )

    assert decision.currentness_passed is False
    assert decision.status is QuoteCurrentnessStatus.DATA_UNHEALTHY
    assert decision.reason == "NAIVE_PROVIDER_TIMESTAMP"


def test_implausibly_future_provider_time_fails_closed() -> None:
    # Protects against provider-local timestamps accidentally being interpreted
    # as UTC (for example an Asia/Shanghai clock shifted roughly +8 hours).
    decision = evaluate_quote_currentness(
        _quote(provider_timestamp=(NOW + timedelta(hours=8)).isoformat()),
        now_utc=NOW,
        max_age_seconds=60,
    )

    assert decision.currentness_passed is False
    assert decision.status is QuoteCurrentnessStatus.DATA_UNHEALTHY
    assert decision.reason == "PROVIDER_TIMESTAMP_IN_FUTURE"


def test_upstream_stale_flag_is_hard_block_even_when_timestamp_looks_fresh() -> None:
    decision = evaluate_quote_currentness(
        _quote(is_stale=True, stale_seconds=1),
        now_utc=NOW,
        max_age_seconds=60,
    )

    assert decision.currentness_passed is False
    assert decision.status is QuoteCurrentnessStatus.STALE_QUOTE_BLOCKED
    assert decision.reason == "UPSTREAM_STALE_FLAG"


@pytest.mark.parametrize("value", ["false", 0, 1])
def test_malformed_upstream_stale_flag_fails_closed(value) -> None:
    decision = evaluate_quote_currentness(
        _quote(is_stale=value),
        now_utc=NOW,
        max_age_seconds=60,
    )

    assert decision.currentness_passed is False
    assert decision.status is QuoteCurrentnessStatus.DATA_UNHEALTHY
    assert decision.reason == "INVALID_UPSTREAM_STALE_FLAG"


def test_unavailable_data_quality_is_hard_block() -> None:
    decision = evaluate_quote_currentness(
        _quote(data_quality="unavailable"),
        now_utc=NOW,
        max_age_seconds=60,
    )

    assert decision.currentness_passed is False
    assert decision.status is QuoteCurrentnessStatus.DATA_UNHEALTHY
    assert decision.reason == "DATA_QUALITY_NOT_ACCEPTED"


@pytest.mark.parametrize("value", [None, "", "unknown", "degraded", "error"])
def test_unknown_or_missing_data_quality_fails_closed(value) -> None:
    decision = evaluate_quote_currentness(
        _quote(data_quality=value),
        now_utc=NOW,
        max_age_seconds=60,
    )

    assert decision.currentness_passed is False
    assert decision.status is QuoteCurrentnessStatus.DATA_UNHEALTHY
    assert decision.reason in {"MISSING_DATA_QUALITY", "DATA_QUALITY_NOT_ACCEPTED"}


def test_partial_data_quality_can_pass_currentness_but_is_not_final_action_authority() -> None:
    decision = evaluate_quote_currentness(
        _quote(data_quality="partial"),
        now_utc=NOW,
        max_age_seconds=60,
    )

    assert decision.currentness_passed is True
    assert decision.data_quality == "partial"


@pytest.mark.parametrize("value", ["bad", float("nan"), float("inf"), -1])
def test_malformed_or_nonfinite_stale_seconds_fails_closed(value) -> None:
    decision = evaluate_quote_currentness(
        _quote(stale_seconds=value),
        now_utc=NOW,
        max_age_seconds=60,
    )

    assert decision.currentness_passed is False
    assert decision.status is QuoteCurrentnessStatus.DATA_UNHEALTHY
    assert decision.reason == "INVALID_UPSTREAM_STALE_SECONDS"


def test_now_utc_must_be_timezone_aware() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        evaluate_quote_currentness(
            _quote(),
            now_utc=datetime(2026, 9, 9, 6, 0, 0),
            max_age_seconds=60,
        )
