"""Permanent adversarial tests for Parameter Selection Identity Drift V0.1.

Structural misuse (duplicate/unknown fold ids, mode-incompatible evidence)
must raise ValueError; it is never folded into a drift resolution. The
trust boundary is honored, not denied: separately supplied evidence can be
swapped between folds and the module cannot detect it -- tests must not
assert the module blocks this.
"""

import ast
import inspect
from datetime import datetime, timedelta, timezone

import pytest

from src.services.strategy_lab.parameter_drift import (
    ParameterDriftFindingCode,
    ParameterDriftResolution,
    evaluate_parameter_drift,
)
from src.services.strategy_lab.temporal_contract import TemporalInterval
from src.services.strategy_lab.walk_forward import (
    FixedParameterEvidence,
    FoldParameterSelectionEvidence,
    FoldValidationResult,
    FoldValidationStatus,
    ParameterSelectionMode,
    WalkForwardFinding,
    WalkForwardFindingCode,
    WalkForwardFold,
    WalkForwardMode,
    WalkForwardValidationReport,
)

UTC = timezone.utc
_HASHES = {"A": "a" * 64, "B": "b" * 64, "C": "c" * 64, "D": "d" * 64}


def _dt(s: str) -> datetime:
    return datetime.fromisoformat(s).replace(tzinfo=UTC)


def _iv(start: str, end: str) -> TemporalInterval:
    return TemporalInterval(_dt(start), _dt(end))


def _fold(fid: str, day: int) -> WalkForwardFold:
    start = _dt("2024-01-01") + timedelta(days=day)
    return WalkForwardFold(
        fold_id=fid,
        train_interval=_iv("2023-01-01T00:00:00", "2023-02-01T00:00:00"),
        validation_interval=None,
        oos_interval=TemporalInterval(start, start + timedelta(days=1)),
    )


def _valid(fid: str, day: int) -> FoldValidationResult:
    return FoldValidationResult(
        fold=_fold(fid, day), status=FoldValidationStatus.VALID, findings=()
    )


def _invalid(fid: str, day: int) -> FoldValidationResult:
    return FoldValidationResult(
        fold=_fold(fid, day),
        status=FoldValidationStatus.INVALID,
        findings=(WalkForwardFinding(code=WalkForwardFindingCode.DUPLICATE_FOLD_ID, fold_id=fid, message="dup"),),
    )


def _leakage(fid: str, day: int) -> FoldValidationResult:
    return FoldValidationResult(
        fold=_fold(fid, day),
        status=FoldValidationStatus.LEAKAGE_RISK,
        findings=(WalkForwardFinding(code=WalkForwardFindingCode.FOLD_EVIDENCE_MISSING, fold_id=fid, message="missing"),),
    )


def _insufficient(fid: str, day: int) -> FoldValidationResult:
    return FoldValidationResult(
        fold=_fold(fid, day),
        status=FoldValidationStatus.INSUFFICIENT_DATA,
        findings=(WalkForwardFinding(code=WalkForwardFindingCode.TRAIN_WARMUP_INSUFFICIENT, fold_id=fid, message="warmup"),),
    )


def _report(results, psm=ParameterSelectionMode.TRAIN_ONLY) -> WalkForwardValidationReport:
    return WalkForwardValidationReport(
        mode=WalkForwardMode.EXPANDING,
        parameter_selection_mode=psm,
        fold_results=tuple(results),
        report_findings=(),
    )


def _ev(fid: str, h: str) -> FoldParameterSelectionEvidence:
    return FoldParameterSelectionEvidence(
        fold_id=fid,
        selected_parameter_hash=_HASHES[h],
        latest_selection_information_at=_dt("2023-06-01T00:00:00"),
        selection_completed_at=_dt("2023-06-02T00:00:00"),
    )


def _fixed(h: str) -> FixedParameterEvidence:
    return FixedParameterEvidence(selected_parameter_hash=_HASHES[h])


def _eval(results, evidence=(), psm=ParameterSelectionMode.TRAIN_ONLY, fixed=None):
    return evaluate_parameter_drift(
        walk_forward_report=_report(results, psm=psm),
        fold_parameter_selection_evidence=evidence,
        fixed_parameter_evidence=fixed,
    )


# --------------------------------------------------------------------------
# FIXED mode semantics
# --------------------------------------------------------------------------


