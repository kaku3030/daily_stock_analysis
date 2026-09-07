import dataclasses
import inspect
from datetime import datetime, timezone
from pathlib import Path

import pytest

from src.services.strategy_lab.experiment_governance import (
    ExperimentManifest,
    LineageAuditContext,
    ParameterOrigin,
    ParameterOriginType,
    audit_experiment_lineage,
)
from src.services.strategy_lab.information_dependency import (
    AvailabilityLag,
    AvailabilityLagKind,
    DeclarationStatus,
    DependencyDeclaration,
    FeatureDependency,
    FeatureDependencyDeclaration,
    FeatureSetDependency,
    InformationDependencyDeclaration,
    LabelDependency,
    StateCarryMode,
    StateDependency,
    evaluate_information_dependency,
)
from src.services.strategy_lab.temporal_contract import TemporalInterval
from src.services.strategy_lab.universe_integrity import (
    UniverseMembershipAnchor,
    UniverseMembershipFacts,
    resolve_universe_membership,
)
from src.services.strategy_lab.walk_forward import (
    FixedParameterEvidence,
    FoldDataEvidence,
    FoldParameterSelectionEvidence,
    FoldSeparationEvidence,
    FoldUniverseIntegrityEvidence,
    FoldValidationResult,
    FoldValidationStatus,
    ParameterSelectionMode,
    UniverseIntegrityRequirement,
    WalkForwardFinding,
    WalkForwardFindingCode,
    WalkForwardFold,
    WalkForwardMode,
    WalkForwardValidationReport,
    compute_contamination_policy_fingerprint,
    compute_evaluation_protocol_fingerprint,
    compute_window_configuration_fingerprint,
    validate_walk_forward,
)

UTC = timezone.utc
VALID = FoldValidationStatus.VALID
INVALID = FoldValidationStatus.INVALID
LEAKAGE_RISK = FoldValidationStatus.LEAKAGE_RISK
INSUFFICIENT_DATA = FoldValidationStatus.INSUFFICIENT_DATA


def _dt(s: str) -> datetime:
    return datetime.fromisoformat(s).replace(tzinfo=UTC)


def _codes(result: FoldValidationResult) -> set:
    return {f.code for f in result.findings}


def _result_for(report: WalkForwardValidationReport, fold_id: str) -> FoldValidationResult:
    return next(r for r in report.fold_results if r.fold.fold_id == fold_id)


# ---- information dependency declaration builders ----


def _valid_declaration(feature_grid: str = "1d", label_grid: str = "1d") -> InformationDependencyDeclaration:
    return InformationDependencyDeclaration(
        contract_version="v1",
        feature_set=DependencyDeclaration(
            status=DeclarationStatus.DECLARED,
            payload=FeatureSetDependency(
                evaluation_bar_grid_id=feature_grid,
                features=(
                    FeatureDependencyDeclaration(
                        feature_id="f1",
                        status=DeclarationStatus.DECLARED,
                        payload=FeatureDependency(
                            bar_grid_id=feature_grid,
                            lookback_bars=5,
                            availability_lag=AvailabilityLag(kind=AvailabilityLagKind.BAR_COUNT, bars=0),
                        ),
                    ),
                ),
            ),
        ),
        label=DependencyDeclaration(
            status=DeclarationStatus.DECLARED,
            payload=LabelDependency(
                bar_grid_id=label_grid,
                information_horizon_bars=3,
                availability_lag=AvailabilityLag(kind=AvailabilityLagKind.BAR_COUNT, bars=1),
            ),
        ),
        state=DependencyDeclaration(status=DeclarationStatus.DECLARED, payload=StateDependency(carry_mode=StateCarryMode.STATELESS)),
        overlap=DependencyDeclaration(status=DeclarationStatus.NOT_APPLICABLE, reason="single sample stream"),
    )


def _undeclared_label_declaration() -> InformationDependencyDeclaration:
    return InformationDependencyDeclaration(
        contract_version="v1",
        feature_set=DependencyDeclaration(
            status=DeclarationStatus.DECLARED,
            payload=FeatureSetDependency(
                evaluation_bar_grid_id="1d",
                features=(
                    FeatureDependencyDeclaration(
                        feature_id="f1",
                        status=DeclarationStatus.DECLARED,
                        payload=FeatureDependency(
                            bar_grid_id="1d", lookback_bars=5,
                            availability_lag=AvailabilityLag(kind=AvailabilityLagKind.BAR_COUNT, bars=0),
                        ),
                    ),
                ),
            ),
        ),
        label=DependencyDeclaration(status=DeclarationStatus.UNDECLARED),
        state=DependencyDeclaration(status=DeclarationStatus.DECLARED, payload=StateDependency(carry_mode=StateCarryMode.STATELESS)),
        overlap=DependencyDeclaration(status=DeclarationStatus.NOT_APPLICABLE, reason="single sample stream"),
    )


def _undeclared_feature_declaration() -> InformationDependencyDeclaration:
    return InformationDependencyDeclaration(
        contract_version="v1",
        feature_set=DependencyDeclaration(status=DeclarationStatus.UNDECLARED),
        label=DependencyDeclaration(
            status=DeclarationStatus.DECLARED,
            payload=LabelDependency(
                bar_grid_id="1d", information_horizon_bars=0,
                availability_lag=AvailabilityLag(kind=AvailabilityLagKind.BAR_COUNT, bars=0),
            ),
        ),
        state=DependencyDeclaration(status=DeclarationStatus.DECLARED, payload=StateDependency(carry_mode=StateCarryMode.STATELESS)),
        overlap=DependencyDeclaration(status=DeclarationStatus.NOT_APPLICABLE, reason="single sample stream"),
    )


def _state_only_warmup_declaration(state_grid: str = "1d", warmup_bars: int = 5) -> InformationDependencyDeclaration:
    """feature_set NOT_APPLICABLE, positive warmup driven entirely by a
    DECLARED COLD_START state -- the constructible case Fix 1 targets.
    """

    return InformationDependencyDeclaration(
        contract_version="v1",
        feature_set=DependencyDeclaration(status=DeclarationStatus.NOT_APPLICABLE, reason="no features"),
        label=DependencyDeclaration(
            status=DeclarationStatus.DECLARED,
            payload=LabelDependency(
                bar_grid_id="1d", information_horizon_bars=0,
                availability_lag=AvailabilityLag(kind=AvailabilityLagKind.BAR_COUNT, bars=0),
            ),
        ),
        state=DependencyDeclaration(
            status=DeclarationStatus.DECLARED,
            payload=StateDependency(
                carry_mode=StateCarryMode.COLD_START, convergence_warmup_bars=warmup_bars, bar_grid_id=state_grid
            ),
        ),
        overlap=DependencyDeclaration(status=DeclarationStatus.NOT_APPLICABLE, reason="single sample stream"),
    )


# ---- manifest / lineage builders ----


def _components_for(info_dep, universe_req, mode, folds, parameter_selection_mode) -> dict:
    return {
        "information_dependency": info_dep.contract_fingerprint,
        "universe_policy": universe_req.fingerprint,
        "window_configuration": compute_window_configuration_fingerprint(mode=mode, folds=folds),
        "contamination_policy": compute_contamination_policy_fingerprint(parameter_selection_mode=parameter_selection_mode),
        "evaluation_protocol": compute_evaluation_protocol_fingerprint(),
    }


def _manifest_with_components(experiment_id, components, *, parent=None, root=None) -> ExperimentManifest:
    return ExperimentManifest(
        experiment_id=experiment_id,
        schema_version="v1",
        governed_components=components,
        created_at=_dt("2020-01-01T00:00:00"),
        root_experiment_id=root or experiment_id,
        parent_experiment_id=parent,
    )


def _lineage_for(manifest, prior=(), history_complete=True):
    return audit_experiment_lineage(
        manifest=manifest, prior_manifests=prior, context=LineageAuditContext(history_complete=history_complete)
    )


# ---- base valid fixtures ----


