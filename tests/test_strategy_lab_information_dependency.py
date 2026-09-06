import dataclasses
import itertools
from datetime import timedelta
from pathlib import Path

import pytest

from src.services.strategy_lab.information_dependency import (
    AvailabilityLag,
    AvailabilityLagKind,
    CompletenessLevel,
    DeclarationStatus,
    DependencyDeclaration,
    EmbargoReason,
    FeatureAvailabilityRequirement,
    FeatureDependency,
    FeatureDependencyDeclaration,
    FeatureSetDependency,
    GridFeatureWarmup,
    InformationDependencyDeclaration,
    InformationDependencyReport,
    LabelDependency,
    OverlapDiagnostics,
    PurgeDerivation,
    ResolutionStatus,
    SampleInformationInterval,
    SampleOverlapDependency,
    StateCarryMode,
    StateDependency,
    UnresolvedCategory,
    UnresolvedCode,
    UnresolvedFinding,
    WarmupSource,
    evaluate_information_dependency,
)


PERMANENT_INFORMATION_DEPENDENCY_TEST_IDS = (
    "TEST_UNDECLARED_PAYLOAD_CANNOT_CONTAIN_PLACEHOLDER_VALUES",
    "TEST_NOT_APPLICABLE_REQUIRES_REASON",
    "TEST_NOT_APPLICABLE_MATRIX_IS_FROZEN",
    "TEST_PAYLOADS_DO_NOT_REPEAT_DECLARATION_STATUS",
    "TEST_NONE_IS_NOT_ZERO",
    "TEST_UNDECLARED_FEATURE_RETAINS_IDENTITY",
    "TEST_SINGLE_FEATURE_NOT_APPLICABLE_REJECTED",
    "TEST_DUPLICATE_FEATURE_IDS_REJECTED",
    "TEST_FEATURE_DECLARATION_ORDER_CANONICAL",
    "TEST_LABEL_NOT_APPLICABLE_REJECTED",
    "TEST_STATE_NOT_APPLICABLE_REJECTED",
    "TEST_STATELESS_HAS_NO_CONVERGENCE_VALUE",
    "TEST_NEGATIVE_LOOKBACK_REJECTED",
    "TEST_EMPTY_DECLARED_FEATURE_SET_REJECTED",
    "TEST_LOOKBACK_IS_ALWAYS_A_BAR_COUNT",
    "TEST_NESTED_UNDECLARED_FEATURE_POISONS_FEATURE_WARMUP",
    "TEST_FEATURE_LOOKBACK_DOES_NOT_CAUSE_PURGE",
    "TEST_LABEL_HORIZON_DRIVES_PURGE",
    "TEST_ZERO_HORIZON_AND_LAG_DERIVES_ZERO_PURGE",
    "TEST_CROSS_GRID_WARMUP_NOT_NUMERICALLY_COMPARED",
    "TEST_CROSS_GRID_RESOLUTION_DOES_NOT_IMPLY_LIMITED_EXPRESSION",
    "TEST_FEATURE_GRID_COMPARED_AGAINST_DECLARED_EVALUATION_GRID",
    "TEST_EVALUATION_GRID_IS_FINGERPRINT_BEARING",
    "TEST_PURGE_DERIVATION_IS_STRUCTURED",
    "TEST_PURGE_DERIVATION_SEALS_IMPOSSIBLE_STATES",
    "TEST_PURGE_DERIVATION_ZERO_HORIZON_IS_LEGAL",
    "TEST_REPORT_PURGE_DERIVATION_MUST_MATCH_DECLARED_LABEL",
    "TEST_FEATURE_REASON_ALLOWED_UNDER_BOTH_STATUSES",
    "TEST_BINDING_FEATURE_TIES_PRESERVED",
    "TEST_ONE_UNRESOLVED_WARMUP_SIDE_POISONS_TOTAL",
    "TEST_UNRESOLVED_WARMUP_CANNOT_INVENT_WARMUP_SOURCE",
    "TEST_WARMUP_SOURCE_IS_SCALAR",
    "TEST_WARMUP_SOURCE_MATRIX",
    "TEST_NO_AGGREGATE_WARMUP_UNRESOLVED_FINDING",
    "TEST_FEATURE_AVAILABILITY_REQUIREMENTS_SURVIVE_REPORTING",
    "TEST_UNDECLARED_FEATURE_HAS_NO_AVAILABILITY_REQUIREMENT",
    "TEST_AVAILABILITY_LAG_DOES_NOT_POISON_WARMUP",
    "TEST_STATE_CARRY_MODE_SURVIVES_REPORTING",
    "TEST_UNSUPPORTED_AVAILABILITY_IS_EXPLICIT",
    "TEST_DURATION_LAG_REQUIRES_EXTERNAL_CALENDAR_RESOLUTION",
    "TEST_CALENDAR_RESOLUTION_ALWAYS_CREATES_UNRESOLVED_FINDING",
    "TEST_DURATION_RESOLUTION_DOES_NOT_IMPLY_LIMITED_EXPRESSION",
    "TEST_OVERLAP_NOT_APPLICABLE_HAS_NO_DIAGNOSTICS_OBJECT",
    "TEST_UNDECLARED_OVERLAP_IS_INCOMPLETE",
    "TEST_DECLARED_UNRESOLVED_OVERLAP_RETAINS_OBLIGATION",
    "TEST_RESOLVED_INTERVALS_EXPOSE_MAX_CONCURRENCY",
    "TEST_RESOLVED_INTERVALS_EXPOSE_MAX_NON_OVERLAPPING",
    "TEST_SAMPLING_STEP_BARS_IS_REQUIRED_AND_FINGERPRINT_BEARING",
    "TEST_SEQUENTIAL_TOPOLOGY_DERIVES_ZERO_EMBARGO",
    "TEST_NO_TOPOLOGY_FIELD_PARTICIPATES",
    "TEST_COMPLETENESS_PRECEDENCE_PRESERVES_EVERY_FINDING",
    "TEST_UNRESOLVED_CATEGORY_OWNS_COMPLETENESS",
    "TEST_FEATURE_ORDER_DOES_NOT_CHANGE_DECLARATION_FINGERPRINT",
    "TEST_CONTRACT_VERSION_CHANGES_CONTRACT_FINGERPRINT",
    "TEST_CONTRACT_VERSION_DOES_NOT_CHANGE_DECLARATION_FINGERPRINT",
    "TEST_CALLER_CANNOT_FORGE_REPORT_FINGERPRINTS",
    "TEST_REPORT_ORDER_INVARIANCE",
    "TEST_FROZEN_PUBLIC_CONTRACT_SHAPE",
)

GRID = "grid-alpha"
OTHER_GRID = "grid-beta"


# ---- builders ----


def _lag_bars(n: int = 0) -> AvailabilityLag:
    return AvailabilityLag(kind=AvailabilityLagKind.BAR_COUNT, bars=n)


def _lag_duration(**kwargs) -> AvailabilityLag:
    return AvailabilityLag(kind=AvailabilityLagKind.DURATION, duration=timedelta(**kwargs))


def _lag_unsupported(note: str = "vendor-defined") -> AvailabilityLag:
    return AvailabilityLag(kind=AvailabilityLagKind.UNSUPPORTED, note=note)


def _feature(
    feature_id: str,
    lookback_bars: int = 10,
    *,
    grid: str = GRID,
    lag: AvailabilityLag | None = None,
) -> FeatureDependencyDeclaration:
    return FeatureDependencyDeclaration(
        feature_id=feature_id,
        status=DeclarationStatus.DECLARED,
        payload=FeatureDependency(
            bar_grid_id=grid,
            lookback_bars=lookback_bars,
            availability_lag=lag or _lag_bars(0),
        ),
    )


def _undeclared_feature(feature_id: str, reason: str | None = None) -> FeatureDependencyDeclaration:
    return FeatureDependencyDeclaration(
        feature_id=feature_id, status=DeclarationStatus.UNDECLARED, reason=reason
    )


def _features(
    *items: FeatureDependencyDeclaration, evaluation_grid: str = GRID
) -> DependencyDeclaration:
    return DependencyDeclaration(
        status=DeclarationStatus.DECLARED,
        payload=FeatureSetDependency(
            evaluation_bar_grid_id=evaluation_grid, features=items
        ),
    )


def _no_features(reason: str = "price-only rule") -> DependencyDeclaration:
    return DependencyDeclaration(status=DeclarationStatus.NOT_APPLICABLE, reason=reason)


