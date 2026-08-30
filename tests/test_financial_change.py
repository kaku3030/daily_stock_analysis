# -*- coding: utf-8 -*-
"""Tests for deterministic financial change comparison."""

from src.services.screening.financial_change import compare_financial_snapshots


def test_first_snapshot_is_insufficient_history() -> None:
    result = compare_financial_snapshots(None, {"earnings": {"revenue_growth": 0.2}})
    assert result["state"] == "insufficient_history"
    assert result["attention"] == "none"


def test_improving_earnings_with_expanding_valuation_is_mixed() -> None:
    result = compare_financial_snapshots(
        {
            "earnings": {"revenue_growth": 0.20, "eps_growth": 0.25},
            "valuation": {"forward_pe": 30},
        },
        {
            "earnings": {"revenue_growth": 0.24, "eps_growth": 0.30},
            "valuation": {"forward_pe": 36},
        },
    )
    assert result["earnings_trend"] == "improving"
    assert result["valuation_trend"] == "expanding"
    assert result["state"] == "mixed"
    assert result["attention"] == "medium"


def test_deteriorating_earnings_get_high_attention() -> None:
    result = compare_financial_snapshots(
        {"earnings": {"revenue_growth": 0.30, "eps_growth": 0.40}},
        {"earnings": {"revenue_growth": 0.20, "eps_growth": 0.25}},
    )
    assert result["earnings_trend"] == "deteriorating"
    assert result["state"] == "deteriorating"
    assert result["attention"] == "high"


def test_guidance_change_is_detected_without_sentiment_guessing() -> None:
    result = compare_financial_snapshots(
        {"earnings": {"guidance": "Revenue expected around 10 billion"}},
        {"earnings": {"guidance": "Revenue expected around 11 billion"}},
    )
    assert result["guidance_changed"] is True
    assert result["state"] == "guidance_changed"
    assert result["guidance"]["previous"]
    assert result["guidance"]["current"]


def test_small_numeric_noise_is_ignored() -> None:
    result = compare_financial_snapshots(
        {"earnings": {"gross_margin": 0.700}},
        {"earnings": {"gross_margin": 0.701}},
    )
    assert result["earnings_trend"] == "stable"
    assert result["quality_changes"] == []
