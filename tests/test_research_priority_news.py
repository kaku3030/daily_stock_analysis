# -*- coding: utf-8 -*-

from src.services.screening.research_priority_news import build_research_priority_events_with_news


def _candidate(state: str) -> dict:
    return {
        "code": "NVDA", "name": "NVIDIA", "grade": "B", "score": 70, "status": "active",
        "industry": "Semiconductors", "catalysts": [], "risks": [], "financial_change": {},
        "news_change": {
            "state": state,
            "new_catalysts": [{"text": "new hyperscaler order"}] if state == "new_catalyst" else [],
            "new_risks": [{"text": "regulatory investigation"}] if state == "new_risk" else [],
        },
    }


def test_new_risk_becomes_notification_ready_risk_review() -> None:
    event = build_research_priority_events_with_news([_candidate("new_risk")], [])[0]
    assert event["event_type"] == "news_risk"
    assert event["research_tone"] == "risk_review"
    assert event["notification_ready"] is True
    assert event["news_change_state"] == "new_risk"


def test_baseline_does_not_raise_priority() -> None:
    base = build_research_priority_events_with_news([_candidate("baseline")], [])[0]
    plain = build_research_priority_events_with_news([_candidate("unchanged")], [])[0]
    assert base["priority_score"] == plain["priority_score"]
