import pytest

from scripts.e06_benchmark import LAYERS, PROTECTED_CONTRACTS, make_row, validate_row


def test_row_keeps_three_layers_and_pending_fresh_context():
    row = make_row(task_id="T1", run_id="smoke", context="current-chat")
    validate_row(row)
    assert tuple(row["layers"]) == LAYERS
    assert row["official_status"] == "CONTAMINATED"
    assert row["contamination"] is True


def test_contaminated_row_cannot_pass():
    row = make_row(task_id="T5", run_id="bad", context="current-chat")
    row["correctness_gate"]["result"] = "PASS"
    with pytest.raises(ValueError, match="contaminated"):
        validate_row(row)


def _fresh_with_gate(values):
    row = make_row(task_id="T1", run_id="x", context="fresh", contamination=False)
    row["correctness_gate"] = {"result": "PASS", "protected_governance": values}
    row["official_status"] = "ELIGIBLE"
    return row


def test_missing_protected_contract_is_not_pass():
    values = {name: "PASS" for name in PROTECTED_CONTRACTS[:-1]}
    with pytest.raises(ValueError, match="seven"):
        validate_row(_fresh_with_gate(values))


@pytest.mark.parametrize("bad", ["FAIL", "UNKNOWN", None])
def test_non_passing_protected_contract_is_not_pass(bad):
    values = {name: "PASS" for name in PROTECTED_CONTRACTS}
    values[PROTECTED_CONTRACTS[0]] = bad
    with pytest.raises(ValueError, match="seven"):
        validate_row(_fresh_with_gate(values))


def test_all_explicit_protected_contracts_pass():
    row = _fresh_with_gate({name: "PASS" for name in PROTECTED_CONTRACTS})
    validate_row(row)


def test_fresh_sample_can_be_eligible_only_after_correctness():
    row = make_row(task_id="T1", run_id="x", context="fresh", contamination=False)
    row["official_status"] = "ELIGIBLE"
    with pytest.raises(ValueError, match="eligibility"):
        validate_row(row)


def test_current_chat_cannot_be_promoted_by_toggling_fields():
    row = make_row(task_id="T1", run_id="x", context="current-chat")
    row["contamination"] = False
    row["official_status"] = "ELIGIBLE"
    row["correctness_gate"] = {
        "result": "PASS",
        "protected_governance": {name: "PASS" for name in PROTECTED_CONTRACTS},
    }
    with pytest.raises(ValueError, match="validated fresh context"):
        validate_row(row)


def test_unknown_metric_is_rejected():
    with pytest.raises(ValueError, match="unknown metrics"):
        make_row(task_id="T1", run_id="x", context="fresh", typo_metric=1)