def test_fixed_mode_not_applicable_with_all_none_metrics() -> None:
    report = _eval(
        (_valid("F1", 0), _valid("F2", 1), _invalid("F3", 2)),
        psm=ParameterSelectionMode.FIXED,
        fixed=_fixed("A"),
    )
    assert report.resolution is ParameterDriftResolution.NOT_APPLICABLE
    assert report.parameter_selection_mode is ParameterSelectionMode.FIXED
    assert report.fixed_parameter_hash == _HASHES["A"]
    assert report.total_fold_count == 3
    assert report.valid_fold_count == 2
    assert report.non_valid_fold_count == 1
    assert report.transition_opportunity_count is None
    assert report.transition_count is None
    assert report.transition_rate is None
    assert report.unique_parameter_hash_count is None
    assert report.longest_observed_stable_run is None
    assert report.fold_observations == ()
    assert report.transitions == ()
    assert [f.code for f in report.findings] == [ParameterDriftFindingCode.FIXED_MODE_NOT_APPLICABLE]
    assert report.findings[0].fold_id is None


def test_fixed_mode_requires_fixed_evidence() -> None:
    with pytest.raises(ValueError):
        _eval((_valid("F1", 0),), psm=ParameterSelectionMode.FIXED)


def test_fixed_mode_rejects_per_fold_evidence() -> None:
    with pytest.raises(ValueError):
        _eval(
            (_valid("F1", 0),),
            evidence=(_ev("F1", "A"),),
            psm=ParameterSelectionMode.FIXED,
            fixed=_fixed("A"),
        )


def test_train_modes_reject_fixed_evidence() -> None:
    with pytest.raises(ValueError):
        _eval((_valid("F1", 0),), psm=ParameterSelectionMode.TRAIN_ONLY, fixed=_fixed("A"))
    with pytest.raises(ValueError):
        _eval((_valid("F1", 0),), psm=ParameterSelectionMode.TRAIN_VALIDATION, fixed=_fixed("A"))


# --------------------------------------------------------------------------
# Structural validation
# --------------------------------------------------------------------------


def test_duplicate_report_fold_id_rejected() -> None:
    with pytest.raises(ValueError):
        _eval((_valid("F1", 0), _valid("F1", 1)))


def test_duplicate_evidence_fold_id_rejected() -> None:
    with pytest.raises(ValueError):
        _eval((_valid("F1", 0),), evidence=(_ev("F1", "A"), _ev("F1", "B")))


def test_unknown_evidence_fold_id_rejected() -> None:
    with pytest.raises(ValueError):
        _eval((_valid("F1", 0),), evidence=(_ev("NOPE", "A"),))


def test_wrong_report_type_rejected() -> None:
    with pytest.raises(ValueError):
        evaluate_parameter_drift(walk_forward_report="not a report")


def test_evidence_entries_must_be_correct_type() -> None:
    with pytest.raises(ValueError):
        _eval((_valid("F1", 0),), evidence=("not evidence",))


# --------------------------------------------------------------------------
# Canonical ordering / shuffle invariance
# --------------------------------------------------------------------------


def test_evidence_input_shuffle_invariance() -> None:
    results = (_valid("F1", 0), _valid("F2", 1), _valid("F3", 2))
    evidence_a = (_ev("F1", "A"), _ev("F2", "B"), _ev("F3", "C"))
    evidence_b = (_ev("F3", "C"), _ev("F1", "A"), _ev("F2", "B"))
    assert _eval(results, evidence=evidence_a) == _eval(results, evidence=evidence_b)


def test_report_fold_order_shuffle_invariance() -> None:
    shuffled = (_valid("F3", 2), _valid("F1", 0), _valid("F2", 1))
    canonical = (_valid("F1", 0), _valid("F2", 1), _valid("F3", 2))
    evidence = (_ev("F1", "A"), _ev("F2", "B"), _ev("F3", "C"))
    a = _eval(shuffled, evidence=evidence)
    b = _eval(canonical, evidence=evidence)
    assert a == b
    assert [o.fold_id for o in a.fold_observations] == ["F1", "F2", "F3"]
    assert [t.from_fold_id for t in a.transitions] == ["F1", "F2"]


# --------------------------------------------------------------------------
# Resolution semantics
# --------------------------------------------------------------------------


def test_zero_valid_folds_insufficient_data() -> None:
    report = _eval((_invalid("F1", 0), _leakage("F2", 1), _insufficient("F3", 2)))
    assert report.resolution is ParameterDriftResolution.INSUFFICIENT_DATA
    assert report.observed_selection_count == 0
    assert report.transition_opportunity_count == 0
    assert report.transition_rate is None
    assert report.unique_parameter_hash_count == 0
    assert report.longest_observed_stable_run is None
    assert ParameterDriftFindingCode.INSUFFICIENT_OBSERVED_SELECTIONS in {f.code for f in report.findings}


