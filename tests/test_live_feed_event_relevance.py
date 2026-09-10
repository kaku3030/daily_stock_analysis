from datetime import datetime, timezone

import pytest

from data_provider.live_feed_types import (
    FailureClass,
    LifecycleState,
    ProviderEvent,
    ProviderEventKind,
)
from src.services.live_feed.commands import FakeProviderCommandExecutor
from src.services.live_feed.controller import LiveFeedController


def _fixed_now():
    return datetime(2026, 9, 9, 10, 0, 0, tzinfo=timezone.utc)


def _controller() -> LiveFeedController:
    return LiveFeedController(
        runtime_instance_id="runtime-current",
        provider_id="futu",
        command_executor=FakeProviderCommandExecutor(),
        now_utc=_fixed_now,
    )


def _connected_event(**overrides) -> ProviderEvent:
    fields = dict(
        runtime_instance_id="runtime-current",
        provider_id="futu",
        controller_generation=0,
        observed_at_utc=_fixed_now(),
        observed_at_monotonic=1.0,
        event_kind=ProviderEventKind.CONNECTED,
    )
    fields.update(overrides)
    return ProviderEvent(**fields)


def _disconnected_event(**overrides) -> ProviderEvent:
    fields = dict(
        runtime_instance_id="runtime-current",
        provider_id="futu",
        controller_generation=0,
        observed_at_utc=_fixed_now(),
        observed_at_monotonic=1.0,
        event_kind=ProviderEventKind.DISCONNECTED,
    )
    fields.update(overrides)
    return ProviderEvent(**fields)


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"runtime_instance_id": "runtime-old"}, "RUNTIME_INSTANCE_MISMATCH"),
        ({"provider_id": "other-provider"}, "PROVIDER_MISMATCH"),
        ({"controller_generation": 99}, "CONTROLLER_GENERATION_MISMATCH"),
    ],
)
def test_case6_identity_mismatch_cannot_advance_lifecycle(overrides, reason) -> None:
    """Frozen adversarial Case 6: stale/foreign provider evidence may be
    retained diagnostically but cannot advance controller truth.
    """

    controller = _controller()
    result = controller.submit_event(_connected_event(**overrides))
    assert result.accepted

    controller.process_pending()
    snapshot = controller.snapshot()

    assert snapshot.lifecycle_state is LifecycleState.DISCONNECTED
    assert any("STALE_PROVIDER_EVENT" in finding and reason in finding for finding in snapshot.findings)


def test_stale_generation_disconnected_cannot_degrade_established_connected_truth() -> None:
    """Relevance-gate regression: once CONNECTED has been legitimately
    established, a DISCONNECTED carrying a non-current controller
    generation must be rejected as stale evidence rather than degrading
    lifecycle truth back to RECONNECTING.

    Test-fidelity NOTE: Slice 1 exposes no public production
    generation-advance mechanism, so there is no way to construct a
    genuine "generation 1 reconnect vs. stale generation 0" race here.
    ``current_generation - 1`` is used only as an abstract stand-in for
    "a generation that is not current" to exercise the relevance gate --
    it does not model a real reconnect lifecycle, and this test makes no
    claim that it does. Full reconnect-generation coverage remains
    outside this Slice.
    """

    controller = _controller()

    # Step 1-2: establish legitimate CONNECTED via a valid-identity event.
    result = controller.submit_event(_connected_event())
    assert result.accepted
    controller.process_pending()
    snapshot = controller.snapshot()
    assert snapshot.lifecycle_state is LifecycleState.CONNECTED

    # Step 3: read back the controller's current generation.
    current_generation = snapshot.controller_generation

    # Step 4: derive a generation that is explicitly not current. Abstract
    # stand-in only -- see the NOTE above.
    stale_generation = current_generation - 1

    # Step 5: submit DISCONNECTED carrying that stale generation.
    result = controller.submit_event(_disconnected_event(controller_generation=stale_generation))
    assert result.accepted
    controller.process_pending()
    snapshot = controller.snapshot()

    # Lifecycle stays CONNECTED -- does not degrade to RECONNECTING.
    assert snapshot.lifecycle_state is LifecycleState.CONNECTED
    assert snapshot.lifecycle_state is not LifecycleState.RECONNECTING

    stale_findings = [f for f in snapshot.findings if "STALE_PROVIDER_EVENT" in f]
    assert len(stale_findings) == 1
    assert "CONTROLLER_GENERATION_MISMATCH" in stale_findings[0]
    assert "kind=DISCONNECTED" in stale_findings[0]

    # No unrelated authoritative state changed as a side effect.
    assert snapshot.failure_class is FailureClass.UNKNOWN
    assert snapshot.stop_requested is False


def test_current_identity_connected_is_accepted_not_flagged_as_stale() -> None:
    """Positive control for the relevance gate: an event carrying the
    controller's exact current runtime_instance_id, provider_id, and
    controller_generation must be accepted and must never be
    misclassified as STALE_PROVIDER_EVENT -- proving the gate rejects
    mismatches without blocking legitimate callbacks.
    """

    controller = _controller()
    current_generation = controller.snapshot().controller_generation

    result = controller.submit_event(
        _connected_event(
            runtime_instance_id="runtime-current",
            provider_id="futu",
            controller_generation=current_generation,
        )
    )
    assert result.accepted

    controller.process_pending()
    snapshot = controller.snapshot()

    assert snapshot.lifecycle_state is LifecycleState.CONNECTED
    assert not any("STALE_PROVIDER_EVENT" in finding for finding in snapshot.findings)