def _base_fixed_case() -> dict:
    folds = (
        WalkForwardFold(
            "f1", TemporalInterval(_dt("2020-01-01"), _dt("2020-06-01")), None,
            TemporalInterval(_dt("2020-06-01"), _dt("2020-07-01")),
        ),
        WalkForwardFold(
            "f2", TemporalInterval(_dt("2020-01-01"), _dt("2020-08-01")), None,
            TemporalInterval(_dt("2020-08-01"), _dt("2020-09-01")),
        ),
    )
    info_dep = evaluate_information_dependency(_valid_declaration())
    universe_req = UniverseIntegrityRequirement(False, False, False)
    components = _components_for(info_dep, universe_req, WalkForwardMode.EXPANDING, folds, ParameterSelectionMode.FIXED)
    manifest = _manifest_with_components("E1", components)
    lineage = _lineage_for(manifest)
    param_origin = ParameterOrigin(
        origin_type=ParameterOriginType.LITERATURE, source_ref="paper", parameter_hash="HASH1",
        declared_at=_dt("2019-01-01"), information_horizon_end=_dt("2019-01-01"),
    )
    fixed_evidence = FixedParameterEvidence(selected_parameter_hash="HASH1")
    separation = tuple(
        FoldSeparationEvidence(
            fold_id=f.fold_id, purge_bar_grid_id="1d", applied_train_to_validation_purge_bars=None,
            applied_pre_oos_purge_bars=4, applied_embargo_bars=0,
        )
        for f in folds
    )
    data = tuple(
        FoldDataEvidence(
            fold_id=f.fold_id, bar_grid_id="1d", usable_train_bars=100,
            usable_validation_bars=None, usable_oos_bars=20,
        )
        for f in folds
    )
    return dict(
        manifest=manifest, mode=WalkForwardMode.EXPANDING, parameter_selection_mode=ParameterSelectionMode.FIXED,
        folds=folds, information_dependency=info_dep, lineage_audit=lineage,
        parameter_origin=param_origin, fixed_parameter_evidence=fixed_evidence,
        fold_parameter_selection_evidence=(), separation_evidence=separation, data_evidence=data,
        universe_requirement=universe_req, universe_integrity_evidence=(),
    )


def _base_train_only_case() -> dict:
    folds = (
        WalkForwardFold(
            "f1", TemporalInterval(_dt("2020-01-01"), _dt("2020-04-01")), None,
            TemporalInterval(_dt("2020-04-01"), _dt("2020-05-01")),
        ),
        WalkForwardFold(
            "f2", TemporalInterval(_dt("2020-02-01"), _dt("2020-06-01")), None,
            TemporalInterval(_dt("2020-06-01"), _dt("2020-07-01")),
        ),
    )
    info_dep = evaluate_information_dependency(_valid_declaration())
    universe_req = UniverseIntegrityRequirement(False, False, False)
    components = _components_for(info_dep, universe_req, WalkForwardMode.ROLLING, folds, ParameterSelectionMode.TRAIN_ONLY)
    manifest = _manifest_with_components("E2", components)
    lineage = _lineage_for(manifest)
    selection = (
        FoldParameterSelectionEvidence(
            fold_id="f1", selected_parameter_hash="H",
            latest_selection_information_at=_dt("2020-03-25"), selection_completed_at=_dt("2020-03-28"),
        ),
        FoldParameterSelectionEvidence(
            fold_id="f2", selected_parameter_hash="H",
            latest_selection_information_at=_dt("2020-05-25"), selection_completed_at=_dt("2020-05-28"),
        ),
    )
    separation = tuple(
        FoldSeparationEvidence(
            fold_id=f.fold_id, purge_bar_grid_id="1d", applied_train_to_validation_purge_bars=None,
            applied_pre_oos_purge_bars=4, applied_embargo_bars=0,
        )
        for f in folds
    )
    data = tuple(
        FoldDataEvidence(
            fold_id=f.fold_id, bar_grid_id="1d", usable_train_bars=100,
            usable_validation_bars=None, usable_oos_bars=20,
        )
        for f in folds
    )
    return dict(
        manifest=manifest, mode=WalkForwardMode.ROLLING, parameter_selection_mode=ParameterSelectionMode.TRAIN_ONLY,
        folds=folds, information_dependency=info_dep, lineage_audit=lineage,
        parameter_origin=None, fixed_parameter_evidence=None,
        fold_parameter_selection_evidence=selection, separation_evidence=separation, data_evidence=data,
        universe_requirement=universe_req, universe_integrity_evidence=(),
    )


def _base_train_validation_case() -> dict:
    folds = (
        WalkForwardFold(
            "f1", TemporalInterval(_dt("2020-01-01"), _dt("2020-04-01")),
            TemporalInterval(_dt("2020-04-01"), _dt("2020-05-01")),
            TemporalInterval(_dt("2020-05-01"), _dt("2020-06-01")),
        ),
        WalkForwardFold(
            "f2", TemporalInterval(_dt("2020-01-01"), _dt("2020-06-01")),
            TemporalInterval(_dt("2020-06-01"), _dt("2020-07-01")),
            TemporalInterval(_dt("2020-07-01"), _dt("2020-08-01")),
        ),
    )
    info_dep = evaluate_information_dependency(_valid_declaration())
    universe_req = UniverseIntegrityRequirement(False, False, False)
    components = _components_for(
        info_dep, universe_req, WalkForwardMode.EXPANDING, folds, ParameterSelectionMode.TRAIN_VALIDATION
    )
    manifest = _manifest_with_components("E3", components)
    lineage = _lineage_for(manifest)
    selection = (
        FoldParameterSelectionEvidence(
            fold_id="f1", selected_parameter_hash="H",
            latest_selection_information_at=_dt("2020-04-25"), selection_completed_at=_dt("2020-04-28"),
        ),
        FoldParameterSelectionEvidence(
            fold_id="f2", selected_parameter_hash="H",
            latest_selection_information_at=_dt("2020-06-25"), selection_completed_at=_dt("2020-06-28"),
        ),
    )
    separation = tuple(
        FoldSeparationEvidence(
            fold_id=f.fold_id, purge_bar_grid_id="1d", applied_train_to_validation_purge_bars=4,
            applied_pre_oos_purge_bars=4, applied_embargo_bars=0,
        )
        for f in folds
    )
    data = tuple(
        FoldDataEvidence(
            fold_id=f.fold_id, bar_grid_id="1d", usable_train_bars=100,
            usable_validation_bars=30, usable_oos_bars=20,
        )
        for f in folds
    )
    return dict(
        manifest=manifest, mode=WalkForwardMode.EXPANDING, parameter_selection_mode=ParameterSelectionMode.TRAIN_VALIDATION,
        folds=folds, information_dependency=info_dep, lineage_audit=lineage,
        parameter_origin=None, fixed_parameter_evidence=None,
        fold_parameter_selection_evidence=selection, separation_evidence=separation, data_evidence=data,
        universe_requirement=universe_req, universe_integrity_evidence=(),
    )


def _with_universe(case: dict, universe_req: UniverseIntegrityRequirement, evidence: tuple) -> dict:
    new_components = _components_for(
        case["information_dependency"], universe_req, case["mode"], case["folds"], case["parameter_selection_mode"]
    )
    new_case = dict(case)
    new_case["manifest"] = _manifest_with_components(case["manifest"].experiment_id, new_components)
    new_case["universe_requirement"] = universe_req
    new_case["universe_integrity_evidence"] = evidence
    return new_case


def _conflict_membership_resolution():
    a = _dt("2021-01-01")
    anchor1 = UniverseMembershipAnchor(universe_id="U1", members=frozenset({"A"}), effective_at=a, available_at=a)
    anchor2 = UniverseMembershipAnchor(universe_id="U1", members=frozenset({"B"}), effective_at=a, available_at=a)
    facts = UniverseMembershipFacts(universe_id="U1", anchors=(anchor1, anchor2), events=())
    return resolve_universe_membership(facts, as_of=a, decision_time=a)


def _indeterminate_membership_resolution():
    facts = UniverseMembershipFacts(universe_id="U1", anchors=(), events=())
    return resolve_universe_membership(facts, as_of=_dt("2021-01-01"), decision_time=_dt("2021-01-01"))


# ==========================================================================
# Valid scenarios
# ==========================================================================


def test_valid_expanding_fixed() -> None:
    report = validate_walk_forward(**_base_fixed_case())
    assert report.total_fold_count == 2
    assert report.valid_fold_count == 2
    for r in report.fold_results:
        assert r.status is VALID
        assert r.findings == ()
    assert report.performance_eligible_fold_ids == ("f1", "f2")
    assert report.report_findings == ()


def test_valid_rolling_train_only() -> None:
    report = validate_walk_forward(**_base_train_only_case())
    assert report.valid_fold_count == 2
    assert report.performance_eligible_fold_ids == ("f1", "f2")


def test_valid_train_validation() -> None:
    report = validate_walk_forward(**_base_train_validation_case())
    assert report.valid_fold_count == 2
    assert report.performance_eligible_fold_ids == ("f1", "f2")


# ==========================================================================
# Fold-set geometry
# ==========================================================================