_UNDECLARED = DependencyDeclaration(status=DeclarationStatus.UNDECLARED)


def _label(horizon: int = 5, lag: AvailabilityLag | None = None, *, grid: str = GRID) -> DependencyDeclaration:
    return DependencyDeclaration(
        status=DeclarationStatus.DECLARED,
        payload=LabelDependency(
            bar_grid_id=grid,
            information_horizon_bars=horizon,
            availability_lag=lag or _lag_bars(1),
        ),
    )


def _state(mode: StateCarryMode, bars: int | None = None, *, grid: str | None = None) -> DependencyDeclaration:
    return DependencyDeclaration(
        status=DeclarationStatus.DECLARED,
        payload=StateDependency(
            carry_mode=mode, convergence_warmup_bars=bars, bar_grid_id=grid
        ),
    )


def _stateless() -> DependencyDeclaration:
    return _state(StateCarryMode.STATELESS)


def _cold_start(bars: int, *, grid: str = GRID) -> DependencyDeclaration:
    return _state(StateCarryMode.COLD_START, bars, grid=grid)


def _no_overlap(reason: str = "one sample per decision") -> DependencyDeclaration:
    return DependencyDeclaration(status=DeclarationStatus.NOT_APPLICABLE, reason=reason)


def _overlap(step: int = 1, intervals=None) -> DependencyDeclaration:
    return DependencyDeclaration(
        status=DeclarationStatus.DECLARED,
        payload=SampleOverlapDependency(
            sampling_step_bars=step, resolved_intervals=intervals
        ),
    )


def _declaration(
    *,
    contract_version: str = "information-dependency-v1",
    feature_set: DependencyDeclaration | None = None,
    label: DependencyDeclaration | None = None,
    state: DependencyDeclaration | None = None,
    overlap: DependencyDeclaration | None = None,
) -> InformationDependencyDeclaration:
    return InformationDependencyDeclaration(
        contract_version=contract_version,
        feature_set=feature_set if feature_set is not None else _features(_feature("f1")),
        label=label if label is not None else _label(),
        state=state if state is not None else _stateless(),
        overlap=overlap if overlap is not None else _no_overlap(),
    )


def _codes(report) -> set[UnresolvedCode]:
    return {finding.code for finding in report.unresolved}


# ---- Declaration wrapper hygiene ----


def test_undeclared_payload_cannot_contain_placeholder_values() -> None:
    with pytest.raises(ValueError):
        DependencyDeclaration(
            status=DeclarationStatus.UNDECLARED,
            payload=FeatureSetDependency(evaluation_bar_grid_id=GRID, features=(_feature("f1"),)),
        )
    with pytest.raises(ValueError):
        DependencyDeclaration(status=DeclarationStatus.UNDECLARED, reason="because")
    with pytest.raises(ValueError):
        FeatureDependencyDeclaration(
            feature_id="f1",
            status=DeclarationStatus.UNDECLARED,
            payload=FeatureDependency(GRID, 3, _lag_bars(0)),
        )


def test_not_applicable_requires_reason() -> None:
    with pytest.raises(ValueError):
        DependencyDeclaration(status=DeclarationStatus.NOT_APPLICABLE)
    with pytest.raises(ValueError):
        DependencyDeclaration(status=DeclarationStatus.NOT_APPLICABLE, reason="   ")
    with pytest.raises(ValueError):
        DependencyDeclaration(
            status=DeclarationStatus.NOT_APPLICABLE,
            reason="r",
            payload=SampleOverlapDependency(sampling_step_bars=1),
        )


def test_declared_wrapper_requires_payload_and_no_reason() -> None:
    with pytest.raises(ValueError):
        DependencyDeclaration(status=DeclarationStatus.DECLARED)
    with pytest.raises(ValueError):
        DependencyDeclaration(
            status=DeclarationStatus.DECLARED,
            payload=StateDependency(carry_mode=StateCarryMode.STATELESS),
            reason="why",
        )


def test_not_applicable_matrix_is_frozen() -> None:
    """Label and State may never be N/A; FeatureSet and Overlap may, with reason."""

    na = DependencyDeclaration(status=DeclarationStatus.NOT_APPLICABLE, reason="stated")

    assert _declaration(feature_set=na) is not None
    assert _declaration(overlap=na) is not None

    with pytest.raises(ValueError):
        _declaration(label=na)
    with pytest.raises(ValueError):
        _declaration(state=na)
    with pytest.raises(ValueError):
        FeatureDependencyDeclaration(feature_id="f1", status=DeclarationStatus.NOT_APPLICABLE)


def test_payloads_do_not_repeat_declaration_status() -> None:
    """Payload dataclasses describe the dependency, never its declaration state."""

    for payload_type in (
        FeatureSetDependency,
        LabelDependency,
        StateDependency,
        SampleOverlapDependency,
        FeatureDependency,
    ):
        names = {f.name for f in dataclasses.fields(payload_type)}
        assert "status" not in names, payload_type.__name__
        assert "reason" not in names, payload_type.__name__

    wrapper = {f.name for f in dataclasses.fields(DependencyDeclaration)}
    assert wrapper == {"status", "payload", "reason"}


def test_aggregate_rejects_wrong_payload_type() -> None:
    with pytest.raises(ValueError):
        _declaration(
            label=DependencyDeclaration(
                status=DeclarationStatus.DECLARED,
                payload=StateDependency(carry_mode=StateCarryMode.STATELESS),
            )
        )
    with pytest.raises(ValueError):
        _declaration(feature_set=FeatureSetDependency(evaluation_bar_grid_id=GRID, features=(_feature("f1"),)))


def test_single_feature_not_applicable_rejected() -> None:
    with pytest.raises(ValueError):
        FeatureDependencyDeclaration(feature_id="f1", status=DeclarationStatus.NOT_APPLICABLE)


def test_label_not_applicable_rejected() -> None:
    with pytest.raises(ValueError):
        _declaration(
            label=DependencyDeclaration(status=DeclarationStatus.NOT_APPLICABLE, reason="r")
        )


def test_state_not_applicable_rejected() -> None:
    with pytest.raises(ValueError):
        _declaration(
            state=DependencyDeclaration(status=DeclarationStatus.NOT_APPLICABLE, reason="r")
        )


def test_none_is_not_zero() -> None:
    undeclared = evaluate_information_dependency(_declaration(feature_set=_UNDECLARED))
    not_applicable = evaluate_information_dependency(_declaration(feature_set=_no_features()))

    assert undeclared.feature_warmup_bars is None
    assert not_applicable.feature_warmup_bars == 0
    assert undeclared.feature_warmup_bars != 0
    assert undeclared.completeness is CompletenessLevel.INCOMPLETE
    assert not_applicable.completeness is CompletenessLevel.COMPLETE


def test_undeclared_feature_retains_identity() -> None:
    report = evaluate_information_dependency(
        _declaration(
            feature_set=_features(_feature("f1", 10), _undeclared_feature("ghost", "tbd"))
        )
    )

    assert report.unresolved_feature_ids == ("ghost",)
    finding = next(f for f in report.unresolved if f.code is UnresolvedCode.FEATURE_UNDECLARED)
    assert finding.evidence["feature_id"] == "ghost"
    assert finding.evidence["reason"] == "tbd"


def test_duplicate_feature_ids_rejected() -> None:
    with pytest.raises(ValueError):
        FeatureSetDependency(evaluation_bar_grid_id=GRID, features=(_feature("f1", 5), _feature("f1", 9)))


def test_feature_declaration_order_canonical() -> None:
    forward = FeatureSetDependency(evaluation_bar_grid_id=GRID, features=(_feature("a", 1), _feature("b", 2), _feature("c", 3)))
    shuffled = FeatureSetDependency(evaluation_bar_grid_id=GRID, features=(_feature("c", 3), _feature("a", 1), _feature("b", 2)))

    assert tuple(f.feature_id for f in forward.features) == ("a", "b", "c")
    assert forward.features == shuffled.features


def test_stateless_has_no_convergence_value() -> None:
    with pytest.raises(ValueError):
        StateDependency(carry_mode=StateCarryMode.STATELESS, convergence_warmup_bars=5)
    with pytest.raises(ValueError):
        StateDependency(carry_mode=StateCarryMode.WARM_START, convergence_warmup_bars=0)


