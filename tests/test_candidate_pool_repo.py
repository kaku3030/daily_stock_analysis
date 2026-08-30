# -*- coding: utf-8 -*-
"""Tests for the persistent research candidate pool."""

from src.repositories.candidate_pool_repo import CandidatePoolRepository, candidate_grade
from src.storage import DatabaseManager


def setup_function() -> None:
    DatabaseManager.reset_instance()


def teardown_function() -> None:
    DatabaseManager.reset_instance()


def test_candidate_grade_boundaries() -> None:
    assert candidate_grade(80) == "A"
    assert candidate_grade(79.99) == "B"
    assert candidate_grade(65) == "B"
    assert candidate_grade(50) == "C"
    assert candidate_grade(49.99) == "D"


def test_sync_preserves_candidate_and_refreshes_state() -> None:
    db = DatabaseManager("sqlite:///:memory:")
    repo = CandidatePoolRepository(db)

    first = repo.sync_from_screen_result(
        {
            "market": "us",
            "strategy": "us_research_priority",
            "run_id": "run-1",
            "picks": [
                {
                    "code": "NVDA",
                    "name": "NVIDIA",
                    "final_score": 82.5,
                    "industry": "Semiconductors",
                    "ranking_reason": "growth and earnings momentum",
                    "risk_summary": "valuation",
                    "factor_scores": {"quality": 88},
                    "llm_catalysts": ["earnings"],
                    "llm_risks": ["multiple compression"],
                }
            ],
        }
    )
    assert first.inserted == 1
    assert first.updated == 0

    second = repo.sync_from_screen_result(
        {
            "market": "us",
            "strategy": "us_research_priority",
            "run_id": "run-2",
            "picks": [
                {
                    "code": "nvda",
                    "name": "NVIDIA",
                    "final_score": 72.0,
                    "industry": "Semiconductors",
                }
            ],
        }
    )
    assert second.inserted == 0
    assert second.updated == 1

    candidate = repo.get("US", "nvda")
    assert candidate is not None
    assert candidate.code == "NVDA"
    assert candidate.grade == "B"
    assert candidate.score == 72.0
    assert candidate.selected_count == 2
    assert candidate.source_run_id == "run-2"
    assert len(repo.list_active("us")) == 1


def test_missing_from_next_scan_does_not_delete_candidate() -> None:
    db = DatabaseManager("sqlite:///:memory:")
    repo = CandidatePoolRepository(db)
    repo.sync_from_screen_result(
        {
            "market": "us",
            "picks": [{"code": "TSLA", "final_score": 66}],
        }
    )

    stats = repo.sync_from_screen_result({"market": "us", "picks": []})

    assert stats.inserted == 0
    assert stats.updated == 0
    assert repo.get("us", "TSLA") is not None