def test_duplicate_fold_id() -> None:
    case = _base_fixed_case()
    folds = case["folds"]
    dup_fold = WalkForwardFold(
        folds[0].fold_id, TemporalInterval(_dt("2020-01-01"), _dt("2020-06-01")), None,
        TemporalInterval(_dt("2020-06-01"), _dt("2020-07-01")),
    )
    case["folds"] = (folds[0], dup_fold)
    report = validate_walk_forward(**case)
    for r in report.fold_results:
        assert WalkForwardFindingCode.DUPLICATE_FOLD_ID in _codes(r)
        assert r.status is INVALID


def test_invalid_fold_internal_geometry() -> None:
    case = _base_fixed_case()
    folds = list(case["folds"])
    folds[0] = WalkForwardFold(
        "f1", TemporalInterval(_dt("2020-06-01"), _dt("2020-07-01")), None,
        TemporalInterval(_dt("2020-06-01"), _dt("2020-06-15")),
    )
    case["folds"] = tuple(folds)
    report = validate_walk_forward(**case)
    r1 = _result_for(report, "f1")
    assert WalkForwardFindingCode.INVALID_FOLD_GEOMETRY in _codes(r1)
    assert r1.status is INVALID


def test_expanding_non_expansion() -> None:
    case = _base_fixed_case()
    folds = list(case["folds"])
    folds[1] = WalkForwardFold(
        "f2", TemporalInterval(_dt("2020-02-01"), _dt("2020-08-01")), None,
        TemporalInterval(_dt("2020-08-01"), _dt("2020-09-01")),
    )
    case["folds"] = tuple(folds)
    report = validate_walk_forward(**case)
    r2 = _result_for(report, "f2")
    assert WalkForwardFindingCode.INVALID_MODE_GEOMETRY in _codes(r2)


def test_rolling_order_violation() -> None:
    case = _base_train_only_case()
    folds = list(case["folds"])
    folds[1] = WalkForwardFold(
        "f2", TemporalInterval(_dt("2020-01-01"), _dt("2020-06-01")), None,
        TemporalInterval(_dt("2020-06-01"), _dt("2020-07-01")),
    )
    case["folds"] = tuple(folds)
    report = validate_walk_forward(**case)
    r2 = _result_for(report, "f2")
    assert WalkForwardFindingCode.INVALID_MODE_GEOMETRY in _codes(r2)


def test_overlapping_oos() -> None:
    case = _base_fixed_case()
    folds = list(case["folds"])
    folds[1] = WalkForwardFold(
        "f2", TemporalInterval(_dt("2020-01-01"), _dt("2020-08-01")), None,
        TemporalInterval(_dt("2020-06-15"), _dt("2020-09-01")),
    )
    case["folds"] = tuple(folds)
    report = validate_walk_forward(**case)
    r2 = _result_for(report, "f2")
    assert WalkForwardFindingCode.OOS_OVERLAP in _codes(r2)
    r1 = _result_for(report, "f1")
    assert WalkForwardFindingCode.OOS_OVERLAP not in _codes(r1)


def test_train_validation_missing_validation() -> None:
    case = _base_train_validation_case()
    folds = list(case["folds"])
    folds[0] = WalkForwardFold(
        "f1", TemporalInterval(_dt("2020-01-01"), _dt("2020-04-01")), None,
        TemporalInterval(_dt("2020-05-01"), _dt("2020-06-01")),
    )
    case["folds"] = tuple(folds)
    report = validate_walk_forward(**case)
    r1 = _result_for(report, "f1")
    assert WalkForwardFindingCode.VALIDATION_REQUIRED in _codes(r1)
    assert r1.status is INVALID


# ==========================================================================
# Manifest binding
# ==========================================================================


def test_manifest_lineage_experiment_id_mismatch() -> None:
    case = _base_fixed_case()
    other_manifest = _manifest_with_components(
        "OTHER", _components_for(
            case["information_dependency"], case["universe_requirement"], case["mode"], case["folds"],
            case["parameter_selection_mode"],
        ),
    )
    other_lineage = _lineage_for(other_manifest)
    case["lineage_audit"] = other_lineage
    report = validate_walk_forward(**case)
    assert report.total_fold_count == len(case["folds"])
    for r in report.fold_results:
        assert r.status is INVALID
        assert WalkForwardFindingCode.EXPERIMENT_IDENTITY_MISMATCH in _codes(r)
    assert any(
        f.code is WalkForwardFindingCode.EXPERIMENT_IDENTITY_MISMATCH and f.fold_id is None
        for f in report.report_findings
    )
    assert report.performance_eligible_fold_ids == ()


@pytest.mark.parametrize(
    "key,code",
    [
        ("information_dependency", WalkForwardFindingCode.INFORMATION_DEPENDENCY_UNBOUND),
        ("universe_policy", WalkForwardFindingCode.UNIVERSE_POLICY_UNBOUND),
        ("window_configuration", WalkForwardFindingCode.WINDOW_CONFIGURATION_UNBOUND),
        ("contamination_policy", WalkForwardFindingCode.CONTAMINATION_POLICY_UNBOUND),
        ("evaluation_protocol", WalkForwardFindingCode.EVALUATION_PROTOCOL_UNBOUND),
    ],
)
def test_each_mandatory_manifest_key_missing(key, code) -> None:
    case = _base_fixed_case()
    components = _components_for(
        case["information_dependency"], case["universe_requirement"], case["mode"], case["folds"],
        case["parameter_selection_mode"],
    )
    del components[key]
    case["manifest"] = _manifest_with_components("E1", components)
    report = validate_walk_forward(**case)
    assert any(f.code is code and f.fold_id is None for f in report.report_findings)
    for r in report.fold_results:
        assert code in _codes(r)
        assert r.status is INVALID


@pytest.mark.parametrize(
    "key,code",
    [
        ("information_dependency", WalkForwardFindingCode.INFORMATION_DEPENDENCY_UNBOUND),
        ("universe_policy", WalkForwardFindingCode.UNIVERSE_POLICY_UNBOUND),
        ("window_configuration", WalkForwardFindingCode.WINDOW_CONFIGURATION_UNBOUND),
        ("contamination_policy", WalkForwardFindingCode.CONTAMINATION_POLICY_UNBOUND),
        ("evaluation_protocol", WalkForwardFindingCode.EVALUATION_PROTOCOL_UNBOUND),
    ],
)
def test_each_mandatory_manifest_key_fingerprint_mismatch(key, code) -> None:
    case = _base_fixed_case()
    components = _components_for(
        case["information_dependency"], case["universe_requirement"], case["mode"], case["folds"],
        case["parameter_selection_mode"],
    )
    components[key] = "0" * 64
    case["manifest"] = _manifest_with_components("E1", components)
    report = validate_walk_forward(**case)
    for r in report.fold_results:
        assert code in _codes(r)
        assert r.status is INVALID


def test_information_dependency_swap_blocked() -> None:
    case = _base_fixed_case()
    other = evaluate_information_dependency(_valid_declaration(label_grid="4h"))
    case["information_dependency"] = other
    report = validate_walk_forward(**case)
    for r in report.fold_results:
        assert WalkForwardFindingCode.INFORMATION_DEPENDENCY_UNBOUND in _codes(r)


def test_universe_policy_swap_blocked() -> None:
    case = _base_fixed_case()
    case["universe_requirement"] = UniverseIntegrityRequirement(True, False, False)
    report = validate_walk_forward(**case)
    for r in report.fold_results:
        assert WalkForwardFindingCode.UNIVERSE_POLICY_UNBOUND in _codes(r)


# ==========================================================================
# FIXED parameter provenance
# ==========================================================================


def test_fixed_horizon_inside_train_blocked() -> None:
    case = _base_fixed_case()
    case["parameter_origin"] = ParameterOrigin(
        origin_type=ParameterOriginType.LITERATURE, source_ref="paper", parameter_hash="HASH1",
        declared_at=_dt("2020-01-01"), information_horizon_end=_dt("2020-01-01"),
    )
    report = validate_walk_forward(**case)
    for r in report.fold_results:
        assert WalkForwardFindingCode.PARAMETER_ORIGIN_INFORMATION_HORIZON_VIOLATION in _codes(r)
        assert r.status is LEAKAGE_RISK


def test_fixed_declared_at_inside_train_blocked() -> None:
    case = _base_fixed_case()
    case["parameter_origin"] = ParameterOrigin(
        origin_type=ParameterOriginType.LITERATURE, source_ref="paper", parameter_hash="HASH1",
        declared_at=_dt("2020-01-01"), information_horizon_end=_dt("2019-01-01"),
    )
    report = validate_walk_forward(**case)
    for r in report.fold_results:
        assert WalkForwardFindingCode.PARAMETER_ORIGIN_DECLARED_AT_VIOLATION in _codes(r)
        assert r.status is LEAKAGE_RISK