def test_one_valid_observed_insufficient_data() -> None:
    report = _eval((_valid("F1", 0),), evidence=(_ev("F1", "A"),))
    assert report.resolution is ParameterDriftResolution.INSUFFICIENT_DATA
    assert report.observed_selection_count == 1
    assert report.transition_opportunity_count == 0
    assert report.transition_rate is None
    assert report.unique_parameter_hash_count == 1
    assert report.longest_observed_stable_run == 1


def test_five_valid_one_observed_four_missing_incomplete() -> None:
    results = tuple(_valid(f"F{i}", i) for i in range(5))
    report = _eval(results, evidence=(_ev("F0", "A"),))
    assert report.resolution is ParameterDriftResolution.INCOMPLETE_EVIDENCE
    assert report.observed_selection_count == 1
    assert report.missing_valid_selection_count == 4
    missing_codes = [f.code for f in report.findings if f.code is ParameterDriftFindingCode.VALID_FOLD_SELECTION_EVIDENCE_MISSING]
    assert len(missing_codes) == 4
    assert ParameterDriftFindingCode.INSUFFICIENT_OBSERVED_SELECTIONS not in {f.code for f in report.findings}


def test_missing_breaks_continuity_no_transition() -> None:
    report = _eval(
        (_valid("F1", 0), _valid("F2", 1), _valid("F3", 2)),
        evidence=(_ev("F1", "A"), _ev("F3", "B")),
    )
    assert report.resolution is ParameterDriftResolution.INCOMPLETE_EVIDENCE
    assert report.transitions == ()
    assert report.transition_opportunity_count == 0
    assert report.transition_rate is None
    assert report.unique_parameter_hash_count == 2
    assert report.longest_observed_stable_run == 1


# --------------------------------------------------------------------------
# Gap / continuity semantics
# --------------------------------------------------------------------------


def test_invalid_between_transition_skipped_one() -> None:
    report = _eval(
        (_valid("F1", 0), _invalid("F2", 1), _valid("F3", 2)),
        evidence=(_ev("F1", "A"), _ev("F3", "B")),
    )
    assert report.resolution is ParameterDriftResolution.RESOLVED
    assert len(report.transitions) == 1
    t = report.transitions[0]
    assert (t.from_fold_id, t.to_fold_id) == ("F1", "F3")
    assert t.changed is True
    assert t.skipped_non_valid_fold_count == 1
    assert report.transition_opportunity_count == 1
    assert report.transition_count == 1
    assert report.transition_rate == 1.0


def test_two_invalids_between_skipped_two() -> None:
    report = _eval(
        (_valid("F1", 0), _invalid("F2", 1), _leakage("F3", 2), _valid("F4", 3)),
        evidence=(_ev("F1", "A"), _ev("F4", "B")),
    )
    assert len(report.transitions) == 1
    assert report.transitions[0].skipped_non_valid_fold_count == 2
    assert report.non_valid_fold_count == 2


def test_non_valid_does_not_break_run() -> None:
    report = _eval(
        (_valid("F1", 0), _invalid("F2", 1), _valid("F3", 2)),
        evidence=(_ev("F1", "A"), _ev("F3", "A")),
    )
    assert report.longest_observed_stable_run == 2
    assert len(report.transitions) == 1
    assert report.transitions[0].changed is False
    assert report.transitions[0].skipped_non_valid_fold_count == 1
    assert report.transition_count == 0
    assert report.transition_rate == 0.0


def test_missing_valid_breaks_run() -> None:
    report = _eval(
        (_valid("F1", 0), _valid("F2", 1), _valid("F3", 2)),
        evidence=(_ev("F1", "A"), _ev("F3", "A")),
    )
    assert report.longest_observed_stable_run == 1
    assert report.transitions == ()


# --------------------------------------------------------------------------
# Metrics determinism
# --------------------------------------------------------------------------


def test_aa_transition_opportunity_preserved() -> None:
    report = _eval((_valid("F1", 0), _valid("F2", 1)), evidence=(_ev("F1", "A"), _ev("F2", "A")))
    assert report.resolution is ParameterDriftResolution.RESOLVED
    assert report.transition_opportunity_count == 1
    assert report.transition_count == 0
    assert report.transition_rate == 0.0
    assert report.transitions[0].changed is False


def test_ab_transition_counted() -> None:
    report = _eval((_valid("F1", 0), _valid("F2", 1)), evidence=(_ev("F1", "A"), _ev("F2", "B")))
    assert report.transition_count == 1
    assert report.transition_rate == 1.0


