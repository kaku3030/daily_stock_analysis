from src.services.stock_radar_v2.notifications import RadarNotifier
from src.services.stock_radar_v2.runtime_notifications import NotificationServiceRadarSink


class FakeNotificationService:
    def __init__(self) -> None:
        self.calls = []

    def send_with_results(self, content, **kwargs):
        self.calls.append((content, kwargs))
        return ["sent"]


def test_runtime_sink_uses_existing_alert_route_and_research_only_payload() -> None:
    service = FakeNotificationService()
    sink = NotificationServiceRadarSink(service)

    RadarNotifier(sink).notify(
        "signal_qa_alert",
        {"signal_type": "breakout", "review_id": "review-1", "failure_count": 7},
    )

    content, kwargs = service.calls[0]
    assert kwargs["route_type"] == "alert"
    assert kwargs["severity"] == "warning"
    assert kwargs["dedup_key"] == "stock_radar_v2:signal_qa_alert:breakout:7"
    assert kwargs["cooldown_key"] == "stock_radar_v2:signal_qa_alert:breakout:warning"
    assert kwargs["structured_payload"]["research_only"] is True
    assert "不是买卖建议或交易指令" in content


def test_critical_health_event_maps_to_critical_severity() -> None:
    service = FakeNotificationService()
    RadarNotifier(NotificationServiceRadarSink(service)).notify(
        "data_health_alert",
        {"provider": "primary", "reason": "authentication_error"},
    )

    assert service.calls[0][1]["severity"] == "critical"


def test_runtime_sink_is_fail_open_when_notification_service_raises() -> None:
    class BrokenNotificationService:
        def send_with_results(self, content, **kwargs):
            raise RuntimeError("channel unavailable")

    sink = NotificationServiceRadarSink(BrokenNotificationService())

    RadarNotifier(sink).notify("provider_fallback_alert", {"provider": "primary"})

    assert sink.last_error == "channel unavailable"