def test_fixed_parameter_hash_mismatch() -> None:
    case = _base_fixed_case()
    case["fixed_parameter_evidence"] = FixedParameterEvidence(selected_parameter_hash="WRONG")
    report = validate_walk_forward(**case)
    for r in report.fold_results:
        assert WalkForwardFindingCode.PARAMETER_HASH_MISMATCH in _codes(r)
        assert r.status is INVALID


def test_fixed_self_origin_experiment() -> None:
    case = _base_fixed_case()
    case["parameter_origin"] = ParameterOrigin(
        origin_type=ParameterOriginType.PRIOR_EXPERIMENT, source_ref="paper", parameter_hash="HASH1",
        declared_at=_dt("2019-01-01"), information_horizon_end=_dt("2019-01-01"),
        origin_experiment_id="E1",
    )
    report = validate_walk_forward(**case)
    for r in report.fold_results:
        assert WalkForwardFindingCode.PARAMETER_ORIGIN_SELF_REFERENCE in _codes(r)
        assert r.status is INVALID


def test_fixed_missing_parameter_origin_is_auditable() -> None:
    case = _base_fixed_case()
    case["parameter_origin"] = None
    report = validate_walk_forward(**case)
    assert report.total_fold_count == len(case["folds"])
    for r in report.fold_results:
        assert WalkForwardFindingCode.PARAMETER_ORIGIN_REQUIRED in _codes(r)
        assert r.status is INVALID
    assert any(
        f.code is WalkForwardFindingCode.PARAMETER_ORIGIN_REQUIRED and f.fold_id is None
        for f in report.report_findings
    )
    assert report.performance_eligible_fold_ids == ()


def test_fixed_missing_fixed_parameter_evidence_is_auditable() -> None:
    case = _base_fixed_case()
    case["fixed_parameter_evidence"] = None
    report = validate_walk_forward(**case)
    assert report.total_fold_count == len(case["folds"])
    for r in report.fold_results:
        assert WalkForwardFindingCode.FIXED_EVIDENCE_REQUIRED in _codes(r)
        assert r.status is INVALID
    assert any(
        f.code is WalkForwardFindingCode.FIXED_EVIDENCE_REQUIRED and f.fold_id is None
        for f in report.report_findings
    )


def test_fixed_forbidden_fold_selection_evidence_is_auditable() -> None:
    case = _base_fixed_case()
    case["fold_parameter_selection_evidence"] = (
        FoldParameterSelectionEvidence(
            fold_id="f1", selected_parameter_hash="H",
            latest_selection_information_at=_dt("2020-01-02"), selection_completed_at=_dt("2020-01-03"),
        ),
    )
    report = validate_walk_forward(**case)
    assert report.total_fold_count == len(case["folds"])
    for r in report.fold_results:
        assert WalkForwardFindingCode.FORBIDDEN_FOLD_SELECTION_EVIDENCE_UNDER_FIXED in _codes(r)
        assert r.status is INVALID
    assert any(
        f.code is WalkForwardFindingCode.FORBIDDEN_FOLD_SELECTION_EVIDENCE_UNDER_FIXED and f.fold_id is None
        for f in report.report_findings
    )


def test_fixed_zero_fold_hash_mismatch_and_self_reference_still_auditable() -> None:
    info_dep = evaluate_information_dependency(_valid_declaration())
    universe_req = UniverseIntegrityRequirement(False, False, False)
    components = _components_for(info_dep, universe_req, WalkForwardMode.EXPANDING, (), ParameterSelectionMode.FIXED)
    manifest = _manifest_with_components("E1", components)
    lineage = _lineage_for(manifest)
    param_origin = ParameterOrigin(
        origin_type=ParameterOriginType.PRIOR_EXPERIMENT, source_ref="paper", parameter_hash="HASH1",
        declared_at=_dt("2019-01-01"), information_horizon_end=_dt("2019-01-01"),
        origin_experiment_id="E1",
    )
    report = validate_walk_forward(
        manifest=manifest, mode=WalkForwardMode.EXPANDING, parameter_selection_mode=ParameterSelectionMode.FIXED,
        folds=(), information_dependency=info_dep, lineage_audit=lineage,
        parameter_origin=param_origin, fixed_parameter_evidence=FixedParameterEvidence(selected_parameter_hash="WRONG"),
        fold_parameter_selection_evidence=(), separation_evidence=(), data_evidence=(),
        universe_requirement=universe_req, universe_integrity_evidence=(),
    )
    assert report.total_fold_count == 0
    assert any(f.code is WalkForwardFindingCode.PARAMETER_HASH_MISMATCH for f in report.report_findings)
    assert any(f.code is WalkForwardFindingCode.PARAMETER_ORIGIN_SELF_REFERENCE for f in report.report_findings)
    assert not any(
        f.code in (
            WalkForwardFindingCode.PARAMETER_ORIGIN_INFORMATION_HORIZON_VIOLATION,
            WalkForwardFindingCode.PARAMETER_ORIGIN_DECLARED_AT_VIOLATION,
        )
        for f in report.report_findings
    )


def test_state_only_warmup_wrong_grid() -> None:
    case = _base_fixed_case()
    info_dep = evaluate_information_dependency(_state_only_warmup_declaration(state_grid="1d", warmup_bars=5))
    case["information_dependency"] = info_dep
    components = _components_for(
        info_dep, case["universe_requirement"], case["mode"], case["folds"], case["parameter_selection_mode"]
    )
    case["manifest"] = _manifest_with_components("E1", components)
    data = list(case["data_evidence"])
    data[0] = FoldDataEvidence(fold_id="f1", bar_grid_id="1m", usable_train_bars=100, usable_validation_bars=None, usable_oos_bars=20)
    case["data_evidence"] = tuple(data)
    report = validate_walk_forward(**case)
    r1 = _result_for(report, "f1")
    assert WalkForwardFindingCode.BAR_GRID_MISMATCH in _codes(r1)
    assert r1.status is INVALID


def test_state_only_warmup_correct_grid_allowed() -> None:
    case = _base_fixed_case()
    info_dep = evaluate_information_dependency(_state_only_warmup_declaration(state_grid="1d", warmup_bars=5))
    case["information_dependency"] = info_dep
    components = _components_for(
        info_dep, case["universe_requirement"], case["mode"], case["folds"], case["parameter_selection_mode"]
    )
    case["manifest"] = _manifest_with_components("E1", components)
    report = validate_walk_forward(**case)
    for r in report.fold_results:
        assert WalkForwardFindingCode.BAR_GRID_MISMATCH not in _codes(r)


# ==========================================================================
# TRAIN_ONLY / TRAIN_VALIDATION selection timing
# ==========================================================================


def test_train_only_selection_exactly_train_end_rejected() -> None:
    case = _base_train_only_case()
    selection = list(case["fold_parameter_selection_evidence"])
    selection[0] = FoldParameterSelectionEvidence(
        fold_id="f1", selected_parameter_hash="H",
        latest_selection_information_at=_dt("2020-04-01"), selection_completed_at=_dt("2020-04-05"),
    )
    case["fold_parameter_selection_evidence"] = tuple(selection)
    report = validate_walk_forward(**case)
    r1 = _result_for(report, "f1")
    assert WalkForwardFindingCode.PARAMETER_SELECTION_OUTSIDE_ALLOWED_WINDOW in _codes(r1)


def test_train_validation_selection_exactly_validation_end_rejected() -> None:
    case = _base_train_validation_case()
    selection = list(case["fold_parameter_selection_evidence"])
    selection[0] = FoldParameterSelectionEvidence(
        fold_id="f1", selected_parameter_hash="H",
        latest_selection_information_at=_dt("2020-05-01"), selection_completed_at=_dt("2020-05-05"),
    )
    case["fold_parameter_selection_evidence"] = tuple(selection)
    report = validate_walk_forward(**case)
    r1 = _result_for(report, "f1")
    assert WalkForwardFindingCode.PARAMETER_SELECTION_OUTSIDE_ALLOWED_WINDOW in _codes(r1)


def test_selection_completed_at_equals_oos_start_rejected() -> None:
    case = _base_train_only_case()
    selection = list(case["fold_parameter_selection_evidence"])
    selection[0] = FoldParameterSelectionEvidence(
        fold_id="f1", selected_parameter_hash="H",
        latest_selection_information_at=_dt("2020-03-25"), selection_completed_at=_dt("2020-04-01"),
    )
    case["fold_parameter_selection_evidence"] = tuple(selection)
    report = validate_walk_forward(**case)
    r1 = _result_for(report, "f1")
    assert WalkForwardFindingCode.OOS_PARAMETER_PEEK in _codes(r1)