def test_negative_lookback_rejected() -> None:
    with pytest.raises(ValueError):
        FeatureDependency(bar_grid_id=GRID, lookback_bars=-1, availability_lag=_lag_bars(0))
    with pytest.raises(ValueError):
        LabelDependency(
            bar_grid_id=GRID, information_horizon_bars=-1, availability_lag=_lag_bars(0)
        )
    with pytest.raises(ValueError):
        AvailabilityLag(kind=AvailabilityLagKind.BAR_COUNT, bars=-1)


def test_empty_declared_feature_set_rejected() -> None:
    with pytest.raises(ValueError):
        FeatureSetDependency(evaluation_bar_grid_id=GRID, features=())


def test_lookback_is_always_a_bar_count() -> None:
    lookback = {f.name: f for f in dataclasses.fields(FeatureDependency)}["lookback_bars"]
    horizon = {f.name: f for f in dataclasses.fields(LabelDependency)}["information_horizon_bars"]
    assert str(lookback.type) == "int"
    assert str(horizon.type) == "int"

    with pytest.raises(ValueError):
        FeatureDependency(
            bar_grid_id=GRID, lookback_bars=timedelta(days=1), availability_lag=_lag_bars(0)
        )
    assert {k.value for k in AvailabilityLagKind} == {"bar_count", "duration", "unsupported"}


def test_bar_grid_id_is_opaque_and_never_normalized() -> None:
    report = evaluate_information_dependency(
        _declaration(
            feature_set=_features(
                _feature("daily", 3, grid="1d"), _feature("spelled", 4, grid="daily")
            ),
            label=_label(grid="1d"),
        )
    )

    assert tuple(e.bar_grid_id for e in report.per_grid_feature_warmup) == ("1d", "daily")
    assert report.required_warmup_bars is None


# ---- Warmup ----


def test_nested_undeclared_feature_poisons_feature_warmup() -> None:
    report = evaluate_information_dependency(
        _declaration(feature_set=_features(_feature("f1", 10), _undeclared_feature("f2")))
    )

    assert report.feature_warmup_bars is None
    assert report.required_warmup_bars is None
    assert report.warmup_source is WarmupSource.UNRESOLVED
    assert UnresolvedCode.FEATURE_UNDECLARED in _codes(report)
    assert report.completeness is CompletenessLevel.INCOMPLETE


def test_cross_grid_warmup_not_numerically_compared() -> None:
    report = evaluate_information_dependency(
        _declaration(
            feature_set=_features(
                _feature("slow", 200, grid=OTHER_GRID), _feature("fast", 5, grid=GRID)
            )
        )
    )

    assert report.feature_warmup_bars is None
    assert report.required_warmup_bars is None
    assert report.warmup_source is WarmupSource.UNRESOLVED
    finding = next(
        f for f in report.unresolved if f.code is UnresolvedCode.CROSS_GRID_WARMUP_NOT_COMPARABLE
    )
    assert finding.category is UnresolvedCategory.EXTERNAL_RESOLUTION_REQUIRED
    assert report.calendar_resolution_required is True
    per_grid = {e.bar_grid_id: e.warmup_bars for e in report.per_grid_feature_warmup}
    assert per_grid == {GRID: 5, OTHER_GRID: 200}


def test_cross_grid_resolution_does_not_imply_limited_expression() -> None:
    """Cross-grid is an external-resolution gap, not a schema capability gap."""

    report = evaluate_information_dependency(
        _declaration(
            feature_set=_features(_feature("off", 12, grid=OTHER_GRID), evaluation_grid=GRID)
        )
    )

    assert report.feature_warmup_bars is None
    assert report.required_warmup_bars is None
    assert report.warmup_source is WarmupSource.UNRESOLVED
    assert report.calendar_resolution_required is True
    assert {f.category for f in report.unresolved} == {
        UnresolvedCategory.EXTERNAL_RESOLUTION_REQUIRED
    }
    assert report.completeness is CompletenessLevel.COMPLETE
    assert report.completeness is not CompletenessLevel.LIMITED_EXPRESSION


def test_feature_grid_compared_against_declared_evaluation_grid() -> None:
    """A uniform feature set is still cross-grid if it is off the eval grid."""

    off_grid = evaluate_information_dependency(
        _declaration(
            feature_set=_features(_feature("only", 7, grid=OTHER_GRID), evaluation_grid=GRID)
        )
    )
    on_grid = evaluate_information_dependency(
        _declaration(feature_set=_features(_feature("only", 7, grid=GRID), evaluation_grid=GRID))
    )

    assert off_grid.required_warmup_bars is None
    assert off_grid.warmup_source is WarmupSource.UNRESOLVED
    finding = next(
        f
        for f in off_grid.unresolved
        if f.code is UnresolvedCode.CROSS_GRID_WARMUP_NOT_COMPARABLE
    )
    assert finding.evidence["evaluation_bar_grid_id"] == GRID
    assert finding.evidence["off_grid_features"] == (("only", OTHER_GRID),)

    assert on_grid.feature_warmup_bars == 7
    assert on_grid.required_warmup_bars == 7
    assert on_grid.warmup_source is WarmupSource.FEATURE
    assert on_grid.binding_feature_ids == ("only",)


def test_cold_start_state_off_evaluation_grid_is_unresolved() -> None:
    report = evaluate_information_dependency(
        _declaration(
            feature_set=_features(_feature("f1", 5), evaluation_grid=GRID),
            state=_cold_start(40, grid=OTHER_GRID),
        )
    )

    assert report.required_warmup_bars is None
    assert report.warmup_source is WarmupSource.UNRESOLVED
    assert report.calendar_resolution_required is True
    assert report.completeness is CompletenessLevel.COMPLETE


def test_evaluation_grid_is_fingerprint_bearing() -> None:
    left = _declaration(feature_set=_features(_feature("f1", 5, grid=GRID), evaluation_grid=GRID))
    right = _declaration(
        feature_set=_features(_feature("f1", 5, grid=GRID), evaluation_grid=OTHER_GRID)
    )

    assert left.declaration_fingerprint != right.declaration_fingerprint
    assert left.contract_fingerprint != right.contract_fingerprint

    with pytest.raises(ValueError):
        FeatureSetDependency(evaluation_bar_grid_id="", features=(_feature("f1"),))
    with pytest.raises(ValueError):
        FeatureSetDependency(evaluation_bar_grid_id="   ", features=(_feature("f1"),))


def test_purge_derivation_is_structured() -> None:
    import enum as _enum

    resolvable = evaluate_information_dependency(_declaration(label=_label(3, _lag_bars(2))))
    assert resolvable.required_purge_bars == 5
    assert resolvable.purge_derivation == PurgeDerivation(
        label_horizon_bars=3,
        label_lag_kind=AvailabilityLagKind.BAR_COUNT,
        label_lag_bars=2,
        resolvable_in_bars=True,
    )

    duration = evaluate_information_dependency(
        _declaration(label=_label(3, _lag_duration(hours=6)))
    )
    assert duration.required_purge_bars is None
    assert duration.purge_derivation == PurgeDerivation(
        label_horizon_bars=3,
        label_lag_kind=AvailabilityLagKind.DURATION,
        label_lag_bars=None,
        resolvable_in_bars=False,
    )

    undeclared = evaluate_information_dependency(_declaration(label=_UNDECLARED))
    assert undeclared.required_purge_bars is None
    assert undeclared.purge_derivation == PurgeDerivation(
        label_horizon_bars=None,
        label_lag_kind=None,
        label_lag_bars=None,
        resolvable_in_bars=False,
    )

    # A diagnostic record, never a verdict/driver enum.
    assert dataclasses.is_dataclass(PurgeDerivation)
    assert not isinstance(resolvable.purge_derivation, _enum.Enum)
    with pytest.raises(ValueError):
        PurgeDerivation(
            label_horizon_bars=None,
            label_lag_kind=None,
            label_lag_bars=None,
            resolvable_in_bars=True,
        )


