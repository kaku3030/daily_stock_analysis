# -*- coding: utf-8 -*-
"""Tests for persisted research-priority events."""

from src.repositories.research_priority_repo import ResearchPriorityEventRepository
from src.storage import DatabaseManager


def setup_function() -> None:
    DatabaseManager.reset_instance()


def teardown_function() -> None:
    DatabaseManager.reset_instance()


def test_priority_event_sync_is_idempotent_per_run() -> None:
    db = DatabaseManager("sqlite:///:memory:")
    repo = ResearchPriorityEventRepository(db)
    events = [
        {
            "code": "NVDA",
            "priority_level": "urgent",
            "priority_score": 82.5,
            "event_type": "financial_risk",
            "research_tone": "risk_review",
            "notification_ready": True,
            "reasons": ["financial deterioration"],
        }
    ]

    assert repo.sync_run("us", "run-1", events) == 1
    assert repo.sync_run("us", "run-1", events) == 0

    latest = repo.list_latest("us")
    assert len(latest) == 1
    assert latest[0].code == "NVDA"
    assert latest[0].priority_level == "urgent"
    assert latest[0].notification_ready is True
