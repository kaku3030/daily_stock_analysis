# -*- coding: utf-8 -*-
"""Tests for the persistent research candidate pool."""

from src.repositories.candidate_pool_repo import (
    CandidatePoolRepository,
    candidate_grade,
    candidate_to_dict,
)
from src.storage import DatabaseManager


def setup_function() -> None:
    DatabaseManager.reset_instance()


def teardown_function() -> None:
    DatabaseManager.reset_instance()


def _healthy_payload(code: str, score: float = 70.0, run_id: str = "run") -> dict:
    return {
        "market": "us",
        "strategy": "us_research_priority",
        "run_id": run_id,
        "snapshot_count": 100,
        "source_errors": [],
        "picks": [{"code": code, "final_score": score}],
    }


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
            "snapshot_count": 100,
            "source_errors": [],
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
            "snapshot_count": 100,
            "source_errors": [],
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
    assert candidate.missed_runs == 0
    assert len(repo.list_active("us")) == 1


def test_missing_from_empty_or_degraded_scan_does_not_age_candidate() -> None:
    db = DatabaseManager("sqlite:///:memory:")
    repo = CandidatePoolRepository(db)
    repo.sync_from_screen_result(_healthy_payload("TSLA", 66))

    repo.sync_from_screen_result(
        {
            "market": "us",
            "snapshot_count": 0,
            "picks": [],
        }
    )
    repo.sync_from_screen_result(
        {
            "market": "us",
            "snapshot_count": 100,
            "source_errors": ["provider failed"],
            "picks": [{"code": "AAPL", "final_score": 75}],
        }
    )

    candidate = repo.get("us", "TSLA")
    assert candidate is not None
    assert candidate.status == "active"
    assert candidate.missed_runs == 0


def test_healthy_misses_move_candidate_to_watching_then_retired() -> None:
    db = DatabaseManager("sqlite:///:memory:")
    repo = CandidatePoolRepository(db)
    repo.sync_from_screen_result(_healthy_payload("TSLA", 66, "seed"))

    repo.sync_from_screen_result(_healthy_payload("AAPL", 75, "miss-1"))
    candidate = repo.get("us", "TSLA")
    assert candidate is not None
    assert candidate.status == "active"
    assert candidate.missed_runs == 1

    stats = repo.sync_from_screen_result(_healthy_payload("AAPL", 75, "miss-2"))
    candidate = repo.get("us", "TSLA")
    assert candidate is not None
    assert candidate.status == "watching"
    assert candidate.missed_runs == 2
    assert stats.watching == 1

    repo.sync_from_screen_result(_healthy_payload("AAPL", 75, "miss-3"))
    repo.sync_from_screen_result(_healthy_payload("AAPL", 75, "miss-4"))
    stats = repo.sync_from_screen_result(_healthy_payload("AAPL", 75, "miss-5"))
    candidate = repo.get("us", "TSLA")
    assert candidate is not None
    assert candidate.status == "retired"
    assert candidate.missed_runs == 5
    assert stats.retired == 1


def test_reselection_reactivates_retired_candidate_and_resets_misses() -> None:
    db = DatabaseManager("sqlite:///:memory:")
    repo = CandidatePoolRepository(db)
    repo.sync_from_screen_result(_healthy_payload("TSLA", 66, "seed"))
    for index in range(5):
        repo.sync_from_screen_result(_healthy_payload("AAPL", 75, f"miss-{index}"))

    stats = repo.sync_from_screen_result(_healthy_payload("TSLA", 83, "return"))
    candidate = repo.get("us", "TSLA")
    assert candidate is not None
    assert candidate.status == "active"
    assert candidate.grade == "A"
    assert candidate.missed_runs == 0
    assert stats.reactivated == 1

    exported = candidate_to_dict(candidate)
    assert exported["status"] == "active"
    assert exported["grade"] == "A"
    assert exported["selected_count"] == 2