def test_selection_information_after_completion_rejected() -> None:
    case = _base_train_only_case()
    selection = list(case["fold_parameter_selection_evidence"])
    selection[0] = FoldParameterSelectionEvidence(
        fold_id="f1", selected_parameter_hash="H",
        latest_selection_information_at=_dt("2020-03-28"), selection_completed_at=_dt("2020-03-25"),
    )
    case["fold_parameter_selection_evidence"] = tuple(selection)
    report = validate_walk_forward(**case)
    r1 = _result_for(report, "f1")
    assert WalkForwardFindingCode.PARAMETER_SELECTION_OUTSIDE_ALLOWED_WINDOW in _codes(r1)


def test_train_only_validation_peek_rejected() -> None:
    """TRAIN_ONLY still checks against train_interval.end even when the fold
    also carries a validation_interval: a selection timestamp falling inside
    that validation window is strictly after train.end and must be rejected.
    This behavior is already correct; this test locks it as permanent.
    """

    case = _base_train_only_case()
    folds = list(case["folds"])
    folds[0] = WalkForwardFold(
        "f1", TemporalInterval(_dt("2020-01-01"), _dt("2020-04-01")),
        TemporalInterval(_dt("2020-04-01"), _dt("2020-04-20")),
        TemporalInterval(_dt("2020-04-20"), _dt("2020-05-01")),
    )
    case["folds"] = tuple(folds)
    components = _components_for(
        case["information_dependency"], case["universe_requirement"], case["mode"], case["folds"],
        case["parameter_selection_mode"],
    )
    case["manifest"] = _manifest_with_components(case["manifest"].experiment_id, components)
    selection = list(case["fold_parameter_selection_evidence"])
    selection[0] = FoldParameterSelectionEvidence(
        fold_id="f1", selected_parameter_hash="H",
        latest_selection_information_at=_dt("2020-04-10"), selection_completed_at=_dt("2020-04-15"),
    )
    case["fold_parameter_selection_evidence"] = tuple(selection)
    separation = list(case["separation_evidence"])
    separation[0] = FoldSeparationEvidence(
        fold_id="f1", purge_bar_grid_id="1d", applied_train_to_validation_purge_bars=4,
        applied_pre_oos_purge_bars=4, applied_embargo_bars=0,
    )
    case["separation_evidence"] = tuple(separation)
    data = list(case["data_evidence"])
    data[0] = FoldDataEvidence(
        fold_id="f1", bar_grid_id="1d", usable_train_bars=100, usable_validation_bars=30, usable_oos_bars=20
    )
    case["data_evidence"] = tuple(data)
    report = validate_walk_forward(**case)
    r1 = _result_for(report, "f1")
    assert WalkForwardFindingCode.PARAMETER_SELECTION_OUTSIDE_ALLOWED_WINDOW in _codes(r1)
    assert r1.status is LEAKAGE_RISK


# ==========================================================================
# Purge / warmup / embargo / grid
# ==========================================================================


def test_label_grid_evaluation_grid_mismatch_case_is_independent() -> None:
    """Label grid and evaluation grid may legitimately differ; each of the
    two grid checks must compare against its own correct reference grid.
    """

    folds = (
        WalkForwardFold(
            "f1", TemporalInterval(_dt("2020-01-01"), _dt("2020-06-01")), None,
            TemporalInterval(_dt("2020-06-01"), _dt("2020-07-01")),
        ),
    )
    info_dep = evaluate_information_dependency(_valid_declaration(feature_grid="4h", label_grid="1d"))
    universe_req = UniverseIntegrityRequirement(False, False, False)
    components = _components_for(info_dep, universe_req, WalkForwardMode.EXPANDING, folds, ParameterSelectionMode.FIXED)
    manifest = _manifest_with_components("E1", components)
    lineage = _lineage_for(manifest)
    param_origin = ParameterOrigin(
        origin_type=ParameterOriginType.LITERATURE, source_ref="paper", parameter_hash="HASH1",
        declared_at=_dt("2019-01-01"), information_horizon_end=_dt("2019-01-01"),
    )
    separation = (
        FoldSeparationEvidence(
            fold_id="f1", purge_bar_grid_id="1d", applied_train_to_validation_purge_bars=None,
            applied_pre_oos_purge_bars=4, applied_embargo_bars=0,
        ),
    )
    data = (
        FoldDataEvidence(fold_id="f1", bar_grid_id="4h", usable_train_bars=100, usable_validation_bars=None, usable_oos_bars=20),
    )
    report = validate_walk_forward(
        manifest=manifest, mode=WalkForwardMode.EXPANDING, parameter_selection_mode=ParameterSelectionMode.FIXED,
        folds=folds, information_dependency=info_dep, lineage_audit=lineage,
        parameter_origin=param_origin, fixed_parameter_evidence=FixedParameterEvidence(selected_parameter_hash="HASH1"),
        fold_parameter_selection_evidence=(), separation_evidence=separation, data_evidence=data,
        universe_requirement=universe_req, universe_integrity_evidence=(),
    )
    r1 = _result_for(report, "f1")
    assert WalkForwardFindingCode.BAR_GRID_MISMATCH not in _codes(r1)
    assert r1.status is VALID


def test_purge_grid_mismatch() -> None:
    case = _base_fixed_case()
    sep = list(case["separation_evidence"])
    sep[0] = FoldSeparationEvidence(
        fold_id="f1", purge_bar_grid_id="WRONG_GRID", applied_train_to_validation_purge_bars=None,
        applied_pre_oos_purge_bars=4, applied_embargo_bars=0,
    )
    case["separation_evidence"] = tuple(sep)
    report = validate_walk_forward(**case)
    r1 = _result_for(report, "f1")
    assert WalkForwardFindingCode.BAR_GRID_MISMATCH in _codes(r1)
    assert r1.status is INVALID


def test_applied_purge_required_minus_one() -> None:
    case = _base_fixed_case()
    sep = list(case["separation_evidence"])
    sep[0] = FoldSeparationEvidence(
        fold_id="f1", purge_bar_grid_id="1d", applied_train_to_validation_purge_bars=None,
        applied_pre_oos_purge_bars=3, applied_embargo_bars=0,
    )
    case["separation_evidence"] = tuple(sep)
    report = validate_walk_forward(**case)
    r1 = _result_for(report, "f1")
    assert WalkForwardFindingCode.PURGE_INSUFFICIENT in _codes(r1)


def test_no_validation_purge_contradiction() -> None:
    """A fold with no validation_interval must not carry a
    applied_train_to_validation_purge_bars value -- there is no
    train-to-validation boundary for it to describe.
    """

    case = _base_fixed_case()
    sep = list(case["separation_evidence"])
    sep[0] = FoldSeparationEvidence(
        fold_id="f1", purge_bar_grid_id="1d", applied_train_to_validation_purge_bars=4,
        applied_pre_oos_purge_bars=4, applied_embargo_bars=0,
    )
    case["separation_evidence"] = tuple(sep)
    report = validate_walk_forward(**case)
    r1 = _result_for(report, "f1")
    assert WalkForwardFindingCode.INVALID_FOLD_GEOMETRY in _codes(r1)
    assert r1.status is INVALID


def test_data_evidence_contradicts_geometry() -> None:
    """A fold with no validation_interval must not carry a
    usable_validation_bars value.
    """

    case = _base_fixed_case()
    data = list(case["data_evidence"])
    data[0] = FoldDataEvidence(
        fold_id="f1", bar_grid_id="1d", usable_train_bars=100, usable_validation_bars=30, usable_oos_bars=20
    )
    case["data_evidence"] = tuple(data)
    report = validate_walk_forward(**case)
    r1 = _result_for(report, "f1")
    assert WalkForwardFindingCode.INVALID_FOLD_GEOMETRY in _codes(r1)
    assert r1.status is INVALID


def test_purge_required_none() -> None:
    case = _base_fixed_case()
    info_dep = evaluate_information_dependency(_undeclared_label_declaration())
    case["information_dependency"] = info_dep
    components = _components_for(
        info_dep, case["universe_requirement"], case["mode"], case["folds"], case["parameter_selection_mode"]
    )
    case["manifest"] = _manifest_with_components("E1", components)
    report = validate_walk_forward(**case)
    for r in report.fold_results:
        assert WalkForwardFindingCode.PURGE_REQUIREMENT_UNRESOLVED in _codes(r)


