# -*- coding: utf-8 -*-
"""Tests for news/catalyst history, dedupe, and priority integration."""

from src.repositories.research_event_repo import (
    ResearchEventSnapshotRepository,
    research_event_snapshot_to_dict,
)
from src.services.screening.news_change import (
    build_event_evidence,
    compare_event_evidence,
    events_equivalent,
)
from src.services.screening.research_priority import build_research_priority_events
from src.storage import DatabaseManager


def setup_function() -> None:
    DatabaseManager.reset_instance()


def teardown_function() -> None:
    DatabaseManager.reset_instance()


def test_paraphrased_old_catalyst_is_not_new() -> None:
    previous = build_event_evidence(
        {"llm_catalysts": ["AI demand remains strong"], "llm_risks": []}
    )
    current = build_event_evidence(
        {"llm_catalysts": ["Strong AI demand continues"], "llm_risks": []}
    )

    change = compare_event_evidence(previous, current)

    assert events_equivalent("AI demand remains strong", "Strong AI demand continues")
    assert change["state"] == "unchanged"
    assert change["material"] is False
    assert change["new_catalysts"] == []


def test_new_risk_has_high_attention_but_missing_evidence_is_not_recovery() -> None:
    previous = build_event_evidence(
        {"llm_catalysts": ["Blackwell demand"], "llm_risks": []}
    )
    current = build_event_evidence(
        {
            "llm_catalysts": ["Blackwell demand"],
            "llm_risks": ["DOJ launches investigation"],
        }
    )

    change = compare_event_evidence(previous, current)
    missing = compare_event_evidence(current, build_event_evidence({}))

    assert change["state"] == "new_risk"
    assert change["attention"] == "high"
    assert change["material"] is True
    assert change["new_risks"] == ["DOJ launches investigation"]
    assert missing["state"] == "resolved_or_missing"
    assert missing["resolution_confirmed"] is False
    assert missing["material"] is False


def test_event_snapshot_repo_compares_adjacent_runs_and_is_idempotent() -> None:
    db = DatabaseManager("sqlite:///:memory:")
    repo = ResearchEventSnapshotRepository(db)

    first_pick = {
        "code": "NVDA",
        "llm_catalysts": ["AI demand remains strong"],
        "llm_risks": [],
        "dsa_news": [{"title": "AI infrastructure spending stays firm"}],
    }
    second_pick = {
        "code": "NVDA",
        "llm_catalysts": ["Strong AI demand continues", "New hyperscaler order"],
        "llm_risks": ["Export restriction review"],
        "dsa_news": [{"title": "Hyperscaler expands accelerator order"}],
    }

    assert repo.sync_run("us", "run-1", [first_pick]) == 1
    first = research_event_snapshot_to_dict(repo.list_run("us", "run-1")[0])
    assert first["detail"]["baseline"] is True

    assert repo.sync_run("us", "run-2", [second_pick]) == 1
    assert repo.sync_run("us", "run-2", [second_pick]) == 0
    latest = research_event_snapshot_to_dict(repo.list_run("us", "run-2")[0])
    assert latest["previous_run_id"] == "run-1"
    assert latest["detail"]["state"] == "new_risk"
    assert latest["detail"]["new_catalysts"] == ["New hyperscaler order"]
    assert latest["detail"]["new_risks"] == ["Export restriction review"]


def test_new_risk_feeds_research_priority_without_trade_instruction() -> None:
    candidates = [
        {
            "code": "NVDA",
            "name": "NVIDIA",
            "grade": "A",
            "score": 84,
            "status": "active",
            "industry": "Semiconductors",
            "catalysts": [],
            "risks": [],
            "financial_change": {},
            "news_change": {
                "state": "new_risk",
                "attention": "high",
                "material": True,
                "new_catalysts": [],
                "new_risks": ["Export restriction review"],
            },
        }
    ]

    event = build_research_priority_events(candidates, [])[0]

    assert event["event_type"] == "news_risk"
    assert event["research_tone"] == "risk_review"
    assert event["notification_ready"] is True
    assert event["news_change_state"] == "new_risk"
    assert "operation_advice" not in event
    assert "action" not in event
