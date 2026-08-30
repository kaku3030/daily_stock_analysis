# -*- coding: utf-8 -*-
"""Tests for earnings/valuation normalization and radar output."""

from src.schemas.research_financials import extract_financial_snapshot
from src.services.screening.earnings_valuation_radar import (
    build_earnings_valuation_radar,
    earnings_valuation_radar_markdown,
)


def test_extract_financial_snapshot_uses_pick_valuation_and_dsa_fundamentals() -> None:
    snapshot = extract_financial_snapshot(
        {
            "pe_ratio": 31.5,
            "pb_ratio": 12.2,
            "dsa_context": {
                "fundamentals": {
                    "forwardPE": 28.1,
                    "revenueGrowth": 0.24,
                    "earningsGrowth": 0.31,
                    "grossMargins": 0.72,
                    "earnings_date": "2026-08-27",
                    "outlook": "next-quarter revenue above consensus",
                }
            },
        }
    )

    assert snapshot["mode"] == "fundamentals"
    assert snapshot["confidence"] == "high"
    assert snapshot["valuation"]["pe_ratio"] == 31.5
    assert snapshot["valuation"]["forward_pe"] == 28.1
    assert snapshot["earnings"]["revenue_growth"] == 0.24
    assert snapshot["earnings"]["eps_growth"] == 0.31
    assert snapshot["earnings"]["guidance"] == "next-quarter revenue above consensus"


def test_extract_financial_snapshot_does_not_invent_missing_fields() -> None:
    snapshot = extract_financial_snapshot({"pe_ratio": 20})

    assert snapshot["mode"] == "valuation_only"
    assert snapshot["confidence"] == "low"
    assert snapshot["valuation"] == {"pe_ratio": 20}
    assert snapshot["earnings"] == {}


def test_earnings_valuation_radar_preserves_missing_evidence() -> None:
    candidates = [
        {
            "code": "NVDA",
            "name": "NVIDIA",
            "grade": "A",
            "score": 88,
            "status": "active",
            "industry": "Semiconductors",
            "financial_snapshot": {
                "mode": "fundamentals",
                "confidence": "high",
                "valuation": {"pe_ratio": 30, "forward_pe": 27},
                "earnings": {
                    "revenue_growth": 0.2,
                    "eps_growth": 0.25,
                    "earnings_date": "2026-08-27",
                },
            },
        },
        {
            "code": "TSLA",
            "name": "Tesla",
            "grade": "B",
            "score": 70,
            "status": "watching",
            "industry": "Automobiles",
            "financial_snapshot": {
                "mode": "none",
                "confidence": "none",
                "valuation": {},
                "earnings": {},
            },
        },
    ]

    rows = build_earnings_valuation_radar(candidates)

    assert rows[0]["code"] == "NVDA"
    assert rows[0]["forward_pe"] == 27
    tsla = next(row for row in rows if row["code"] == "TSLA")
    assert tsla["pe_ratio"] is None
    assert tsla["revenue_growth"] is None
    markdown = earnings_valuation_radar_markdown(rows)
    assert "财报与估值雷达" in markdown
    assert "NVDA" in markdown
