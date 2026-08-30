# -*- coding: utf-8 -*-
"""Candidate-pool persistence for point-in-time financial evidence."""

from src.repositories.candidate_pool_repo import CandidatePoolRepository, candidate_to_dict
from src.storage import DatabaseManager


def setup_function() -> None:
    DatabaseManager.reset_instance()


def teardown_function() -> None:
    DatabaseManager.reset_instance()


def test_candidate_pool_persists_latest_financials_and_run_snapshot() -> None:
    db = DatabaseManager("sqlite:///:memory:")
    repo = CandidatePoolRepository(db)
    stats = repo.sync_from_screen_result(
        {
            "market": "us",
            "strategy": "us_research_priority",
            "run_id": "earnings-run-1",
            "snapshot_count": 100,
            "source_errors": [],
            "picks": [
                {
                    "code": "NVDA",
                    "final_score": 88,
                    "pe_ratio": 30.5,
                    "pb_ratio": 18.2,
                    "total_mv": 4200000000000,
                    "dsa_context": {
                        "fundamentals": {
                            "forwardPE": 27.8,
                            "revenueGrowth": 0.22,
                            "earningsGrowth": 0.28,
                            "grossMargins": 0.71,
                        }
                    },
                }
            ],
        }
    )

    assert stats.financial_snapshots == 1
    exported = candidate_to_dict(repo.get("us", "NVDA"))
    assert exported["pe_ratio"] == 30.5
    assert exported["pb_ratio"] == 18.2
    assert exported["financial_data_confidence"] == "high"
    assert exported["financial_snapshot"]["valuation"]["forward_pe"] == 27.8
    assert exported["financial_snapshot"]["earnings"]["revenue_growth"] == 0.22

    history = repo.list_financial_snapshots("us", "NVDA")
    assert len(history) == 1
    assert history[0].run_id == "earnings-run-1"
    assert history[0].pe_ratio == 30.5


def test_missing_financials_do_not_overwrite_previous_good_snapshot() -> None:
    db = DatabaseManager("sqlite:///:memory:")
    repo = CandidatePoolRepository(db)
    repo.sync_from_screen_result(
        {
            "market": "us",
            "run_id": "run-good",
            "snapshot_count": 100,
            "source_errors": [],
            "picks": [
                {
                    "code": "NVDA",
                    "final_score": 88,
                    "pe_ratio": 30,
                    "dsa_context": {
                        "fundamentals": {
                            "revenueGrowth": 0.2,
                            "earningsGrowth": 0.3,
                        }
                    },
                }
            ],
        }
    )
    repo.sync_from_screen_result(
        {
            "market": "us",
            "run_id": "run-missing",
            "snapshot_count": 100,
            "source_errors": [],
            "picks": [{"code": "NVDA", "final_score": 85}],
        }
    )

    exported = candidate_to_dict(repo.get("us", "NVDA"))
    assert exported["pe_ratio"] == 30
    assert exported["financial_snapshot"]["earnings"]["revenue_growth"] == 0.2
    assert len(repo.list_financial_snapshots("us", "NVDA")) == 1
