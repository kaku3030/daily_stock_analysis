# -*- coding: utf-8 -*-
"""Tests for research-priority transition notification gating."""

from src.services.screening.research_priority_transition import (
    build_research_priority_alerts,
    evaluate_research_priority_transition,
)


def test_same_high_event_is_suppressed() -> None:
    previous = {
        "priority_level": "high",
        "event_type": "positive_convergence",
        "research_tone": "positive_watch",
    }
    current = {
        **previous,
        "notification_ready": True,
        "priority_score": 70,
    }
    result = evaluate_research_priority_transition(previous, current)
    assert result["notify"] is False


def test_priority_upgrade_is_notified() -> None:
    previous = {
        "priority_level": "normal",
        "event_type": "catalyst_focus",
        "research_tone": "positive_watch",
    }
    current = {
        "priority_level": "high",
        "event_type": "catalyst_focus",
        "research_tone": "positive_watch",
        "notification_ready": True,
    }
    result = evaluate_research_priority_transition(previous, current)
    assert result["notify"] is True
    assert result["transition_type"] == "priority_upgrade"


def test_positive_to_risk_flip_is_critical() -> None:
    previous = {
        "priority_level": "high",
        "event_type": "positive_convergence",
        "research_tone": "positive_watch",
    }
    current = {
        "priority_level": "urgent",
        "event_type": "financial_risk",
        "research_tone": "risk_review",
        "notification_ready": True,
    }
    result = evaluate_research_priority_transition(previous, current)
    assert result["notify"] is True
    assert result["transition_type"] == "tone_flip"
    assert result["severity"] == "critical"


def test_new_guidance_change_notifies_even_without_priority_upgrade() -> None:
    previous = {
        "priority_level": "normal",
        "event_type": "priority_refresh",
        "research_tone": "neutral",
    }
    current = {
        "priority_level": "normal",
        "event_type": "guidance_change",
        "research_tone": "mixed",
        "guidance_changed": True,
        "notification_ready": False,
    }
    result = evaluate_research_priority_transition(previous, current)
    assert result["notify"] is True
    assert result["transition_type"] == "new_guidance_change"


def test_first_non_material_event_only_builds_baseline() -> None:
    current = {
        "code": "MSFT",
        "priority_level": "normal",
        "event_type": "priority_refresh",
        "research_tone": "neutral",
        "notification_ready": False,
    }
    alerts = build_research_priority_alerts([current], {})
    assert alerts == []