def test_purge_derivation_seals_impossible_states() -> None:
    """Every combination in the frozen legal-state table is enforced at
    construction, both the states that must succeed and every adjacent
    inconsistent combination that must be rejected.
    """

    # ---- legal states must construct cleanly ----
    PurgeDerivation(
        label_horizon_bars=None,
        label_lag_kind=None,
        label_lag_bars=None,
        resolvable_in_bars=False,
    )
    PurgeDerivation(
        label_horizon_bars=3,
        label_lag_kind=AvailabilityLagKind.BAR_COUNT,
        label_lag_bars=2,
        resolvable_in_bars=True,
    )
    PurgeDerivation(
        label_horizon_bars=3,
        label_lag_kind=AvailabilityLagKind.DURATION,
        label_lag_bars=None,
        resolvable_in_bars=False,
    )
    PurgeDerivation(
        label_horizon_bars=3,
        label_lag_kind=AvailabilityLagKind.UNSUPPORTED,
        label_lag_bars=None,
        resolvable_in_bars=False,
    )

    # ---- BAR_COUNT + lag_bars=None ----
    with pytest.raises(ValueError):
        PurgeDerivation(
            label_horizon_bars=3,
            label_lag_kind=AvailabilityLagKind.BAR_COUNT,
            label_lag_bars=None,
            resolvable_in_bars=True,
        )

    # ---- BAR_COUNT + resolvable=False ----
    with pytest.raises(ValueError):
        PurgeDerivation(
            label_horizon_bars=3,
            label_lag_kind=AvailabilityLagKind.BAR_COUNT,
            label_lag_bars=2,
            resolvable_in_bars=False,
        )

    # ---- DURATION + lag_bars!=None ----
    with pytest.raises(ValueError):
        PurgeDerivation(
            label_horizon_bars=3,
            label_lag_kind=AvailabilityLagKind.DURATION,
            label_lag_bars=2,
            resolvable_in_bars=False,
        )

    # ---- DURATION + resolvable=True ----
    with pytest.raises(ValueError):
        PurgeDerivation(
            label_horizon_bars=3,
            label_lag_kind=AvailabilityLagKind.DURATION,
            label_lag_bars=None,
            resolvable_in_bars=True,
        )

    # ---- UNSUPPORTED + lag_bars!=None ----
    with pytest.raises(ValueError):
        PurgeDerivation(
            label_horizon_bars=3,
            label_lag_kind=AvailabilityLagKind.UNSUPPORTED,
            label_lag_bars=2,
            resolvable_in_bars=False,
        )

    # ---- UNSUPPORTED + resolvable=True ----
    with pytest.raises(ValueError):
        PurgeDerivation(
            label_horizon_bars=3,
            label_lag_kind=AvailabilityLagKind.UNSUPPORTED,
            label_lag_bars=None,
            resolvable_in_bars=True,
        )

    # ---- lag_kind=None + lag_bars!=None ----
    with pytest.raises(ValueError):
        PurgeDerivation(
            label_horizon_bars=None,
            label_lag_kind=None,
            label_lag_bars=2,
            resolvable_in_bars=False,
        )

    # ---- lag_kind=None + resolvable=True ----
    with pytest.raises(ValueError):
        PurgeDerivation(
            label_horizon_bars=None,
            label_lag_kind=None,
            label_lag_bars=None,
            resolvable_in_bars=True,
        )

    # ---- lag_kind=None + horizon!=None ----
    with pytest.raises(ValueError):
        PurgeDerivation(
            label_horizon_bars=3,
            label_lag_kind=None,
            label_lag_bars=None,
            resolvable_in_bars=False,
        )

    # ---- BAR_COUNT + horizon=None ----
    with pytest.raises(ValueError):
        PurgeDerivation(
            label_horizon_bars=None,
            label_lag_kind=AvailabilityLagKind.BAR_COUNT,
            label_lag_bars=2,
            resolvable_in_bars=True,
        )

    # ---- DURATION + horizon=None ----
    with pytest.raises(ValueError):
        PurgeDerivation(
            label_horizon_bars=None,
            label_lag_kind=AvailabilityLagKind.DURATION,
            label_lag_bars=None,
            resolvable_in_bars=False,
        )

    # ---- UNSUPPORTED + horizon=None ----
    with pytest.raises(ValueError):
        PurgeDerivation(
            label_horizon_bars=None,
            label_lag_kind=AvailabilityLagKind.UNSUPPORTED,
            label_lag_bars=None,
            resolvable_in_bars=False,
        )


def test_purge_derivation_zero_horizon_is_legal() -> None:
    """label_horizon_bars=0 is an explicitly legal, resolved value -- it is a
    stated fact, not a missing one.
    """

    zero_horizon = PurgeDerivation(
        label_horizon_bars=0,
        label_lag_kind=AvailabilityLagKind.BAR_COUNT,
        label_lag_bars=0,
        resolvable_in_bars=True,
    )
    assert zero_horizon.label_horizon_bars == 0
    assert zero_horizon.resolvable_in_bars is True

    report = evaluate_information_dependency(_declaration(label=_label(0, _lag_bars(0))))
    assert report.required_purge_bars == 0
    assert report.purge_derivation.label_horizon_bars == 0


def test_report_purge_derivation_must_match_declared_label() -> None:
    """A locally self-consistent PurgeDerivation is not enough: it must also
    be a faithful reflection of report.declaration.label.
    """

    declaration = _declaration(label=_label(3, _lag_bars(2)))
    report = evaluate_information_dependency(declaration)
    base_kwargs = dict(
        declaration=declaration,
        completeness=report.completeness,
        required_warmup_bars=report.required_warmup_bars,
        feature_warmup_bars=report.feature_warmup_bars,
        state_warmup_bars=report.state_warmup_bars,
        warmup_source=report.warmup_source,
        binding_feature_ids=report.binding_feature_ids,
        state_carry_mode=report.state_carry_mode,
        feature_availability_requirements=report.feature_availability_requirements,
        required_embargo_bars=report.required_embargo_bars,
        embargo_reason=report.embargo_reason,
        overlap=report.overlap,
        unresolved=report.unresolved,
        calendar_resolution_required=report.calendar_resolution_required,
    )

    # Sanity: the real report's own derivation passes.
    InformationDependencyReport(
        required_purge_bars=report.required_purge_bars,
        purge_derivation=report.purge_derivation,
        **base_kwargs,
    )

    # Wrong horizon.
    with pytest.raises(ValueError):
        InformationDependencyReport(
            required_purge_bars=7,
            purge_derivation=PurgeDerivation(
                label_horizon_bars=5,
                label_lag_kind=AvailabilityLagKind.BAR_COUNT,
                label_lag_bars=2,
                resolvable_in_bars=True,
            ),
            **base_kwargs,
        )

    # Wrong lag kind (label actually declares BAR_COUNT).
    with pytest.raises(ValueError):
        InformationDependencyReport(
            required_purge_bars=None,
            purge_derivation=PurgeDerivation(
                label_horizon_bars=3,
                label_lag_kind=AvailabilityLagKind.DURATION,
                label_lag_bars=None,
                resolvable_in_bars=False,
            ),
            **base_kwargs,
        )

    # Wrong lag bars under the correct BAR_COUNT kind.
    with pytest.raises(ValueError):
        InformationDependencyReport(
            required_purge_bars=99,
            purge_derivation=PurgeDerivation(
                label_horizon_bars=3,
                label_lag_kind=AvailabilityLagKind.BAR_COUNT,
                label_lag_bars=99,
                resolvable_in_bars=True,
            ),
            **base_kwargs,
        )

    # A locally-legal "undeclared" derivation attached to a DECLARED label.
    with pytest.raises(ValueError):
        InformationDependencyReport(
            required_purge_bars=None,
            purge_derivation=PurgeDerivation(
                label_horizon_bars=None,
                label_lag_kind=None,
                label_lag_bars=None,
                resolvable_in_bars=False,
            ),
            **base_kwargs,
        )

    # And the reverse: a resolved derivation attached to an UNDECLARED label.
    undeclared_declaration = _declaration(label=_UNDECLARED)
    undeclared_report = evaluate_information_dependency(undeclared_declaration)
    undeclared_kwargs = dict(base_kwargs)
    undeclared_kwargs["declaration"] = undeclared_declaration
    undeclared_kwargs["completeness"] = undeclared_report.completeness
    undeclared_kwargs["unresolved"] = undeclared_report.unresolved
    with pytest.raises(ValueError):
        InformationDependencyReport(
            required_purge_bars=5,
            purge_derivation=PurgeDerivation(
                label_horizon_bars=3,
                label_lag_kind=AvailabilityLagKind.BAR_COUNT,
                label_lag_bars=2,
                resolvable_in_bars=True,
            ),
            **undeclared_kwargs,
        )


