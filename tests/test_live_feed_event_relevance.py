from datetime import datetime, timezone

import pytest

from data_provider.live_feed_types import LifecycleState, ProviderEvent, ProviderEventKind
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
