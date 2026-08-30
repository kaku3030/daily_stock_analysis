# -*- coding: utf-8 -*-
"""Tests for deterministic research-priority fusion."""

from src.services.screening.research_priority import build_research_priority_events


def test_financial_deterioration_becomes_urgent_risk_review() -> None:
    candidates = [
        {
            "code": "NVDA",
            "name": "NVIDIA",
            "grade": "A",
            "score": 88,
            "status": "active",
            "industry": "Semiconductors",
            "catalysts": ["new accelerator launch"],
            "risks": ["valuation"],
            "financial_change": {
                "attention": "high",
                "earnings_trend": "deteriorating",
                "valuation_trend": "expanding",
                "guidance_changed": False,
            },
        }
    ]
    industries = [
        {
            "industry": "Semiconductors",
            "market_data_mode": "blended",
            "market_strength_score": 82,
            "combined_strength_score": 84,
        }
    ]

    event = build_research_priority_events(candidates, industries)[0]

    assert event["priority_level"] == "urgent"
    assert event["event_type"] == "financial_risk"
    assert event["research_tone"] == "risk_review"
    assert event["notification_ready"] is True


def test_positive_convergence_requires_quality_and_industry_support() -> None:
    candidates = [
        {
            "code": "AVGO",
            "name": "Broadcom",
            "grade": "B",
            "score": 76,
            "status": "active",
            "industry": "Semiconductors",
            "catalysts": ["AI demand"],
            "risks": [],
            "financial_change": {
                "attention": "medium",
                "earnings_trend": "improving",
                "valuation_trend": "stable",
                "guidance_changed": False,
            },
        }
    ]
    industries = [
        {
            "industry": "Semiconductors",
            "market_data_mode": "blended",
            "market_strength_score": 80,
            "combined_strength_score": 81,
        }
    ]

    event = build_research_priority_events(candidates, industries)[0]

    assert event["priority_level"] == "high"
    assert event["event_type"] == "positive_convergence"
    assert event["research_tone"] == "positive_watch"
    assert event["notification_ready"] is True


def test_candidate_only_industry_does_not_double_count_as_market_strength() -> None:
    candidates = [
        {
            "code": "MSFT",
            "grade": "B",
            "score": 70,
            "status": "active",
            "industry": "Software",
            "catalysts": [],
            "risks": [],
            "financial_change": {},
        }
    ]
    industries = [
        {
            "industry": "Software",
            "market_data_mode": "candidate_only",
            "research_strength_score": 90,
            "combined_strength_score": 90,
            "market_strength_score": None,
        }
    ]

    event = build_research_priority_events(candidates, industries)[0]

    assert event["industry_market_score"] is None
    assert event["event_type"] == "priority_refresh"
    assert event["notification_ready"] is False