def test_feature_reason_allowed_under_both_statuses() -> None:
    declared = FeatureDependencyDeclaration(
        feature_id="f1",
        status=DeclarationStatus.DECLARED,
        payload=FeatureDependency(GRID, 3, _lag_bars(0)),
        reason="documented upstream",
    )
    undeclared = FeatureDependencyDeclaration(
        feature_id="f2", status=DeclarationStatus.UNDECLARED, reason="pending vendor answer"
    )

    assert declared.reason == "documented upstream"
    assert undeclared.reason == "pending vendor answer"
    with pytest.raises(ValueError):
        FeatureDependencyDeclaration(
            feature_id="f3",
            status=DeclarationStatus.DECLARED,
            payload=FeatureDependency(GRID, 3, _lag_bars(0)),
            reason="   ",
        )

    with_reason = _declaration(feature_set=_features(declared))
    without = _declaration(
        feature_set=_features(
            FeatureDependencyDeclaration(
                feature_id="f1",
                status=DeclarationStatus.DECLARED,
                payload=FeatureDependency(GRID, 3, _lag_bars(0)),
            )
        )
    )
    assert with_reason.declaration_fingerprint != without.declaration_fingerprint


def test_binding_feature_ties_preserved() -> None:
    report = evaluate_information_dependency(
        _declaration(feature_set=_features(_feature("a", 30), _feature("b", 30), _feature("c", 10)))
    )

    assert report.required_warmup_bars == 30
    assert report.binding_feature_ids == ("a", "b")
    assert report.warmup_source is WarmupSource.FEATURE


def test_one_unresolved_warmup_side_poisons_total() -> None:
    report = evaluate_information_dependency(
        _declaration(feature_set=_features(_feature("f1", 10)), state=_UNDECLARED)
    )

    assert report.feature_warmup_bars == 10
    assert report.state_warmup_bars is None
    assert report.required_warmup_bars is None


def test_unresolved_warmup_cannot_invent_warmup_source() -> None:
    report = evaluate_information_dependency(
        _declaration(feature_set=_features(_feature("f1", 10)), state=_UNDECLARED)
    )

    assert report.required_warmup_bars is None
    assert report.warmup_source is WarmupSource.UNRESOLVED
    assert report.binding_feature_ids == ()


def test_warmup_source_is_scalar() -> None:
    report = evaluate_information_dependency(_declaration())

    assert isinstance(report.warmup_source, WarmupSource)
    assert not isinstance(report.warmup_source, (tuple, list, set, frozenset))
    assert {m.value for m in WarmupSource} == {
        "none",
        "feature",
        "state",
        "both",
        "unresolved",
    }


@pytest.mark.parametrize(
    "feature_set,state,expected_source,expected_total",
    [
        (None, None, WarmupSource.FEATURE, 10),
        (None, None, WarmupSource.FEATURE, 10),
    ],
    ids=["feature_gt_state", "feature_gt_state_repeat"],
)
def test_warmup_source_feature_dominates(
    feature_set, state, expected_source, expected_total
) -> None:
    report = evaluate_information_dependency(_declaration())
    assert report.warmup_source is expected_source
    assert report.required_warmup_bars == expected_total


def test_warmup_source_matrix() -> None:
    cases = [
        (_features(_feature("f1", 10)), _stateless(), WarmupSource.FEATURE, 10),
        (_features(_feature("f1", 5)), _cold_start(40), WarmupSource.STATE, 40),
        (_features(_feature("f1", 12)), _cold_start(12), WarmupSource.BOTH, 12),
        (_features(_feature("f1", 0)), _stateless(), WarmupSource.NONE, 0),
        (_no_features(), _stateless(), WarmupSource.NONE, 0),
        (_UNDECLARED, _stateless(), WarmupSource.UNRESOLVED, None),
        (_features(_feature("f1", 10)), _UNDECLARED, WarmupSource.UNRESOLVED, None),
    ]
    for feature_set, state, expected_source, expected_total in cases:
        report = evaluate_information_dependency(
            _declaration(feature_set=feature_set, state=state)
        )
        assert report.warmup_source is expected_source, (feature_set, state)
        assert report.required_warmup_bars == expected_total

    # Feature-level ties live in binding_feature_ids, not in warmup_source.
    tied = evaluate_information_dependency(
        _declaration(feature_set=_features(_feature("a", 7), _feature("b", 7)))
    )
    assert tied.warmup_source is WarmupSource.FEATURE
    assert tied.binding_feature_ids == ("a", "b")


def test_no_aggregate_warmup_unresolved_finding() -> None:
    """Unresolved warmup is structural; only specific causes are reported."""

    assert not hasattr(UnresolvedCode, "WARMUP_UNRESOLVED")

    undeclared_side = evaluate_information_dependency(
        _declaration(feature_set=_features(_feature("f1", 10)), state=_UNDECLARED)
    )
    cross_grid = evaluate_information_dependency(
        _declaration(
            feature_set=_features(_feature("a", 5, grid=GRID), _feature("b", 6, grid=OTHER_GRID))
        )
    )

    assert {f.category for f in undeclared_side.unresolved} == {UnresolvedCategory.UNDECLARED}
    assert undeclared_side.completeness is CompletenessLevel.INCOMPLETE
    assert {f.category for f in cross_grid.unresolved} == {
        UnresolvedCategory.EXTERNAL_RESOLUTION_REQUIRED
    }
    assert cross_grid.completeness is CompletenessLevel.COMPLETE
    for report in (undeclared_side, cross_grid):
        assert report.required_warmup_bars is None
        assert report.warmup_source is WarmupSource.UNRESOLVED


def test_availability_lag_does_not_poison_warmup() -> None:
    report = evaluate_information_dependency(
        _declaration(feature_set=_features(_feature("f1", 25, lag=_lag_duration(days=1))))
    )

    assert report.feature_warmup_bars == 25
    assert report.required_warmup_bars == 25
    assert report.warmup_source is WarmupSource.FEATURE
    assert UnresolvedCode.CALENDAR_RESOLUTION_REQUIRED in _codes(report)


def test_state_carry_mode_survives_reporting() -> None:
    for state, expected in (
        (_stateless(), StateCarryMode.STATELESS),
        (_cold_start(7), StateCarryMode.COLD_START),
        (_state(StateCarryMode.WARM_START), StateCarryMode.WARM_START),
        (_UNDECLARED, None),
    ):
        report = evaluate_information_dependency(_declaration(state=state))
        assert report.state_carry_mode is expected

    warm = evaluate_information_dependency(_declaration(state=_state(StateCarryMode.WARM_START)))
    assert warm.state_warmup_bars == 0


# ---- Purge ----


def test_label_horizon_drives_purge() -> None:
    report = evaluate_information_dependency(_declaration(label=_label(9, _lag_bars(2))))

    assert report.required_purge_bars == 11
    assert report.purge_derivation.resolvable_in_bars is True
    assert report.calendar_resolution_required is False


def test_feature_lookback_does_not_cause_purge() -> None:
    small = evaluate_information_dependency(
        _declaration(feature_set=_features(_feature("f1", 1)), label=_label(4, _lag_bars(0)))
    )
    huge = evaluate_information_dependency(
        _declaration(feature_set=_features(_feature("f1", 5000)), label=_label(4, _lag_bars(0)))
    )

    assert small.required_purge_bars == huge.required_purge_bars == 4


def test_zero_horizon_and_lag_derives_zero_purge() -> None:
    report = evaluate_information_dependency(_declaration(label=_label(0, _lag_bars(0))))

    assert report.required_purge_bars == 0
    assert report.required_purge_bars is not None
    assert report.purge_derivation.resolvable_in_bars is True


def test_undeclared_label_leaves_purge_unknown() -> None:
    report = evaluate_information_dependency(_declaration(label=_UNDECLARED))

    assert report.required_purge_bars is None
    assert report.purge_derivation.resolvable_in_bars is False
    assert UnresolvedCode.LABEL_UNDECLARED in _codes(report)
    assert report.completeness is CompletenessLevel.INCOMPLETE


# ---- Availability category ----


def test_duration_lag_requires_external_calendar_resolution() -> None:
    report = evaluate_information_dependency(_declaration(label=_label(3, _lag_duration(days=2))))

    assert report.calendar_resolution_required is True
    assert report.required_purge_bars is None
    finding = next(
        f for f in report.unresolved if f.code is UnresolvedCode.CALENDAR_RESOLUTION_REQUIRED
    )
    assert finding.category is UnresolvedCategory.EXTERNAL_RESOLUTION_REQUIRED