def test_embargo_evidence_none_even_required_zero() -> None:
    case = _base_fixed_case()
    sep = list(case["separation_evidence"])
    sep[0] = FoldSeparationEvidence(
        fold_id="f1", purge_bar_grid_id="1d", applied_train_to_validation_purge_bars=None,
        applied_pre_oos_purge_bars=4, applied_embargo_bars=None,
    )
    case["separation_evidence"] = tuple(sep)
    report = validate_walk_forward(**case)
    r1 = _result_for(report, "f1")
    assert WalkForwardFindingCode.EMBARGO_APPLICATION_UNRESOLVED in _codes(r1)


def test_warmup_required_none() -> None:
    case = _base_fixed_case()
    info_dep = evaluate_information_dependency(_undeclared_feature_declaration())
    case["information_dependency"] = info_dep
    components = _components_for(
        info_dep, case["universe_requirement"], case["mode"], case["folds"], case["parameter_selection_mode"]
    )
    case["manifest"] = _manifest_with_components("E1", components)
    report = validate_walk_forward(**case)
    for r in report.fold_results:
        assert WalkForwardFindingCode.WARMUP_REQUIREMENT_UNRESOLVED in _codes(r)


def test_warmup_wrong_grid() -> None:
    case = _base_fixed_case()
    data = list(case["data_evidence"])
    data[0] = FoldDataEvidence(
        fold_id="f1", bar_grid_id="WRONG_GRID", usable_train_bars=100, usable_validation_bars=None, usable_oos_bars=20
    )
    case["data_evidence"] = tuple(data)
    report = validate_walk_forward(**case)
    r1 = _result_for(report, "f1")
    assert WalkForwardFindingCode.BAR_GRID_MISMATCH in _codes(r1)


def test_train_warmup_insufficient() -> None:
    case = _base_fixed_case()
    data = list(case["data_evidence"])
    data[0] = FoldDataEvidence(
        fold_id="f1", bar_grid_id="1d", usable_train_bars=3, usable_validation_bars=None, usable_oos_bars=20
    )
    case["data_evidence"] = tuple(data)
    report = validate_walk_forward(**case)
    r1 = _result_for(report, "f1")
    assert WalkForwardFindingCode.TRAIN_WARMUP_INSUFFICIENT in _codes(r1)
    assert r1.status is INSUFFICIENT_DATA


def test_usable_bars_none_vs_zero_distinction() -> None:
    case = _base_fixed_case()
    data = list(case["data_evidence"])
    data[0] = FoldDataEvidence(
        fold_id="f1", bar_grid_id="1d", usable_train_bars=100, usable_validation_bars=None, usable_oos_bars=None
    )
    data[1] = FoldDataEvidence(
        fold_id="f2", bar_grid_id="1d", usable_train_bars=100, usable_validation_bars=None, usable_oos_bars=0
    )
    case["data_evidence"] = tuple(data)
    report = validate_walk_forward(**case)
    r1 = _result_for(report, "f1")
    r2 = _result_for(report, "f2")
    assert WalkForwardFindingCode.FOLD_EVIDENCE_MISSING in _codes(r1)
    assert WalkForwardFindingCode.OOS_DATA_EMPTY not in _codes(r1)
    assert WalkForwardFindingCode.OOS_DATA_EMPTY in _codes(r2)
    assert WalkForwardFindingCode.FOLD_EVIDENCE_MISSING not in _codes(r2)


# ==========================================================================
# Universe integrity
# ==========================================================================


def test_universe_conflict() -> None:
    case = _with_universe(
        _base_fixed_case(),
        UniverseIntegrityRequirement(True, False, False),
        (FoldUniverseIntegrityEvidence("f1", (_conflict_membership_resolution(),), (), ()),
         FoldUniverseIntegrityEvidence("f2", (_conflict_membership_resolution(),), (), ())),
    )
    report = validate_walk_forward(**case)
    for r in report.fold_results:
        assert WalkForwardFindingCode.UNIVERSE_INTEGRITY_CONFLICT in _codes(r)
        assert r.status is INVALID


def test_universe_indeterminate() -> None:
    case = _with_universe(
        _base_fixed_case(),
        UniverseIntegrityRequirement(True, False, False),
        (FoldUniverseIntegrityEvidence("f1", (_indeterminate_membership_resolution(),), (), ()),
         FoldUniverseIntegrityEvidence("f2", (_indeterminate_membership_resolution(),), (), ())),
    )
    report = validate_walk_forward(**case)
    for r in report.fold_results:
        assert WalkForwardFindingCode.UNIVERSE_INTEGRITY_INDETERMINATE in _codes(r)
        assert r.status is LEAKAGE_RISK


def test_required_universe_domain_empty() -> None:
    case = _with_universe(_base_fixed_case(), UniverseIntegrityRequirement(True, False, False), ())
    report = validate_walk_forward(**case)
    for r in report.fold_results:
        assert WalkForwardFindingCode.UNIVERSE_INTEGRITY_EVIDENCE_MISSING in _codes(r)
        assert r.status is LEAKAGE_RISK


def test_optional_universe_domain_empty() -> None:
    case = _with_universe(_base_fixed_case(), UniverseIntegrityRequirement(False, False, False), ())
    report = validate_walk_forward(**case)
    for r in report.fold_results:
        assert WalkForwardFindingCode.UNIVERSE_INTEGRITY_EVIDENCE_MISSING not in _codes(r)
        assert r.status is VALID


def test_optional_universe_domain_with_conflict_still_invalid() -> None:
    case = _with_universe(
        _base_fixed_case(),
        UniverseIntegrityRequirement(False, False, False),
        (FoldUniverseIntegrityEvidence("f1", (_conflict_membership_resolution(),), (), ()),
         FoldUniverseIntegrityEvidence("f2", (), (), ())),
    )
    report = validate_walk_forward(**case)
    r1 = _result_for(report, "f1")
    r2 = _result_for(report, "f2")
    assert WalkForwardFindingCode.UNIVERSE_INTEGRITY_CONFLICT in _codes(r1)
    assert r1.status is INVALID
    assert r2.status is VALID


# ==========================================================================
# Lineage
# ==========================================================================


def test_lineage_violation() -> None:
    case = _base_fixed_case()
    components = _components_for(
        case["information_dependency"], case["universe_requirement"], case["mode"], case["folds"],
        case["parameter_selection_mode"],
    )
    manifest = _manifest_with_components("E1", components, parent="E1", root="E1")
    case["manifest"] = manifest
    case["lineage_audit"] = _lineage_for(manifest)
    report = validate_walk_forward(**case)
    for r in report.fold_results:
        assert WalkForwardFindingCode.LINEAGE_VIOLATION in _codes(r)
        assert r.status is INVALID


def test_lineage_indeterminate() -> None:
    case = _base_fixed_case()
    components = _components_for(
        case["information_dependency"], case["universe_requirement"], case["mode"], case["folds"],
        case["parameter_selection_mode"],
    )
    manifest = _manifest_with_components("E1", components, parent="GHOST_PARENT", root="GHOST_PARENT")
    case["manifest"] = manifest
    case["lineage_audit"] = _lineage_for(manifest, prior=(), history_complete=False)
    report = validate_walk_forward(**case)
    for r in report.fold_results:
        assert WalkForwardFindingCode.LINEAGE_INDETERMINATE in _codes(r)
        assert r.status is LEAKAGE_RISK


# ==========================================================================
# Evidence coverage
# ==========================================================================


def test_unknown_evidence_fold_id() -> None:
    case = _base_fixed_case()
    data = list(case["data_evidence"])
    data.append(FoldDataEvidence(fold_id="GHOST", bar_grid_id="1d", usable_train_bars=1, usable_validation_bars=None, usable_oos_bars=1))
    case["data_evidence"] = tuple(data)
    report = validate_walk_forward(**case)
    assert any(
        f.code is WalkForwardFindingCode.EVIDENCE_FOLD_ID_UNKNOWN and f.fold_id is None
        for f in report.report_findings
    )
    assert report.total_fold_count == 2


def test_unknown_evidence_fold_id_deduplicated_per_distinct_id() -> None:
    """Multiple evidence entries sharing the same unknown fold_id must yield
    exactly one EVIDENCE_FOLD_ID_UNKNOWN finding, not one per entry.
    """

    case = _base_fixed_case()
    data = list(case["data_evidence"])
    data.append(FoldDataEvidence(fold_id="GHOST", bar_grid_id="1d", usable_train_bars=1, usable_validation_bars=None, usable_oos_bars=1))
    data.append(FoldDataEvidence(fold_id="GHOST", bar_grid_id="1d", usable_train_bars=2, usable_validation_bars=None, usable_oos_bars=2))
    data.append(FoldDataEvidence(fold_id="GHOST", bar_grid_id="1d", usable_train_bars=3, usable_validation_bars=None, usable_oos_bars=3))
    case["data_evidence"] = tuple(data)
    report = validate_walk_forward(**case)
    unknown = [f for f in report.report_findings if f.code is WalkForwardFindingCode.EVIDENCE_FOLD_ID_UNKNOWN]
    assert len(unknown) == 1
    assert report.total_fold_count == 2


