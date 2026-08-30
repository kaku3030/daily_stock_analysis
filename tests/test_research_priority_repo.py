# -*- coding: utf-8 -*-
"""Tests for persisted research-priority events."""

from src.repositories.research_priority_repo import ResearchPriorityEventRepository
from src.storage import DatabaseManager


def setup_function() -> None:
    DatabaseManager.reset_instance()


def teardown_function() -> None:
    DatabaseManager.reset_instance()


def _event(code: str, priority: str, event_type: str) -> dict:
    return {
        "code": code,
        "priority_level": priority,
        "priority_score": 82.5,
        "event_type": event_type,
        "research_tone": "risk_review" if event_type == "financial_risk" else "positive_watch",
        "notification_ready": True,
        "reasons": ["test"],
    }


def test_priority_event_sync_is_idempotent_per_run() -> None:
    db = DatabaseManager("sqlite:///:memory:")
    repo = ResearchPriorityEventRepository(db)
    events = [_event("NVDA", "urgent", "financial_risk")]

    assert repo.sync_run("us", "run-1", events) == 1
    assert repo.sync_run("us", "run-1", events) == 0

    latest = repo.list_latest("us")
    assert len(latest) == 1
    assert latest[0].code == "NVDA"
    assert latest[0].priority_level == "urgent"
    assert latest[0].notification_ready is True


def test_latest_payload_map_can_exclude_current_run() -> None:
    db = DatabaseManager("sqlite:///:memory:")
    repo = ResearchPriorityEventRepository(db)
    repo.sync_run("us", "run-1", [_event("NVDA", "normal", "catalyst_focus")])
    repo.sync_run("us", "run-2", [_event("NVDA", "urgent", "financial_risk")])

    previous = repo.latest_payload_map("us", exclude_run_id="run-2")

    assert previous["NVDA"]["priority_level"] == "normal"
    assert previous["NVDA"]["event_type"] == "catalyst_focus"
