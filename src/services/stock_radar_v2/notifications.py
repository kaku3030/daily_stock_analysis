"""Single notification boundary for Stock Radar V2 events."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Mapping


SUPPORTED_EVENT_TYPES = frozenset(
    {
        "data_health_alert",
        "provider_fallback_alert",
        "signal_qa_alert",
        "portfolio_risk_alert",
        "confirmed_signal_alert",
    }
)


@dataclass(frozen=True)
class RadarNotification:
    event_type: str
    payload: Mapping[str, Any]
    created_at: datetime


class RadarNotifier:
    """Validate and dispatch typed events through one callable sink."""

    def __init__(self, sink: Callable[[RadarNotification], None] | None = None) -> None:
        self._sink = sink

    def notify(self, event_type: str, payload: Mapping[str, Any]) -> RadarNotification:
        normalized = str(event_type).strip()
        if normalized not in SUPPORTED_EVENT_TYPES:
            raise ValueError(f"unsupported Stock Radar event type: {event_type}")
        event = RadarNotification(
            event_type=normalized,
            payload=dict(payload),
            created_at=datetime.now(timezone.utc),
        )
        if self._sink is not None:
            self._sink(event)
        return event


def notify(
    event_type: str,
    payload: Mapping[str, Any],
    *,
    notifier: RadarNotifier | None = None,
) -> RadarNotification:
    """Unified functional entry point used by Stock Radar integrations."""

    return (notifier or RadarNotifier()).notify(event_type, payload)
