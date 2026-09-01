import pytest

from src.services.stock_radar_v2.notifications import SUPPORTED_EVENT_TYPES, RadarNotifier, notify


def test_unified_notify_supports_all_mvp_event_types() -> None:
    received = []
    notifier = RadarNotifier(received.append)

    for event_type in sorted(SUPPORTED_EVENT_TYPES):
        event = notifier.notify(event_type, {"research_only": True})
        assert event.event_type == event_type

    assert {event.event_type for event in received} == SUPPORTED_EVENT_TYPES


def test_unified_notify_rejects_unknown_event_type() -> None:
    with pytest.raises(ValueError, match="unsupported"):
        RadarNotifier().notify("buy_order_alert", {})


def test_functional_notify_uses_the_same_boundary() -> None:
    received = []
    event = notify(
        "confirmed_signal_alert",
        {"signal_state": "confirmed"},
        notifier=RadarNotifier(received.append),
    )
    assert received == [event]
