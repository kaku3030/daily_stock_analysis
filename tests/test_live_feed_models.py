from dataclasses import FrozenInstanceError
from datetime import datetime, timezone

import pytest

from data_provider.live_feed_types import (
    DeliveryMode,
    FailureClass,
    LifecycleState,
    ProviderEvent,
    ProviderEventKind,
    SemanticStreamKey,
)
from src.services.live_feed.identity import ControllerGeneration, new_runtime_instance_id


def _key(**overrides) -> SemanticStreamKey:
    fields = dict(provider_id="futu", market="HK", symbol="HK.00700", stream_type="QUOTE")
    fields.update(overrides)
    return SemanticStreamKey(**fields)


def test_semantic_stream_key_equality_and_hash_for_identical_fields() -> None:
    a = _key()
    b = _key()
    assert a == b
    assert hash(a) == hash(b)


@pytest.mark.parametrize(
    "field_name,override",
    [
        ("provider_id", "xtquant"),
        ("market", "US"),
        ("symbol", "HK.09988"),
        ("stream_type", "K_1M"),
        ("timeframe", "1m"),
        ("session_mode", "PRE_MARKET"),
        ("adjustment_mode", "FORWARD"),
        ("feed", "BASIC"),
    ],
)
def test_semantic_stream_key_differs_by_each_semantics_affecting_field(field_name, override) -> None:
    baseline = _key()
    changed = _key(**{field_name: override})
    assert baseline != changed
    assert hash(baseline) != hash(changed)


def test_runtime_instance_id_unique_per_call() -> None:
    ids = {new_runtime_instance_id() for _ in range(100)}
    assert len(ids) == 100


def test_controller_generation_independent_of_provider_diagnostic_conn_id() -> None:
    # controller_generation is a controller-owned value object -- advancing
    # it has nothing to do with any provider-supplied identifier (e.g. a
    # Futu-internal conn_id) and starts from a fixed, controller-local origin.
    gen = ControllerGeneration.initial()
    assert gen.value == 0
    advanced = gen.advance()
    assert advanced.value == 1
    # original is unchanged (immutable value object)
    assert gen.value == 0
    provider_conn_id = 89  # e.g. Futu's own internal counter, per FUTU_SEMANTIC_CONTRACT_V0_1.md
    assert advanced.value != provider_conn_id


def test_provider_event_is_immutable() -> None:
    event = ProviderEvent(
        runtime_instance_id="r1",
        provider_id="futu",
        controller_generation=0,
        observed_at_utc=datetime.now(timezone.utc),
        observed_at_monotonic=1.0,
        event_kind=ProviderEventKind.DATA,
    )
    with pytest.raises(FrozenInstanceError):
        event.event_kind = ProviderEventKind.ERROR  # type: ignore[misc]


def test_delivery_mode_default_is_unknown() -> None:
    event = ProviderEvent(
        runtime_instance_id="r1",
        provider_id="futu",
        controller_generation=0,
        observed_at_utc=datetime.now(timezone.utc),
        observed_at_monotonic=1.0,
        event_kind=ProviderEventKind.DATA,
    )
    assert event.delivery_mode is DeliveryMode.UNKNOWN


def test_lifecycle_state_enum_matches_frozen_contract_state_machine() -> None:
    assert {s.value for s in LifecycleState} == {
        "DISCONNECTED",
        "CONNECTING",
        "CONNECTED",
        "SUBSCRIBING",
        "LIVE",
        "DEGRADED",
        "RECONNECTING",
        "FAILED",
    }


def test_failure_class_kept_separate_from_lifecycle_state() -> None:
    assert set(FailureClass) != set(LifecycleState)
    assert {f.value for f in FailureClass} == {"TRANSIENT", "REQUIRES_INTERVENTION", "UNKNOWN"}
