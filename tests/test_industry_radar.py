# -*- coding: utf-8 -*-
"""Tests for the blended research industry radar."""

from src.services.screening.industry_radar import build_industry_radar, industry_radar_markdown


def test_industry_radar_blends_market_heat_when_available() -> None:
    candidates = [
        {
            "code": "NVDA", "industry": "Semiconductors", "grade": "A", "score": 88,
            "status": "active", "selected_count": 5, "industry_change_pct": 1.8,
            "industry_heat_score": 92, "board_heat_score": 88,
            "board_heat_latest_score": 90, "board_heat_trend_score": 84,
            "board_heat_persistence_score": 86,
        },
        {
            "code": "AVGO", "industry": "Semiconductors", "grade": "A", "score": 84,
            "status": "active", "selected_count": 4, "industry_change_pct": 1.8,
            "industry_heat_score": 92, "board_heat_score": 88,
            "board_heat_latest_score": 90, "board_heat_trend_score": 84,
            "board_heat_persistence_score": 86,
        },
        {
            "code": "JPM", "industry": "Banks", "grade": "B", "score": 74,
            "status": "active", "selected_count": 3, "industry_change_pct": -0.5,
            "industry_heat_score": 35, "board_heat_score": 40,
            "board_heat_latest_score": 38, "board_heat_trend_score": 32,
            "board_heat_persistence_score": 45,
        },
    ]

    rows = build_industry_radar(candidates)

    assert rows[0]["industry"] == "Semiconductors"
    assert rows[0]["market_data_mode"] == "blended"
    assert rows[0]["market_strength_score"] is not None
    assert rows[0]["combined_strength_score"] > rows[1]["combined_strength_score"]
    assert rows[0]["industry_change_pct"] == 1.8
    assert rows[0]["confidence"] == "medium"
    assert "市场分" in industry_radar_markdown(rows)


def test_industry_radar_falls_back_to_candidate_only() -> None:
    rows = build_industry_radar([
        {"code": "MSFT", "industry": "Software", "grade": "A", "score": 85, "status": "active", "selected_count": 4},
        {"code": "ORCL", "industry": "Software", "grade": "B", "score": 72, "status": "watching", "selected_count": 2},
    ])

    assert rows[0]["market_data_mode"] == "candidate_only"
    assert rows[0]["market_strength_score"] is None
    assert rows[0]["combined_strength_score"] == rows[0]["research_strength_score"]


def test_industry_radar_excludes_retired_and_missing_industry() -> None:
    candidates = [
        {"code": "TSLA", "industry": "Automobiles", "grade": "A", "score": 90, "status": "retired", "selected_count": 5},
        {"code": "AAPL", "industry": "", "grade": "A", "score": 90, "status": "active", "selected_count": 5},
    ]
    assert build_industry_radar(candidates) == []
    assert "暂无可用行业数据" in industry_radar_markdown([])