def test_duplicate_evidence_fold_id() -> None:
    case = _base_fixed_case()
    data = list(case["data_evidence"])
    data.append(FoldDataEvidence(fold_id="f1", bar_grid_id="1d", usable_train_bars=100, usable_validation_bars=None, usable_oos_bars=20))
    case["data_evidence"] = tuple(data)
    report = validate_walk_forward(**case)
    r1 = _result_for(report, "f1")
    assert WalkForwardFindingCode.DUPLICATE_EVIDENCE_FOLD_ID in _codes(r1)
    assert r1.status is INVALID


def test_missing_evidence_fold_id() -> None:
    case = _base_fixed_case()
    case["separation_evidence"] = tuple(e for e in case["separation_evidence"] if e.fold_id != "f1")
    report = validate_walk_forward(**case)
    r1 = _result_for(report, "f1")
    assert WalkForwardFindingCode.FOLD_EVIDENCE_MISSING in _codes(r1)


# ==========================================================================
# Structural invariants
# ==========================================================================


def _assert_reports_equivalent(report_a, report_b) -> None:
    assert report_a.fold_results == report_b.fold_results
    assert report_a.report_findings == report_b.report_findings
    assert report_a.performance_eligible_fold_ids == report_b.performance_eligible_fold_ids
    assert report_a.total_fold_count == report_b.total_fold_count
    assert report_a.valid_fold_count == report_b.valid_fold_count
    assert report_a.insufficient_data_fold_count == report_b.insufficient_data_fold_count
    assert report_a.leakage_risk_fold_count == report_b.leakage_risk_fold_count
    assert report_a.invalid_fold_count == report_b.invalid_fold_count


def test_input_fold_shuffle_order_invariance() -> None:
    case = _base_fixed_case()
    report_a = validate_walk_forward(**case)

    shuffled = dict(case)
    shuffled["folds"] = tuple(reversed(case["folds"]))
    report_b = validate_walk_forward(**shuffled)

    _assert_reports_equivalent(report_a, report_b)


def test_evidence_shuffle_order_invariance() -> None:
    case = _base_fixed_case()
    report_a = validate_walk_forward(**case)

    shuffled = dict(case)
    shuffled["separation_evidence"] = tuple(reversed(case["separation_evidence"]))
    shuffled["data_evidence"] = tuple(reversed(case["data_evidence"]))
    report_b = validate_walk_forward(**shuffled)

    _assert_reports_equivalent(report_a, report_b)


def test_every_input_fold_retained_in_denominator() -> None:
    report = validate_walk_forward(**_base_fixed_case())
    assert report.total_fold_count == 2
    assert {r.fold.fold_id for r in report.fold_results} == {"f1", "f2"}


def test_only_valid_returned_by_performance_eligible_fold_ids() -> None:
    case = _base_fixed_case()
    data = list(case["data_evidence"])
    data[0] = FoldDataEvidence(fold_id="f1", bar_grid_id="1d", usable_train_bars=3, usable_validation_bars=None, usable_oos_bars=20)
    case["data_evidence"] = tuple(data)
    report = validate_walk_forward(**case)
    assert report.performance_eligible_fold_ids == ("f2",)


def test_report_level_findings_do_not_create_ghost_fold_results() -> None:
    case = _base_fixed_case()
    data = list(case["data_evidence"])
    data.append(FoldDataEvidence(fold_id="GHOST", bar_grid_id="1d", usable_train_bars=1, usable_validation_bars=None, usable_oos_bars=1))
    case["data_evidence"] = tuple(data)
    report = validate_walk_forward(**case)
    assert report.total_fold_count == 2
    assert "GHOST" not in {r.fold.fold_id for r in report.fold_results}


# ==========================================================================
# Golden fingerprint fixtures (hard-coded, not merely self-consistent)
# ==========================================================================


def test_golden_fingerprint_universe_policy() -> None:
    requirement = UniverseIntegrityRequirement(True, False, True)
    assert requirement.fingerprint == "b5653be633d49ff7f2ca860ec414de0be9ccbdd49651f8e20889998b2d7bf67d"


def test_golden_fingerprint_window_configuration() -> None:
    folds = (
        WalkForwardFold(
            "GOLD-F1", TemporalInterval(_dt("2024-01-01"), _dt("2024-02-01")), None,
            TemporalInterval(_dt("2024-02-01"), _dt("2024-03-01")),
        ),
    )
    fp = compute_window_configuration_fingerprint(mode=WalkForwardMode.EXPANDING, folds=folds)
    assert fp == "6aeffc0037c410168b09820b1f8dc685b6a777702d2ff895da2daabb6f9d531b"


def test_golden_fingerprint_contamination_policy() -> None:
    fp = compute_contamination_policy_fingerprint(parameter_selection_mode=ParameterSelectionMode.TRAIN_ONLY)
    assert fp == "0c8482d3c5f221bd817ac671c330c020a5b34ab62585d8c182f070454fa5f561"


def test_golden_fingerprint_evaluation_protocol() -> None:
    fp = compute_evaluation_protocol_fingerprint()
    assert fp == "f7b2768d7c33ba8721b7346400baef7350774f7d92dd8f614c3cc4f0f7d5ddd4"


# ==========================================================================
# Structural boundaries / frozen contract shape
# ==========================================================================


def _module_tree():
    import ast

    from src.services.strategy_lab import walk_forward

    return ast.parse(Path(walk_forward.__file__).read_text(encoding="utf-8"))


def test_no_forbidden_imports() -> None:
    import ast

    forbidden_roots = {
        "screening",
        "stock_mapping",
        "stock_index_loader",
        "providers",
        "repositories",
        "trading_calendar",
        "pandas",
        "numpy",
        "data_provider",
        "storage",
        "sqlalchemy",
    }

    for node in ast.walk(_module_tree()):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert not (set(alias.name.split(".")) & forbidden_roots), alias.name
        elif isinstance(node, ast.ImportFrom):
            assert not (set((node.module or "").split(".")) & forbidden_roots), node.module


