# -*- coding: utf-8 -*-
"""Tests for research-priority notification adapter."""

from dataclasses import dataclass

from src.services.screening.research_priority_notifications import (
    dispatch_research_priority_alerts,
    format_research_priority_alert,
)


@dataclass
class FakeChannelResult:
    channel: str = "telegram"
    success: bool = True
    error_code: str | None = None
    retryable: bool = False


@dataclass
class FakeDispatch:
    dispatched: bool = True
    success: bool = True
    status: str = "sent"
    message: str | None = None
    channel_results: list | None = None


class FakeNotifier:
    def __init__(self) -> None:
        self.calls = []

    def send_with_results(self, content, **kwargs):
        self.calls.append((content, kwargs))
        return FakeDispatch(channel_results=[FakeChannelResult()])


def _alert(code="NVDA", severity="critical"):
    return {
        "code": code,
        "name": "NVIDIA",
        "severity": severity,
        "transition_type": "tone_flip",
        "previous_priority": "high",
        "current_priority": "urgent",
        "previous_event_type": "positive_convergence",
        "current_event_type": "financial_risk",
        "previous_tone": "positive_watch",
        "current_tone": "risk_review",
        "priority_score": 84,
        "financial_attention": "high",
        "guidance_changed": False,
        "reason": "研究倾向发生反转",
        "reasons": ["盈利趋势 deteriorating", "行业强度 82"],
    }


def test_format_research_alert_keeps_research_boundary() -> None:
    text = format_research_priority_alert(_alert())

    assert "NVDA" in text
    assert "high → urgent" in text
    assert "不是买卖建议或交易指令" in text
    assert "止损" not in text
    assert "目标价" not in text


def test_dispatch_uses_existing_alert_route_and_severity() -> None:
    notifier = FakeNotifier()

    results = dispatch_research_priority_alerts(
        [_alert()],
        market="us",
        run_id="run-2",
        notifier=notifier,
    )

    assert len(results) == 1
    assert results[0]["success"] is True
    assert len(notifier.calls) == 1
    _, kwargs = notifier.calls[0]
    assert kwargs["route_type"] == "alert"
    assert kwargs["severity"] == "critical"
    assert kwargs["email_stock_codes"] == ["NVDA"]
    assert "run-2" in kwargs["dedup_key"]


def test_dispatch_caps_alert_count() -> None:
    notifier = FakeNotifier()
    alerts = [_alert(code=f"T{i}", severity="warning") for i in range(8)]

    results = dispatch_research_priority_alerts(
        alerts,
        run_id="run-3",
        max_alerts=3,
        notifier=notifier,
    )

    assert len(results) == 3
    assert len(notifier.calls) == 3


def test_dispatch_is_fail_open_on_notifier_exception() -> None:
    class BrokenNotifier:
        def send_with_results(self, content, **kwargs):
            raise RuntimeError("channel unavailable")

    results = dispatch_research_priority_alerts(
        [_alert()],
        notifier=BrokenNotifier(),
    )

    assert results[0]["success"] is False
    assert results[0]["status"] == "dispatch_exception"