def test_calendar_resolution_always_creates_unresolved_finding() -> None:
    report = evaluate_information_dependency(
        _declaration(feature_set=_no_features(), label=_label(6, _lag_duration(hours=6)))
    )

    calendar = [f for f in report.unresolved if f.code is UnresolvedCode.CALENDAR_RESOLUTION_REQUIRED]
    assert len(calendar) == 1
    assert calendar[0].evidence["duration_microseconds"] == 6 * 3600 * 1_000_000


def test_duration_resolution_does_not_imply_limited_expression() -> None:
    report = evaluate_information_dependency(
        _declaration(feature_set=_no_features(), label=_label(2, _lag_duration(days=1)))
    )

    assert UnresolvedCode.CALENDAR_RESOLUTION_REQUIRED in _codes(report)
    assert report.completeness is CompletenessLevel.COMPLETE
    assert report.unresolved != ()


def test_unsupported_availability_is_explicit() -> None:
    report = evaluate_information_dependency(
        _declaration(feature_set=_no_features(), label=_label(3, _lag_unsupported("event-driven")))
    )

    assert report.completeness is CompletenessLevel.LIMITED_EXPRESSION
    unsupported = [f for f in report.unresolved if f.code is UnresolvedCode.UNSUPPORTED_AVAILABILITY]
    assert len(unsupported) == 1
    assert unsupported[0].category is UnresolvedCategory.LIMITED_EXPRESSION
    assert unsupported[0].evidence["note"] == "event-driven"
    assert report.required_purge_bars is None


def test_unresolved_category_owns_completeness() -> None:
    import src.services.strategy_lab.information_dependency as module

    assert not hasattr(module, "DiagnosticSeverity")
    assert {c.value for c in UnresolvedCategory} == {
        "undeclared",
        "limited_expression",
        "external_resolution_required",
    }

    external_only = evaluate_information_dependency(
        _declaration(feature_set=_no_features(), label=_label(1, _lag_duration(days=1)))
    )
    limited = evaluate_information_dependency(
        _declaration(feature_set=_no_features(), label=_label(1, _lag_unsupported()))
    )
    undeclared = evaluate_information_dependency(_declaration(label=_UNDECLARED))

    assert external_only.completeness is CompletenessLevel.COMPLETE
    assert limited.completeness is CompletenessLevel.LIMITED_EXPRESSION
    assert undeclared.completeness is CompletenessLevel.INCOMPLETE


def test_feature_availability_requirements_survive_reporting() -> None:
    duration_lag = _lag_duration(days=3)
    unsupported_lag = _lag_unsupported("vendor-defined")
    report = evaluate_information_dependency(
        _declaration(
            feature_set=_features(
                _feature("bars", 4, lag=_lag_bars(2)),
                _feature("dur", 5, lag=duration_lag),
                _feature("nope", 6, lag=unsupported_lag),
            )
        )
    )

    got = {r.feature_id: r for r in report.feature_availability_requirements}
    assert got["bars"].availability_lag == AvailabilityLag(
        kind=AvailabilityLagKind.BAR_COUNT, bars=2
    )
    assert got["dur"].availability_lag == duration_lag
    assert got["dur"].availability_lag.duration == timedelta(days=3)
    assert got["nope"].availability_lag == unsupported_lag
    assert got["nope"].availability_lag.note == "vendor-defined"
    assert got["bars"].bar_grid_id == GRID
    assert UnresolvedCode.CALENDAR_RESOLUTION_REQUIRED in _codes(report)
    assert UnresolvedCode.UNSUPPORTED_AVAILABILITY in _codes(report)


def test_undeclared_feature_has_no_availability_requirement() -> None:
    """Requirements are obligations; an unknown obligation is not one."""

    report = evaluate_information_dependency(
        _declaration(feature_set=_features(_feature("A", 3), _undeclared_feature("B")))
    )

    ids = {r.feature_id for r in report.feature_availability_requirements}
    assert ids == {"A"}
    assert "B" not in ids
    assert report.unresolved_feature_ids == ("B",)
    assert any(
        f.code is UnresolvedCode.FEATURE_UNDECLARED and f.evidence["feature_id"] == "B"
        for f in report.unresolved
    )
    for requirement in report.feature_availability_requirements:
        assert requirement.bar_grid_id is not None
        assert requirement.availability_lag is not None


# ---- Overlap ----


def test_overlap_not_applicable_has_no_diagnostics_object() -> None:
    report = evaluate_information_dependency(_declaration(overlap=_no_overlap()))

    assert report.overlap is None
    assert UnresolvedCode.OVERLAP_UNDECLARED not in _codes(report)


def test_undeclared_overlap_is_incomplete() -> None:
    report = evaluate_information_dependency(_declaration(overlap=_UNDECLARED))

    assert report.overlap is None
    assert UnresolvedCode.OVERLAP_UNDECLARED in _codes(report)
    assert report.completeness is CompletenessLevel.INCOMPLETE


def test_declared_unresolved_overlap_retains_obligation() -> None:
    report = evaluate_information_dependency(_declaration(overlap=_overlap(step=3)))

    assert report.overlap is not None
    assert report.overlap.resolution_status is ResolutionStatus.UNRESOLVED
    assert report.overlap.sampling_step_bars == 3
    assert report.overlap.max_concurrent_samples is None
    assert report.overlap.max_non_overlapping_samples is None
    assert report.overlap.sample_count is None


def test_resolved_intervals_expose_max_concurrency() -> None:
    intervals = (
        SampleInformationInterval(0, 10),
        SampleInformationInterval(5, 15),
        SampleInformationInterval(6, 8),
        SampleInformationInterval(20, 30),
    )
    report = evaluate_information_dependency(_declaration(overlap=_overlap(intervals=intervals)))

    assert report.overlap.resolution_status is ResolutionStatus.RESOLVED
    assert report.overlap.sample_count == 4
    assert report.overlap.max_concurrent_samples == 3


def test_half_open_intervals_do_not_count_as_overlapping() -> None:
    intervals = (
        SampleInformationInterval(0, 10),
        SampleInformationInterval(10, 20),
    )
    report = evaluate_information_dependency(_declaration(overlap=_overlap(intervals=intervals)))

    assert report.overlap.max_concurrent_samples == 1
    assert report.overlap.max_non_overlapping_samples == 2


def test_resolved_intervals_expose_max_non_overlapping() -> None:
    intervals = (
        SampleInformationInterval(0, 10),
        SampleInformationInterval(5, 15),
        SampleInformationInterval(12, 18),
        SampleInformationInterval(20, 30),
    )
    report = evaluate_information_dependency(_declaration(overlap=_overlap(intervals=intervals)))

    assert report.overlap.max_non_overlapping_samples == 3


def test_sampling_step_bars_is_required_and_fingerprint_bearing() -> None:
    with pytest.raises(TypeError):
        SampleOverlapDependency()  # type: ignore[call-arg]
    with pytest.raises(ValueError):
        SampleOverlapDependency(sampling_step_bars=0)
    with pytest.raises(ValueError):
        SampleOverlapDependency(sampling_step_bars=-1)

    assert (
        _declaration(overlap=_overlap(step=1)).declaration_fingerprint
        != _declaration(overlap=_overlap(step=2)).declaration_fingerprint
    )


def test_interval_requires_positive_width() -> None:
    with pytest.raises(ValueError):
        SampleInformationInterval(5, 5)
    with pytest.raises(ValueError):
        SampleInformationInterval(5, 4)


# ---- Embargo ----


def test_sequential_topology_derives_zero_embargo() -> None:
    report = evaluate_information_dependency(_declaration())

    assert report.required_embargo_bars == 0
    assert report.embargo_reason is EmbargoReason.NO_APPLICABLE_DEPENDENCY


def test_no_topology_field_participates() -> None:
    import src.services.strategy_lab.information_dependency as module

    assert not hasattr(module, "EvaluationTopology")
    assert "topology" not in {f.name for f in dataclasses.fields(InformationDependencyDeclaration)}

    payload = _declaration()._declaration_payload()
    assert set(payload) == {"feature_set", "label", "state", "overlap"}
    assert "topology" not in {f.name for f in dataclasses.fields(InformationDependencyReport)}


# ---- Completeness ----


