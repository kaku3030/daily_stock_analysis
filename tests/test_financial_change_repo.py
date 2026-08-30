# -*- coding: utf-8 -*-
"""Integration tests for persisted candidate financial changes."""

from src.repositories.candidate_pool_repo import CandidatePoolRepository
from src.repositories.financial_change_repo import (
    CandidateFinancialChangeRepository,
    financial_change_to_dict,
)
from src.storage import DatabaseManager


def setup_function() -> None:
    DatabaseManager.reset_instance()


def teardown_function() -> None:
    DatabaseManager.reset_instance()


def _payload(run_id: str, revenue_growth: float, forward_pe: float) -> dict:
    return {
        "market": "us",
        "strategy": "us_research_priority",
        "run_id": run_id,
        "snapshot_count": 100,
        "source_errors": [],
        "picks": [
            {
                "code": "NVDA",
                "final_score": 88,
                "pe_ratio": forward_pe + 2,
                "dsa_context": {
                    "fundamentals": {
                        "revenueGrowth": revenue_growth,
                        "earningsGrowth": revenue_growth + 0.05,
                        "forwardPE": forward_pe,
                    }
                },
            }
        ],
    }


def test_financial_change_repo_compares_adjacent_valid_snapshots() -> None:
    db = DatabaseManager("sqlite:///:memory:")
    pool = CandidatePoolRepository(db)
    changes = CandidateFinancialChangeRepository(db)

    pool.sync_from_screen_result(_payload("run-1", 0.20, 30))
    assert changes.sync_run("us", "run-1") == 1
    first = financial_change_to_dict(changes.list_latest("us")[0])
    assert first["state"] == "insufficient_history"

    pool.sync_from_screen_result(_payload("run-2", 0.26, 36))
    assert changes.sync_run("us", "run-2") == 1
    latest = financial_change_to_dict(changes.list_latest("us")[0])
    assert latest["previous_run_id"] == "run-1"
    assert latest["earnings_trend"] == "improving"
    assert latest["valuation_trend"] == "expanding"
    assert latest["state"] == "mixed"
    assert latest["attention"] == "medium"


def test_financial_change_sync_is_idempotent_per_run() -> None:
    db = DatabaseManager("sqlite:///:memory:")
    pool = CandidatePoolRepository(db)
    changes = CandidateFinancialChangeRepository(db)

    pool.sync_from_screen_result(_payload("run-1", 0.20, 30))
    assert changes.sync_run("us", "run-1") == 1
    assert changes.sync_run("us", "run-1") == 0
