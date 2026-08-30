# -*- coding: utf-8 -*-
"""Candidate-pool persistence for industry radar fields."""

from src.repositories.candidate_pool_repo import CandidatePoolRepository, candidate_to_dict
from src.storage import DatabaseManager


def setup_function() -> None:
    DatabaseManager.reset_instance()


def teardown_function() -> None:
    DatabaseManager.reset_instance()


def test_candidate_pool_persists_industry_market_fields() -> None:
    db = DatabaseManager("sqlite:///:memory:")
    repo = CandidatePoolRepository(db)
    repo.sync_from_screen_result({
        "market": "us",
        "snapshot_count": 100,
        "source_errors": [],
        "picks": [{
            "code": "NVDA",
            "final_score": 88,
            "industry": "Semiconductors",
            "industry_rank": 2,
            "industry_change_pct": 1.75,
            "industry_heat_score": 91,
            "board_heat_score": 87,
            "board_heat_latest_score": 90,
            "board_heat_trend_score": 83,
            "board_heat_persistence_score": 85,
            "board_heat_cooling_score": 12,
            "board_heat_observations": 9,
            "board_heat_state": "heating",
            "board_heat_summary": "strong and persistent",
        }],
    })

    exported = candidate_to_dict(repo.get("us", "NVDA"))
    assert exported["industry_rank"] == 2
    assert exported["industry_change_pct"] == 1.75
    assert exported["industry_heat_score"] == 91
    assert exported["board_heat_trend_score"] == 83
    assert exported["board_heat_persistence_score"] == 85
    assert exported["board_heat_state"] == "heating"
