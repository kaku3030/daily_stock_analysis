import pytest

from scripts.e06_benchmark import LAYERS, make_row, validate_row


def test_row_keeps_three_layers_and_pending_fresh_context():
    row = make_row(task_id="T1", run_id="smoke", context="current-chat")
    validate_row(row)
    assert tuple(row["layers"]) == LAYERS
    assert row["official_status"] == "PENDING_FRESH_CONTEXT"
    assert row["contamination"] is True


def test_contaminated_row_cannot_pass():
    row = make_row(task_id="T5", run_id="bad", context="current-chat")
    row["correctness_gate"]["result"] = "PASS"
    with pytest.raises(ValueError, match="contaminated"):
        validate_row(row)


def test_unknown_metric_is_rejected():
    with pytest.raises(ValueError, match="unknown metrics"):
        make_row(task_id="T1", run_id="x", context="fresh", typo_metric=1)