def test_completeness_precedence_preserves_every_finding() -> None:
    report = evaluate_information_dependency(
        _declaration(
            feature_set=_features(
                _feature("dur", 3, lag=_lag_duration(days=1)),
                _feature("nope", 4, lag=_lag_unsupported("vendor")),
            ),
            label=_UNDECLARED,
            overlap=_overlap(step=2),
        )
    )

    assert {f.category for f in report.unresolved} == {
        UnresolvedCategory.UNDECLARED,
        UnresolvedCategory.LIMITED_EXPRESSION,
        UnresolvedCategory.EXTERNAL_RESOLUTION_REQUIRED,
    }
    assert report.completeness is CompletenessLevel.INCOMPLETE
    for code in (
        UnresolvedCode.CALENDAR_RESOLUTION_REQUIRED,
        UnresolvedCode.UNSUPPORTED_AVAILABILITY,
        UnresolvedCode.LABEL_UNDECLARED,
        UnresolvedCode.OVERLAP_UNRESOLVED,
    ):
        assert code in _codes(report)


def test_clean_declaration_is_complete() -> None:
    report = evaluate_information_dependency(_declaration())

    assert report.completeness is CompletenessLevel.COMPLETE
    assert report.unresolved == ()


# ---- Fingerprints ----


def test_feature_order_does_not_change_declaration_fingerprint() -> None:
    forward = _declaration(feature_set=_features(_feature("a", 1), _feature("b", 2), _feature("c", 3)))
    shuffled = _declaration(feature_set=_features(_feature("c", 3), _feature("a", 1), _feature("b", 2)))

    assert forward.declaration_fingerprint == shuffled.declaration_fingerprint
    assert forward.contract_fingerprint == shuffled.contract_fingerprint
    assert len(forward.declaration_fingerprint) == 64


def test_contract_version_changes_contract_fingerprint() -> None:
    first = _declaration(contract_version="information-dependency-v1")
    second = _declaration(contract_version="information-dependency-v2")

    assert first.contract_fingerprint != second.contract_fingerprint


def test_contract_version_does_not_change_declaration_fingerprint() -> None:
    first = _declaration(contract_version="information-dependency-v1")
    second = _declaration(contract_version="information-dependency-v2")

    assert first.declaration_fingerprint == second.declaration_fingerprint


@pytest.mark.parametrize(
    "left,right",
    [
        (_declaration(feature_set=_features(_feature("f1", 10))), _declaration(feature_set=_no_features())),
        (_declaration(feature_set=_no_features("r1")), _declaration(feature_set=_no_features("r2"))),
        (
            _declaration(feature_set=_features(_feature("f1", 10))),
            _declaration(feature_set=_features(_feature("renamed", 10))),
        ),
        (
            _declaration(feature_set=_features(_feature("f1", 10), evaluation_grid=GRID)),
            _declaration(feature_set=_features(_feature("f1", 10), evaluation_grid=OTHER_GRID)),
        ),
        (
            _declaration(feature_set=_features(_feature("f1", 10))),
            _declaration(feature_set=_features(_undeclared_feature("f1"))),
        ),
        (
            _declaration(feature_set=_features(_undeclared_feature("f1"))),
            _declaration(feature_set=_features(_undeclared_feature("f1", "pending"))),
        ),
        (
            _declaration(feature_set=_features(_feature("f1", 10))),
            _declaration(
                feature_set=_features(
                    FeatureDependencyDeclaration(
                        feature_id="f1",
                        status=DeclarationStatus.DECLARED,
                        payload=FeatureDependency(GRID, 10, _lag_bars(0)),
                        reason="documented",
                    )
                )
            ),
        ),
        (
            _declaration(feature_set=_features(_feature("f1", 10))),
            _declaration(feature_set=_features(_feature("f1", 10, grid=OTHER_GRID))),
        ),
        (
            _declaration(feature_set=_features(_feature("f1", 10))),
            _declaration(feature_set=_features(_feature("f1", 11))),
        ),
        (
            _declaration(feature_set=_features(_feature("f1", 10, lag=_lag_bars(1)))),
            _declaration(feature_set=_features(_feature("f1", 10, lag=_lag_duration(days=1)))),
        ),
        (
            _declaration(feature_set=_features(_feature("f1", 10, lag=_lag_duration(days=1)))),
            _declaration(feature_set=_features(_feature("f1", 10, lag=_lag_duration(days=2)))),
        ),
        (
            _declaration(feature_set=_features(_feature("f1", 10, lag=_lag_unsupported("n1")))),
            _declaration(feature_set=_features(_feature("f1", 10, lag=_lag_unsupported("n2")))),
        ),
        (_declaration(label=_label(5)), _declaration(label=_label(6))),
        (_declaration(state=_stateless()), _declaration(state=_state(StateCarryMode.WARM_START))),
        (_declaration(state=_cold_start(3)), _declaration(state=_cold_start(4))),
        (_declaration(overlap=_overlap(step=1)), _declaration(overlap=_overlap(step=2))),
        (
            _declaration(overlap=_overlap(intervals=(SampleInformationInterval(0, 5),))),
            _declaration(overlap=_overlap(intervals=(SampleInformationInterval(0, 6),))),
        ),
    ],
    ids=[
        "declaration_status",
        "not_applicable_reason",
        "feature_id",
        "evaluation_bar_grid_id",
        "feature_dependency_status",
        "feature_undeclared_reason",
        "feature_declared_reason",
        "bar_grid_id",
        "lookback_bars",
        "availability_lag_kind",
        "availability_lag_value",
        "availability_lag_note",
        "label_horizon",
        "state_carry_mode",
        "state_convergence",
        "overlap_sampling_step_bars",
        "resolved_intervals",
    ],
)
def test_declaration_fingerprint_is_sensitive_to_every_declared_item(left, right) -> None:
    assert left.declaration_fingerprint != right.declaration_fingerprint
    assert left.contract_fingerprint != right.contract_fingerprint


def test_duration_is_fingerprinted_as_exact_microseconds() -> None:
    one_day = _declaration(label=_label(1, _lag_duration(days=1)))
    same_day = _declaration(label=_label(1, _lag_duration(hours=24)))
    micro_apart = _declaration(label=_label(1, _lag_duration(days=1, microseconds=1)))

    assert one_day.declaration_fingerprint == same_day.declaration_fingerprint
    assert one_day.declaration_fingerprint != micro_apart.declaration_fingerprint


def test_none_and_zero_produce_different_fingerprints() -> None:
    assert (
        _declaration(feature_set=_UNDECLARED).declaration_fingerprint
        != _declaration(feature_set=_no_features()).declaration_fingerprint
    )


def test_caller_cannot_forge_report_fingerprints() -> None:
    report = evaluate_information_dependency(_declaration())
    expected = _declaration().declaration_fingerprint

    with pytest.raises(TypeError):
        InformationDependencyReport(  # type: ignore[call-arg]
            declaration_fingerprint="fake",
            contract_fingerprint="fake",
            completeness=CompletenessLevel.COMPLETE,
        )

    with pytest.raises(AttributeError):
        report.declaration_fingerprint = "fake"  # type: ignore[misc]
    with pytest.raises(AttributeError):
        report.contract_fingerprint = "fake"  # type: ignore[misc]

    assert type(report).__dict__["declaration_fingerprint"].fset is None
    assert type(report).__dict__["contract_fingerprint"].fset is None
    assert report.declaration_fingerprint == expected
    assert report.contract_version == "information-dependency-v1"


# ---- Report determinism and construction invariants ----


def test_report_order_invariance() -> None:
    features = (_feature("a", 30), _feature("b", 30), _feature("c", 10))
    reports = [
        evaluate_information_dependency(_declaration(feature_set=_features(*permutation)))
        for permutation in itertools.permutations(features)
    ]

    for report in reports:
        assert report == reports[0]
        assert report.unresolved == reports[0].unresolved


def test_unresolved_findings_are_canonically_sorted() -> None:
    report = evaluate_information_dependency(
        _declaration(feature_set=_UNDECLARED, label=_UNDECLARED, overlap=_UNDECLARED)
    )

    codes = [f.code.value for f in report.unresolved]
    assert codes == sorted(codes)


