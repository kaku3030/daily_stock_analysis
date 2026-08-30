# -*- coding: utf-8 -*-
"""Tests for the candidate-derived research industry radar."""

from src.services.screening.industry_radar import (
    build_industry_radar,
    industry_radar_markdown,
)


def test_industry_radar_ranks_stronger_candidate_group_first() -> None:
    candidates = [
        {
            "code": "NVDA",
            "name": "NVIDIA",
            "industry": "Semiconductors",
            "grade": "A",
            "score": 88,
            "status": "active",
            "selected_count": 5,
        },
        {
            "code": "AVGO",
            "name": "Broadcom",
            "industry": "Semiconductors",
            "grade": "A",
            "score": 84,
            "status": "active",
            "selected_count": 4,
        },
        {
            "code": "AMD",
            "name": "AMD",
            "industry": "Semiconductors",
            "grade": "B",
            "score": 72,
            "status": "watching",
            "selected_count": 2,
        },
        {
            "code": "JPM",
            "name": "JPMorgan",
            "industry": "Banks",
            "grade": "B",
            "score": 68,
            "status": "active",
            "selected_count": 1,
        },
    ]

    rows = build_industry_radar(candidates)

    assert [row["industry"] for row in rows] == ["Semiconductors", "Banks"]
    assert rows[0]["rank"] == 1
    assert rows[0]["candidate_count"] == 3
    assert rows[0]["grade_ab_count"] == 3
    assert rows[0]["confidence"] == "high"
    assert rows[0]["top_candidates"][0]["code"] == "NVDA"
    assert rows[0]["top_candidates"][0]["industry_rank"] == 1


def test_industry_radar_excludes_retired_and_missing_industry() -> None:
    candidates = [
        {
            "code": "TSLA",
            "industry": "Automobiles",
            "grade": "A",
            "score": 90,
            "status": "retired",
            "selected_count": 5,
        },
        {
            "code": "AAPL",
            "industry": "",
            "grade": "A",
            "score": 90,
            "status": "active",
            "selected_count": 5,
        },
    ]

    assert build_industry_radar(candidates) == []
    markdown = industry_radar_markdown([])
    assert "暂无可用行业数据" in markdown


def test_industry_radar_can_ignore_watching_candidates() -> None:
    candidates = [
        {
            "code": "NVDA",
            "industry": "Semiconductors",
            "grade": "A",
            "score": 88,
            "status": "active",
            "selected_count": 4,
        },
        {
            "code": "AMD",
            "industry": "Semiconductors",
            "grade": "B",
            "score": 70,
            "status": "watching",
            "selected_count": 3,
        },
    ]

    rows = build_industry_radar(candidates, include_watching=False)

    assert len(rows) == 1
    assert rows[0]["candidate_count"] == 1
    assert rows[0]["top_candidates"][0]["code"] == "NVDA"