def test_all_same_hash() -> None:
    report = _eval(
        (_valid("F1", 0), _valid("F2", 1), _valid("F3", 2)),
        evidence=(_ev("F1", "A"), _ev("F2", "A"), _ev("F3", "A")),
    )
    assert report.transition_count == 0
    assert report.unique_parameter_hash_count == 1
    assert report.longest_observed_stable_run == 3


def test_all_unique_hashes() -> None:
    report = _eval(
        (_valid("F1", 0), _valid("F2", 1), _valid("F3", 2)),
        evidence=(_ev("F1", "A"), _ev("F2", "B"), _ev("F3", "C")),
    )
    assert report.transition_count == 2
    assert report.unique_parameter_hash_count == 3
    assert report.longest_observed_stable_run == 1


def test_alternating_hashes() -> None:
    report = _eval(
        (_valid("F1", 0), _valid("F2", 1), _valid("F3", 2), _valid("F4", 3)),
        evidence=(_ev("F1", "A"), _ev("F2", "B"), _ev("F3", "A"), _ev("F4", "B")),
    )
    assert report.transition_opportunity_count == 3
    assert report.transition_count == 3
    assert report.transition_rate == 1.0
    assert report.longest_observed_stable_run == 1


# --------------------------------------------------------------------------
# Non-VALID evidence handling
# --------------------------------------------------------------------------


def test_non_valid_supplied_evidence_ignored_but_auditable() -> None:
    report = _eval(
        (_valid("F1", 0), _invalid("F2", 1), _valid("F3", 2)),
        evidence=(_ev("F1", "A"), _ev("F2", "C"), _ev("F3", "B")),
    )
    assert report.ignored_non_valid_selection_evidence_count == 1
    obs = {o.fold_id: o for o in report.fold_observations}
    # Hash remains visible on the observation for auditability...
    assert obs["F2"].selected_parameter_hash == _HASHES["C"]
    assert obs["F2"].selection_evidence_supplied is True
    assert obs["F2"].fold_status is FoldValidationStatus.INVALID
    # ...but is excluded from every metric.
    assert report.unique_parameter_hash_count == 2
    assert [t.from_parameter_hash for t in report.transitions] == [_HASHES["A"]]
    assert [t.to_parameter_hash for t in report.transitions] == [_HASHES["B"]]
    assert ParameterDriftFindingCode.NON_VALID_SELECTION_EVIDENCE_IGNORED in {f.code for f in report.findings}
    ignored = [f for f in report.findings if f.code is ParameterDriftFindingCode.NON_VALID_SELECTION_EVIDENCE_IGNORED]
    assert len(ignored) == 1 and ignored[0].fold_id == "F2"


def test_non_valid_without_evidence_neutral() -> None:
    report = _eval(
        (_valid("F1", 0), _invalid("F2", 1)),
        evidence=(_ev("F1", "A"),),
    )
    assert report.ignored_non_valid_selection_evidence_count == 0
    obs = {o.fold_id: o for o in report.fold_observations}
    assert obs["F2"].selected_parameter_hash is None
    assert obs["F2"].selection_evidence_supplied is False


def test_structural_denominator_invariants() -> None:
    report = _eval(
        (_valid("F1", 0), _invalid("F2", 1), _leakage("F3", 2), _valid("F4", 3), _insufficient("F5", 4)),
        evidence=(_ev("F1", "A"), _ev("F4", "B")),
    )
    assert report.total_fold_count == 5
    assert report.total_fold_count == report.valid_fold_count + report.non_valid_fold_count
    assert report.valid_fold_count == 2
    assert report.non_valid_fold_count == 3
    assert report.observed_selection_count + report.missing_valid_selection_count == report.valid_fold_count
    assert report.observed_selection_count == 2
    assert report.missing_valid_selection_count == 0


# --------------------------------------------------------------------------
# Deterministic ordering of findings and transitions
# --------------------------------------------------------------------------


def test_findings_deterministically_sorted() -> None:
    report = _eval(
        (_valid("F1", 0), _valid("F2", 1), _valid("F3", 2)),
        evidence=(_ev("F1", "A"),),
    )
    keys = [(f.code.value, f.fold_id or "", f.message) for f in report.findings]
    assert keys == sorted(keys)


def test_transitions_follow_canonical_order() -> None:
    shuffled = (_valid("F3", 2), _valid("F1", 0), _valid("F2", 1))
    report = _eval(shuffled, evidence=(_ev("F1", "A"), _ev("F2", "B"), _ev("F3", "A")))
    assert [(t.from_fold_id, t.to_fold_id) for t in report.transitions] == [("F1", "F2"), ("F2", "F3")]