def test_report_rejects_inconsistent_construction() -> None:
    base = dict(
        declaration=_declaration(),
        required_purge_bars=None,
        purge_derivation=None,
        required_warmup_bars=None,
        feature_warmup_bars=None,
        state_warmup_bars=None,
        warmup_source=WarmupSource.UNRESOLVED,
        binding_feature_ids=(),
        state_carry_mode=None,
        feature_availability_requirements=(),
        required_embargo_bars=0,
        embargo_reason=EmbargoReason.NO_APPLICABLE_DEPENDENCY,
        overlap=None,
        calendar_resolution_required=False,
    )

    # completeness must match the category-derived level
    with pytest.raises(ValueError):
        InformationDependencyReport(
            **base,
            completeness=CompletenessLevel.COMPLETE,
            unresolved=(
                UnresolvedFinding(
                    code=UnresolvedCode.LABEL_UNDECLARED,
                    category=UnresolvedCategory.UNDECLARED,
                    message="m",
                ),
            ),
        )

    # unresolved warmup must report UNRESOLVED and name no binding features
    with pytest.raises(ValueError):
        InformationDependencyReport(
            **{**base, "warmup_source": WarmupSource.FEATURE},
            completeness=CompletenessLevel.COMPLETE,
            unresolved=(),
        )
    with pytest.raises(ValueError):
        InformationDependencyReport(
            **{**base, "binding_feature_ids": ("x",)},
            completeness=CompletenessLevel.COMPLETE,
            unresolved=(),
        )

    # a resolved warmup must not claim UNRESOLVED
    with pytest.raises(ValueError):
        InformationDependencyReport(
            **{**base, "required_warmup_bars": 3},
            completeness=CompletenessLevel.COMPLETE,
            unresolved=(),
        )


# ---- Frozen public contract shape ----


def test_frozen_public_contract_shape() -> None:
    """Mechanical drift guard, written against the authoritative frozen spec.

    Algorithms staying green is not enough: a rename, a reorder, or a silently
    added field on a frozen type must fail here. Supplementary diagnostic
    fields are asserted separately and are deliberately NOT treated as frozen
    contract merely because they currently exist.
    """

    frozen_fields = {
        DependencyDeclaration: ("status", "payload", "reason"),
        InformationDependencyDeclaration: (
            "contract_version",
            "feature_set",
            "label",
            "state",
            "overlap",
        ),
        FeatureDependencyDeclaration: ("feature_id", "status", "payload", "reason"),
        FeatureSetDependency: ("evaluation_bar_grid_id", "features"),
        LabelDependency: ("bar_grid_id", "information_horizon_bars", "availability_lag"),
        FeatureDependency: ("bar_grid_id", "lookback_bars", "availability_lag"),
        StateDependency: ("carry_mode", "convergence_warmup_bars", "bar_grid_id"),
        SampleOverlapDependency: ("sampling_step_bars", "resolved_intervals"),
        PurgeDerivation: (
            "label_horizon_bars",
            "label_lag_kind",
            "label_lag_bars",
            "resolvable_in_bars",
        ),
        AvailabilityLag: ("kind", "bars", "duration", "note"),
        SampleInformationInterval: ("start_bar_index", "end_bar_index"),
        FeatureAvailabilityRequirement: ("feature_id", "bar_grid_id", "availability_lag"),
        UnresolvedFinding: ("code", "category", "message", "evidence"),
        OverlapDiagnostics: (
            "resolution_status",
            "sampling_step_bars",
            "sample_count",
            "max_concurrent_samples",
            "max_non_overlapping_samples",
        ),
    }
    for cls, names in frozen_fields.items():
        assert dataclasses.is_dataclass(cls), cls.__name__
        actual = tuple(f.name for f in dataclasses.fields(cls))
        assert actual == names, f"{cls.__name__} field drift: {actual} != {names}"

    # PurgeDerivation is a structured diagnostic record, never an enum.
    import enum as _enum

    assert not (isinstance(PurgeDerivation, type) and issubclass(PurgeDerivation, _enum.Enum))


    frozen_enum_members = {
        WarmupSource: {"NONE", "FEATURE", "STATE", "BOTH", "UNRESOLVED"},
        DeclarationStatus: {"DECLARED", "UNDECLARED", "NOT_APPLICABLE"},
        AvailabilityLagKind: {"BAR_COUNT", "DURATION", "UNSUPPORTED"},
        StateCarryMode: {"STATELESS", "WARM_START", "COLD_START"},
        UnresolvedCategory: {"UNDECLARED", "LIMITED_EXPRESSION", "EXTERNAL_RESOLUTION_REQUIRED"},
        CompletenessLevel: {"COMPLETE", "LIMITED_EXPRESSION", "INCOMPLETE"},
        ResolutionStatus: {"RESOLVED", "UNRESOLVED"},
        EmbargoReason: {"NO_APPLICABLE_DEPENDENCY"},
    }
    for enum_type, members in frozen_enum_members.items():
        assert {m.name for m in enum_type} == members, enum_type.__name__

    # The frozen report fields must remain flat and directly reachable.
    report_field_names = {f.name for f in dataclasses.fields(InformationDependencyReport)}
    properties = {
        name
        for name, value in vars(InformationDependencyReport).items()
        if isinstance(value, property)
    }
    frozen_report_fields = {
        "required_purge_bars",
        "purge_derivation",
        "required_warmup_bars",
        "feature_warmup_bars",
        "state_warmup_bars",
        "warmup_source",
        "binding_feature_ids",
        "state_carry_mode",
        "feature_availability_requirements",
        "required_embargo_bars",
        "embargo_reason",
        "overlap",
        "completeness",
        "unresolved",
        "calendar_resolution_required",
        "contract_version",
        "declaration_fingerprint",
        "contract_fingerprint",
    }
    assert frozen_report_fields <= (report_field_names | properties)
    assert {"contract_version", "declaration_fingerprint", "contract_fingerprint"} <= properties

    # Supplementary diagnostics: present and useful, but explicitly NOT frozen
    # contract. `declaration` is the constructor route to the fingerprints.
    supplementary = report_field_names - frozen_report_fields
    assert supplementary == {
        "declaration",
        "per_grid_feature_warmup",
        "unresolved_feature_ids",
    }, f"unexpected non-frozen report field drift: {supplementary}"
    assert dataclasses.is_dataclass(GridFeatureWarmup)


# ---- Permanent adversarial manifest ----


def test_permanent_information_dependency_manifest_cannot_shrink() -> None:
    module_tests = set(globals())
    for test_id in PERMANENT_INFORMATION_DEPENDENCY_TEST_IDS:
        assert test_id.lower() in module_tests, f"missing permanent adversarial test: {test_id}"
    assert len(PERMANENT_INFORMATION_DEPENDENCY_TEST_IDS) == 58


# ---- Structural boundaries ----


def _module_tree():
    import ast

    from src.services.strategy_lab import information_dependency

    return ast.parse(Path(information_dependency.__file__).read_text(encoding="utf-8"))


def test_no_performance_report_dependency() -> None:
    import ast

    forbidden = {
        "performance_models",
        "PerformanceReport",
        "cagr",
        "sharpe",
        "max_drawdown",
        "profit_factor",
        "win_rate",
    }

    for node in ast.walk(_module_tree()):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name.split(".")[-1] not in forbidden
        elif isinstance(node, ast.ImportFrom):
            assert (node.module or "").split(".")[-1] not in forbidden
            for alias in node.names:
                assert alias.name not in forbidden
        elif isinstance(node, ast.Name):
            assert node.id not in forbidden
        elif isinstance(node, ast.Attribute):
            assert node.attr not in forbidden


def test_module_is_a_strategy_lab_leaf() -> None:
    import ast

    for node in ast.walk(_module_tree()):
        if isinstance(node, ast.ImportFrom):
            assert node.level == 0, f"relative import found: {ast.dump(node)}"
            assert not (node.module or "").startswith("src.services.strategy_lab")


def test_no_trading_calendar_or_data_layer_imports() -> None:
    import ast

    forbidden_roots = {
        "data_provider",
        "trading_calendar",
        "repositories",
        "storage",
        "sqlalchemy",
        "zoneinfo",
        "pytz",
        "experiment_governance",
        "pandas",
        "numpy",
    }

    for node in ast.walk(_module_tree()):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert not (set(alias.name.split(".")) & forbidden_roots), alias.name
        elif isinstance(node, ast.ImportFrom):
            assert not (set((node.module or "").split(".")) & forbidden_roots), node.module


def test_canonicalizer_rejects_uncoercible_values() -> None:
    from src.services.strategy_lab.information_dependency import _canonical_json

    class Opaque:
        pass

    with pytest.raises(ValueError):
        _canonical_json({"bad": Opaque()})
    with pytest.raises(ValueError):
        _canonical_json({"bad": 1.5})
