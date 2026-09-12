import json
from pathlib import Path

from scripts.strategy_lab_replay_baseline import build_baseline


ARTIFACT = Path("research/artifacts/recall-calibration-baseline-v0.1.json")


def test_committed_baseline_is_byte_stable_and_contract_is_frozen():
    expected = ARTIFACT.read_text(encoding="utf-8")
    actual = json.dumps(build_baseline(), ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    assert actual == expected
    contract = build_baseline()["dataset_contract"]
    assert contract["contract_version"] == "recall-calibration-dataset-v0.1"
    assert contract["dataset_id"] == "historical-fixture-recall-v0.1"


def test_baseline_totals_and_sample_limit_are_explicit():
    baseline = build_baseline()["baseline"]
    assert baseline["reconciliation"]["totals_match"] is True
    assert baseline["censored_count"] == 1
    assert baseline["unknown_truth_count"] == 2
    assert baseline["sample_size"]["status"] == "NOT_STATISTICALLY_RELIABLE"
