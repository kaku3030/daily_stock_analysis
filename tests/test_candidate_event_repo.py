# -*- coding: utf-8 -*-

from src.repositories.candidate_event_repo import CandidateEventSnapshotRepository, event_snapshot_to_dict
from src.storage import DatabaseManager


def setup_function() -> None:
    DatabaseManager.reset_instance()


def teardown_function() -> None:
    DatabaseManager.reset_instance()


def _payload(run_id: str, catalysts: list[str], risks: list[str]) -> dict:
    return {
        "market": "us",
        "run_id": run_id,
        "picks": [{
            "code": "NVDA",
            "llm_catalysts": catalysts,
            "llm_risks": risks,
            "dsa_news": [{"title": "NVIDIA update", "url": "https://example.com/nvda"}],
        }],
    }


def test_event_snapshots_are_idempotent_and_compare_adjacent_runs() -> None:
    db = DatabaseManager("sqlite:///:memory:")
    repo = CandidateEventSnapshotRepository(db)
    assert repo.sync_run(_payload("run-1", ["AI demand"], [])) == 1
    assert repo.sync_run(_payload("run-1", ["AI demand"], [])) == 0
    assert repo.sync_run(_payload("run-2", ["AI demand", "new order"], ["DOJ investigation"])) == 1

    latest = event_snapshot_to_dict(repo.list_latest("us")[0])
    assert latest["run_id"] == "run-2"
    assert len(latest["change"]["new_catalysts"]) == 1
    assert latest["change"]["new_risks"][0]["severity"] == "high"
    assert latest["news_evidence"][0]["url"] == "https://example.com/nvda"