def test_train_validation_mode_identical_logic() -> None:
    report = _eval(
        (_valid("F1", 0), _valid("F2", 1)),
        evidence=(_ev("F1", "A"), _ev("F2", "B")),
        psm=ParameterSelectionMode.TRAIN_VALIDATION,
    )
    assert report.resolution is ParameterDriftResolution.RESOLVED
    assert report.parameter_selection_mode is ParameterSelectionMode.TRAIN_VALIDATION
    assert report.transition_count == 1
    assert report.transition_rate == 1.0


# --------------------------------------------------------------------------
# No score / label / revisit fields
# --------------------------------------------------------------------------


def test_no_score_label_revisit_fields() -> None:
    from src.services.strategy_lab.parameter_drift import ParameterDriftReport

    fields = {f.name for f in ParameterDriftReport.__dataclass_fields__.values()} if hasattr(ParameterDriftReport, "__dataclass_fields__") else set(inspect.signature(ParameterDriftReport).parameters)
    for forbidden in ("drift_score", "drift_label", "revisit_count"):
        assert forbidden not in fields
    # No severity/stability label field and no score field of any kind.
    assert not any(name.endswith("_label") for name in fields)
    assert not any(name.endswith("_score") for name in fields)


# --------------------------------------------------------------------------
# Purity: no persistence / no parameter-stability algorithm dependency
# --------------------------------------------------------------------------


def test_no_persistence_or_stability_imports() -> None:
    import src.services.strategy_lab.parameter_drift as module

    source = inspect.getsource(module)
    tree = ast.parse(source)
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if getattr(node, "level", 0) > 0:
                # Relative import: the dot count lives in node.level and
                # node.module carries the bare submodule path. A level-1
                # import from this module is a strategy_lab sibling.
                root = "src.services.strategy_lab." + (node.module or "")
            else:
                root = node.module or ""
            imported.add(root)
            imported.update(f"{root}.{alias.name}" for alias in node.names)
    forbidden_roots = ("src.storage", "src.repositories", "sqlalchemy")
    for item in imported:
        for root in forbidden_roots:
            assert not item.startswith(root), f"forbidden import {item!r}"
    # No parameter_stability dependency (algorithmic or import).
    for item in imported:
        assert "parameter_stability" not in item
    # Only closed Walk-Forward types may come from the sibling module.
    from_walk_forward = sorted(item for item in imported if item.startswith("src.services.strategy_lab.walk_forward"))
    assert from_walk_forward == sorted([
        "src.services.strategy_lab.walk_forward",
        "src.services.strategy_lab.walk_forward.FixedParameterEvidence",
        "src.services.strategy_lab.walk_forward.FoldParameterSelectionEvidence",
        "src.services.strategy_lab.walk_forward.FoldValidationResult",
        "src.services.strategy_lab.walk_forward.FoldValidationStatus",
        "src.services.strategy_lab.walk_forward.ParameterSelectionMode",
        "src.services.strategy_lab.walk_forward.WalkForwardValidationReport",
    ])

# --------------------------------------------------------------------------
# Trust boundary: swapped evidence is NOT detected (documented limitation)
# --------------------------------------------------------------------------


def test_swapped_evidence_is_undetectable_trust_boundary() -> None:
    """The module binds evidence only via fold_id; swapping hashes between
    two folds produces a different (but silently accepted) result. This is
    the documented trust boundary -- the test pins it so nobody later
    claims the module proves WF-invocation binding."""

    results = (_valid("F1", 0), _valid("F2", 1))
    truthful = _eval(results, evidence=(_ev("F1", "A"), _ev("F2", "B")))
    swapped = _eval(results, evidence=(_ev("F1", "B"), _ev("F2", "A")))
    # No error is raised; the module simply reports the swapped identities.
    assert swapped.transition_opportunity_count == truthful.transition_opportunity_count
    assert swapped.fold_observations[0].selected_parameter_hash == _HASHES["B"]
    assert truthful.fold_observations[0].selected_parameter_hash == _HASHES["A"]


def test_trust_boundary_documented_in_module_docstring() -> None:
    import src.services.strategy_lab.parameter_drift as module

    doc = module.__doc__ or ""
    assert "opaque caller-supplied identity evidence" in doc
    assert "does NOT prove payload equality" in doc
    assert "parameter-search-space consistency" in doc
    assert "hash canonicalization-policy consistency" in doc
    assert "exact evidence originally used" in doc