def test_frozen_public_contract_shape() -> None:
    frozen_fields = {
        WalkForwardFold: ("fold_id", "train_interval", "validation_interval", "oos_interval"),
        FixedParameterEvidence: ("selected_parameter_hash",),
        FoldParameterSelectionEvidence: (
            "fold_id", "selected_parameter_hash", "latest_selection_information_at", "selection_completed_at",
        ),
        FoldSeparationEvidence: (
            "fold_id", "purge_bar_grid_id", "applied_train_to_validation_purge_bars",
            "applied_pre_oos_purge_bars", "applied_embargo_bars",
        ),
        FoldDataEvidence: (
            "fold_id", "bar_grid_id", "usable_train_bars", "usable_validation_bars", "usable_oos_bars",
        ),
        UniverseIntegrityRequirement: ("require_membership", "require_lifecycle", "require_classification"),
        FoldUniverseIntegrityEvidence: (
            "fold_id", "membership_resolutions", "lifecycle_resolutions", "classification_resolutions",
        ),
        WalkForwardFinding: ("code", "fold_id", "message"),
        FoldValidationResult: ("fold", "status", "findings"),
        WalkForwardValidationReport: ("mode", "parameter_selection_mode", "fold_results", "report_findings"),
    }
    for cls, names in frozen_fields.items():
        assert dataclasses.is_dataclass(cls), cls.__name__
        actual = tuple(f.name for f in dataclasses.fields(cls))
        assert actual == names, f"{cls.__name__} field drift: {actual} != {names}"

    frozen_enum_members = {
        WalkForwardMode: {"EXPANDING", "ROLLING"},
        ParameterSelectionMode: {"FIXED", "TRAIN_ONLY", "TRAIN_VALIDATION"},
        FoldValidationStatus: {"VALID", "INSUFFICIENT_DATA", "LEAKAGE_RISK", "INVALID"},
    }
    for enum_type, members in frozen_enum_members.items():
        assert {m.name for m in enum_type} == members, enum_type.__name__

    assert {m.name for m in WalkForwardFindingCode} == {
        "DUPLICATE_FOLD_ID", "INVALID_FOLD_GEOMETRY", "INVALID_MODE_GEOMETRY", "OOS_OVERLAP",
        "VALIDATION_REQUIRED", "EXPERIMENT_IDENTITY_MISMATCH", "PARAMETER_ORIGIN_REQUIRED",
        "FIXED_EVIDENCE_REQUIRED", "FORBIDDEN_FOLD_SELECTION_EVIDENCE_UNDER_FIXED",
        "LINEAGE_VIOLATION", "LINEAGE_INDETERMINATE",
        "INFORMATION_DEPENDENCY_UNBOUND", "UNIVERSE_POLICY_UNBOUND", "WINDOW_CONFIGURATION_UNBOUND",
        "CONTAMINATION_POLICY_UNBOUND", "EVALUATION_PROTOCOL_UNBOUND", "UNIVERSE_INTEGRITY_CONFLICT",
        "UNIVERSE_INTEGRITY_INDETERMINATE", "UNIVERSE_INTEGRITY_EVIDENCE_MISSING",
        "PARAMETER_HASH_MISMATCH", "PARAMETER_ORIGIN_SELF_REFERENCE",
        "PARAMETER_ORIGIN_INFORMATION_HORIZON_VIOLATION", "PARAMETER_ORIGIN_DECLARED_AT_VIOLATION",
        "PARAMETER_SELECTION_OUTSIDE_ALLOWED_WINDOW", "OOS_PARAMETER_PEEK", "CROSS_FOLD_OOS_FEEDBACK",
        "EVIDENCE_FOLD_ID_UNKNOWN", "DUPLICATE_EVIDENCE_FOLD_ID", "FOLD_EVIDENCE_MISSING",
        "BAR_GRID_MISMATCH", "INFORMATION_DEPENDENCY_INCOMPLETE", "INFORMATION_DEPENDENCY_LIMITED",
        "PURGE_REQUIREMENT_UNRESOLVED", "PURGE_APPLICATION_UNRESOLVED", "PURGE_INSUFFICIENT",
        "EMBARGO_APPLICATION_UNRESOLVED", "EMBARGO_INSUFFICIENT", "WARMUP_REQUIREMENT_UNRESOLVED",
        "TRAIN_WARMUP_INSUFFICIENT", "VALIDATION_DATA_EMPTY", "OOS_DATA_EMPTY",
    }

    assert tuple(inspect.signature(validate_walk_forward).parameters) == (
        "manifest", "mode", "parameter_selection_mode", "folds", "information_dependency", "lineage_audit",
        "parameter_origin", "fixed_parameter_evidence", "fold_parameter_selection_evidence",
        "separation_evidence", "data_evidence", "universe_requirement", "universe_integrity_evidence",
    )
    assert tuple(inspect.signature(compute_window_configuration_fingerprint).parameters) == ("mode", "folds")
    assert tuple(inspect.signature(compute_contamination_policy_fingerprint).parameters) == (
        "parameter_selection_mode",
    )
    assert tuple(inspect.signature(compute_evaluation_protocol_fingerprint).parameters) == ()


PERMANENT_WALK_FORWARD_TEST_IDS = (
    "TEST_VALID_EXPANDING_FIXED",
    "TEST_VALID_ROLLING_TRAIN_ONLY",
    "TEST_VALID_TRAIN_VALIDATION",
    "TEST_DUPLICATE_FOLD_ID",
    "TEST_INVALID_FOLD_INTERNAL_GEOMETRY",
    "TEST_EXPANDING_NON_EXPANSION",
    "TEST_ROLLING_ORDER_VIOLATION",
    "TEST_OVERLAPPING_OOS",
    "TEST_TRAIN_VALIDATION_MISSING_VALIDATION",
    "TEST_MANIFEST_LINEAGE_EXPERIMENT_ID_MISMATCH",
    "TEST_EACH_MANDATORY_MANIFEST_KEY_MISSING",
    "TEST_EACH_MANDATORY_MANIFEST_KEY_FINGERPRINT_MISMATCH",
    "TEST_INFORMATION_DEPENDENCY_SWAP_BLOCKED",
    "TEST_UNIVERSE_POLICY_SWAP_BLOCKED",
    "TEST_FIXED_HORIZON_INSIDE_TRAIN_BLOCKED",
    "TEST_FIXED_DECLARED_AT_INSIDE_TRAIN_BLOCKED",
    "TEST_FIXED_PARAMETER_HASH_MISMATCH",
    "TEST_FIXED_SELF_ORIGIN_EXPERIMENT",
    "TEST_FIXED_MISSING_PARAMETER_ORIGIN_IS_AUDITABLE",
    "TEST_FIXED_MISSING_FIXED_PARAMETER_EVIDENCE_IS_AUDITABLE",
    "TEST_FIXED_FORBIDDEN_FOLD_SELECTION_EVIDENCE_IS_AUDITABLE",
    "TEST_FIXED_ZERO_FOLD_HASH_MISMATCH_AND_SELF_REFERENCE_STILL_AUDITABLE",
    "TEST_STATE_ONLY_WARMUP_WRONG_GRID",
    "TEST_STATE_ONLY_WARMUP_CORRECT_GRID_ALLOWED",
    "TEST_TRAIN_ONLY_SELECTION_EXACTLY_TRAIN_END_REJECTED",
    "TEST_TRAIN_VALIDATION_SELECTION_EXACTLY_VALIDATION_END_REJECTED",
    "TEST_SELECTION_COMPLETED_AT_EQUALS_OOS_START_REJECTED",
    "TEST_SELECTION_INFORMATION_AFTER_COMPLETION_REJECTED",
    "TEST_TRAIN_ONLY_VALIDATION_PEEK_REJECTED",
    "TEST_LABEL_GRID_EVALUATION_GRID_MISMATCH_CASE_IS_INDEPENDENT",
    "TEST_PURGE_GRID_MISMATCH",
    "TEST_APPLIED_PURGE_REQUIRED_MINUS_ONE",
    "TEST_NO_VALIDATION_PURGE_CONTRADICTION",
    "TEST_DATA_EVIDENCE_CONTRADICTS_GEOMETRY",
    "TEST_PURGE_REQUIRED_NONE",
    "TEST_EMBARGO_EVIDENCE_NONE_EVEN_REQUIRED_ZERO",
    "TEST_WARMUP_REQUIRED_NONE",
    "TEST_WARMUP_WRONG_GRID",
    "TEST_TRAIN_WARMUP_INSUFFICIENT",
    "TEST_USABLE_BARS_NONE_VS_ZERO_DISTINCTION",
    "TEST_UNIVERSE_CONFLICT",
    "TEST_UNIVERSE_INDETERMINATE",
    "TEST_REQUIRED_UNIVERSE_DOMAIN_EMPTY",
    "TEST_OPTIONAL_UNIVERSE_DOMAIN_EMPTY",
    "TEST_OPTIONAL_UNIVERSE_DOMAIN_WITH_CONFLICT_STILL_INVALID",
    "TEST_LINEAGE_VIOLATION",
    "TEST_LINEAGE_INDETERMINATE",
    "TEST_UNKNOWN_EVIDENCE_FOLD_ID",
    "TEST_UNKNOWN_EVIDENCE_FOLD_ID_DEDUPLICATED_PER_DISTINCT_ID",
    "TEST_DUPLICATE_EVIDENCE_FOLD_ID",
    "TEST_MISSING_EVIDENCE_FOLD_ID",
    "TEST_INPUT_FOLD_SHUFFLE_ORDER_INVARIANCE",
    "TEST_EVIDENCE_SHUFFLE_ORDER_INVARIANCE",
    "TEST_EVERY_INPUT_FOLD_RETAINED_IN_DENOMINATOR",
    "TEST_ONLY_VALID_RETURNED_BY_PERFORMANCE_ELIGIBLE_FOLD_IDS",
    "TEST_REPORT_LEVEL_FINDINGS_DO_NOT_CREATE_GHOST_FOLD_RESULTS",
    "TEST_GOLDEN_FINGERPRINT_UNIVERSE_POLICY",
    "TEST_GOLDEN_FINGERPRINT_WINDOW_CONFIGURATION",
    "TEST_GOLDEN_FINGERPRINT_CONTAMINATION_POLICY",
    "TEST_GOLDEN_FINGERPRINT_EVALUATION_PROTOCOL",
    "TEST_NO_FORBIDDEN_IMPORTS",
    "TEST_FROZEN_PUBLIC_CONTRACT_SHAPE",
)


def test_permanent_walk_forward_manifest_cannot_shrink() -> None:
    module_tests = set(globals())
    for test_id in PERMANENT_WALK_FORWARD_TEST_IDS:
        assert test_id.lower() in module_tests, f"missing permanent adversarial test: {test_id}"
    assert len(PERMANENT_WALK_FORWARD_TEST_IDS) == 62
