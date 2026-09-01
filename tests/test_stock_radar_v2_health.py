from datetime import datetime, timedelta, timezone

import pytest

from src.services.stock_radar_v2.config import load_stock_radar_config
from src.services.stock_radar_v2.health import FailureKind, FallbackStateMachine, ProviderMode
from src.services.stock_radar_v2.notifications import RadarNotifier


NOW = datetime(2026, 9, 1, tzinfo=timezone.utc)


def _machine():
    events = []
    machine = FallbackStateMachine(
        load_stock_radar_config(),
        notifier=RadarNotifier(events.append),
        primary_name="qmt",
        fallback_name="pytdx",
    )
    return machine, events


def test_three_failures_enter_fallback_once() -> None:
    machine, events = _machine()

    assert machine.record_failure(FailureKind.OTHER, observed_at=NOW).mode is ProviderMode.PRIMARY
    assert machine.record_failure(FailureKind.OTHER, observed_at=NOW).mode is ProviderMode.PRIMARY
    decision = machine.record_failure(FailureKind.OTHER, observed_at=NOW)

    assert decision.mode is ProviderMode.FALLBACK
    assert decision.transitioned is True
    assert [event.event_type for event in events] == ["provider_fallback_alert"]


def test_recovery_requires_cooldown_and_three_spaced_successes() -> None:
    machine, _ = _machine()
    for _ in range(3):
        machine.record_failure(FailureKind.OTHER, observed_at=NOW)

    too_early = machine.record_recovery_probe(True, observed_at=NOW + timedelta(seconds=299))
    assert too_early.accepted is False
    assert machine.mode is ProviderMode.FALLBACK

    for offset in (300, 360):
        decision = machine.record_recovery_probe(True, observed_at=NOW + timedelta(seconds=offset))
        assert decision.mode is ProviderMode.FALLBACK
    recovered = machine.record_recovery_probe(True, observed_at=NOW + timedelta(seconds=420))

    assert recovered.transitioned is True
    assert recovered.mode is ProviderMode.PRIMARY


def test_failed_recovery_probe_resets_success_streak() -> None:
    machine, _ = _machine()
    for _ in range(3):
        machine.record_failure(FailureKind.OTHER, observed_at=NOW)
    machine.record_recovery_probe(True, observed_at=NOW + timedelta(seconds=300))
    machine.record_recovery_probe(False, observed_at=NOW + timedelta(seconds=360))

    decision = machine.record_recovery_probe(True, observed_at=NOW + timedelta(seconds=420))

    assert decision.reason == "recovery_success=1"
    assert machine.mode is ProviderMode.FALLBACK


def test_five_consecutive_timeouts_over_five_seconds_are_critical() -> None:
    machine, events = _machine()
    for index in range(5):
        decision = machine.record_failure(
            FailureKind.TIMEOUT,
            observed_at=NOW + timedelta(seconds=index),
            elapsed_seconds=5.01,
        )

    assert decision.critical is True
    assert "timeout>5s_count=5" in decision.reason
    assert [event.event_type for event in events].count("data_health_alert") == 1


def test_timeout_at_exactly_five_seconds_is_not_severe_timeout() -> None:
    machine, _ = _machine()
    for index in range(5):
        decision = machine.record_failure(
            FailureKind.TIMEOUT,
            observed_at=NOW + timedelta(seconds=index),
            elapsed_seconds=5.0,
        )
    assert decision.critical is False


@pytest.mark.parametrize("sequence", [
    [FailureKind.EMPTY, FailureKind.EMPTY, FailureKind.EMPTY],
    [FailureKind.EMPTY, FailureKind.PARSE, FailureKind.EMPTY],
])
def test_three_consecutive_empty_or_parse_failures_are_critical(sequence) -> None:
    machine, _ = _machine()
    for kind in sequence:
        decision = machine.record_failure(kind, observed_at=NOW)
    assert decision.critical is True
    assert decision.reason == "empty_or_parse_count=3"


@pytest.mark.parametrize(
    "kind",
    [FailureKind.CONNECTION, FailureKind.AUTH, FailureKind.SUBSCRIPTION],
)
def test_explicit_provider_errors_are_immediately_critical(kind) -> None:
    machine, _ = _machine()
    decision = machine.record_failure(kind, observed_at=NOW, error_code="E401")
    assert decision.critical is True
    assert decision.mode is ProviderMode.FALLBACK
    assert "E401" in decision.reason


@pytest.mark.parametrize(
    "sequence",
    [
        [FailureKind.CLOSED_BAR_MISSING, FailureKind.CLOSED_BAR_MISSING],
        [FailureKind.TIMESTAMP_MISMATCH, FailureKind.SESSION_MISMATCH],
    ],
)
def test_two_consecutive_closed_bar_integrity_failures_are_critical(sequence) -> None:
    machine, _ = _machine()
    for kind in sequence:
        decision = machine.record_failure(kind, observed_at=NOW)
    assert decision.critical is True
    assert decision.reason == "closed_bar_integrity_count=2"


def test_success_resets_consecutive_failure_streaks() -> None:
    machine, _ = _machine()
    machine.record_failure(FailureKind.EMPTY, observed_at=NOW)
    machine.record_failure(FailureKind.EMPTY, observed_at=NOW)
    machine.record_success()
    decision = machine.record_failure(FailureKind.EMPTY, observed_at=NOW)
    assert decision.critical is False
    assert machine.empty_parse_streak == 1
