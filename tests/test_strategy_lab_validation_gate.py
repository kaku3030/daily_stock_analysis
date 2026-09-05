from pathlib import Path

import pytest

from src.services.strategy_lab.edge_concentration import EdgeConcentrationResult, EdgeFragilityLabel
from src.services.strategy_lab.execution_stress import ExecutionFragilityLabel, ExecutionStressResult
from src.services.strategy_lab.hard_gates import (
    HARD_GATE_ORDER,
    HardGatePipeline,
    StrategyValidationCase,
)
from src.services.strategy_lab.parameter_stability import (
    MetricDirection,
    ParameterStabilityLabel,
    ParameterStabilityResult,
)
from src.services.strategy_lab.validation_gate import (
    SOFT_VALIDATION_SOURCES,
    SoftValidationReport,
    SoftValidationResult,
    SoftValidationSource,
    SoftValidationStatus,
    aggregate_soft_validation,
    soft_validation_from_edge_concentration,
    soft_validation_from_execution_stress,
    soft_validation_from_parameter_stability,
)
from src.services.strategy_lab.validation_models import GateResult, ValidationDecision


# ---- Foundation-result builders (only the fields adapters care about) ----


def _param_stability(label: ParameterStabilityLabel, **overrides) -> ParameterStabilityResult:
    fields = dict(
        parameter_count=5,
        selected_parameter=1.0,
        direction=MetricDirection.MAXIMIZE,
        stability_label=label,
        warnings=(),
    )
    fields.update(overrides)
    return ParameterStabilityResult(**fields)


def _edge_concentration(label: EdgeFragilityLabel, **overrides) -> EdgeConcentrationResult:
    fields = dict(
        trade_count=25,
        positive_trade_count=25,
        fragility_label=label,
        warnings=(),
    )
    fields.update(overrides)
    return EdgeConcentrationResult(**fields)


def _execution_stress(label: ExecutionFragilityLabel, **overrides) -> ExecutionStressResult:
    fields = dict(
        trade_count=25,
        fragility_label=label,
        warnings=(),
    )
    fields.update(overrides)
    return ExecutionStressResult(**fields)


def _all_acceptable_results() -> list[SoftValidationResult]:
    return [
        soft_validation_from_parameter_stability(
            _param_stability(ParameterStabilityLabel.STABLE_PLATEAU)
        ),
        soft_validation_from_edge_concentration(
            _edge_concentration(EdgeFragilityLabel.DIVERSIFIED)
        ),
        soft_validation_from_execution_stress(
            _execution_stress(ExecutionFragilityLabel.ROBUST)
        ),
    ]


def _stub_hard_gate_pipeline(outcomes: dict[str, bool]) -> HardGatePipeline:
    def build(gate: str):
        def check(case: StrategyValidationCase) -> GateResult:
            return GateResult(
                gate=gate,
                passed=outcomes.get(gate, True),
                reason=f"{gate}_stub_checked",
            )

        return check

    return HardGatePipeline({gate: build(gate) for gate in HARD_GATE_ORDER})


# ---- Per-engine frozen label mapping ----


@pytest.mark.parametrize(
    "label,expected",
    [
        (ParameterStabilityLabel.STABLE_PLATEAU, SoftValidationStatus.ACCEPTABLE),
        (ParameterStabilityLabel.FRAGILE, SoftValidationStatus.CAUTION),
        (ParameterStabilityLabel.NARROW_PEAK, SoftValidationStatus.CAUTION),
        (ParameterStabilityLabel.UNSTABLE_CLIFF, SoftValidationStatus.FRAGILE),
        (ParameterStabilityLabel.INSUFFICIENT_DATA, SoftValidationStatus.INCONCLUSIVE),
    ],
)
def test_parameter_stability_frozen_mapping(label, expected) -> None:
    result = soft_validation_from_parameter_stability(_param_stability(label))
    assert result.status is expected
    assert result.source is SoftValidationSource.PARAMETER_STABILITY
    assert result.label == label.value


@pytest.mark.parametrize(
    "label,expected",
    [
        (EdgeFragilityLabel.DIVERSIFIED, SoftValidationStatus.ACCEPTABLE),
        (EdgeFragilityLabel.MODERATE, SoftValidationStatus.CAUTION),
        (EdgeFragilityLabel.CONCENTRATED, SoftValidationStatus.FRAGILE),
        (EdgeFragilityLabel.EXTREME, SoftValidationStatus.FRAGILE),
        (EdgeFragilityLabel.INSUFFICIENT_DATA, SoftValidationStatus.INCONCLUSIVE),
        (EdgeFragilityLabel.NO_POSITIVE_EDGE, SoftValidationStatus.INCONCLUSIVE),
    ],
)
def test_edge_concentration_frozen_mapping(label, expected) -> None:
    result = soft_validation_from_edge_concentration(_edge_concentration(label))
    assert result.status is expected
    assert result.source is SoftValidationSource.EDGE_CONCENTRATION
    assert result.label == label.value


@pytest.mark.parametrize(
    "label,expected",
    [
        (ExecutionFragilityLabel.ROBUST, SoftValidationStatus.ACCEPTABLE),
        (ExecutionFragilityLabel.MODERATE, SoftValidationStatus.CAUTION),
        (ExecutionFragilityLabel.FRAGILE, SoftValidationStatus.FRAGILE),
        (ExecutionFragilityLabel.EXTREME, SoftValidationStatus.FRAGILE),
        (ExecutionFragilityLabel.INSUFFICIENT_DATA, SoftValidationStatus.INCONCLUSIVE),
        (ExecutionFragilityLabel.NO_POSITIVE_BASELINE_EDGE, SoftValidationStatus.INCONCLUSIVE),
    ],
)
def test_execution_stress_frozen_mapping(label, expected) -> None:
    result = soft_validation_from_execution_stress(_execution_stress(label))
    assert result.status is expected
    assert result.source is SoftValidationSource.EXECUTION_STRESS
    assert result.label == label.value


def test_bad_foundation_labels_never_map_to_acceptable() -> None:
    bad_labels = [
        soft_validation_from_parameter_stability(
            _param_stability(ParameterStabilityLabel.UNSTABLE_CLIFF)
        ),
        soft_validation_from_edge_concentration(
            _edge_concentration(EdgeFragilityLabel.CONCENTRATED)
        ),
        soft_validation_from_edge_concentration(_edge_concentration(EdgeFragilityLabel.EXTREME)),
        soft_validation_from_execution_stress(
            _execution_stress(ExecutionFragilityLabel.FRAGILE)
        ),
        soft_validation_from_execution_stress(
            _execution_stress(ExecutionFragilityLabel.EXTREME)
        ),
    ]
    for result in bad_labels:
        assert result.status is not SoftValidationStatus.ACCEPTABLE


def test_insufficient_data_never_silently_passes() -> None:
    for result in (
        soft_validation_from_parameter_stability(
            _param_stability(ParameterStabilityLabel.INSUFFICIENT_DATA)
        ),
        soft_validation_from_edge_concentration(
            _edge_concentration(EdgeFragilityLabel.INSUFFICIENT_DATA)
        ),
        soft_validation_from_execution_stress(
            _execution_stress(ExecutionFragilityLabel.INSUFFICIENT_DATA)
        ),
    ):
        assert result.status is SoftValidationStatus.INCONCLUSIVE
        assert result.status is not SoftValidationStatus.ACCEPTABLE


def test_no_positive_edge_maps_to_inconclusive_not_hard_fail() -> None:
    edge_result = soft_validation_from_edge_concentration(
        _edge_concentration(EdgeFragilityLabel.NO_POSITIVE_EDGE)
    )
    execution_result = soft_validation_from_execution_stress(
        _execution_stress(ExecutionFragilityLabel.NO_POSITIVE_BASELINE_EDGE)
    )
    assert edge_result.status is SoftValidationStatus.INCONCLUSIVE
    assert execution_result.status is SoftValidationStatus.INCONCLUSIVE


def test_numeric_scores_cannot_override_frozen_labels() -> None:
    """A contrived, mismatched numeric score alongside a bad label must not
    change the adapter's output -- it reads the label field only.
    """

    contrived_high_score = _param_stability(
        ParameterStabilityLabel.UNSTABLE_CLIFF, stability_score=0.99
    )
    result = soft_validation_from_parameter_stability(contrived_high_score)
    assert result.status is SoftValidationStatus.FRAGILE

    contrived_low_fragility_score = _edge_concentration(
        EdgeFragilityLabel.EXTREME, fragility_score=0.0
    )
    result = soft_validation_from_edge_concentration(contrived_low_fragility_score)
    assert result.status is SoftValidationStatus.FRAGILE

    contrived_high_retention = _execution_stress(
        ExecutionFragilityLabel.EXTREME, worst_retention=1.0, fragility_score=0.0
    )
    result = soft_validation_from_execution_stress(contrived_high_retention)
    assert result.status is SoftValidationStatus.FRAGILE


# ---- Aggregation precedence ----


def test_one_fragile_source_dominates_aggregate() -> None:
    results = [
        soft_validation_from_parameter_stability(
            _param_stability(ParameterStabilityLabel.STABLE_PLATEAU)
        ),
        soft_validation_from_edge_concentration(
            _edge_concentration(EdgeFragilityLabel.DIVERSIFIED)
        ),
        soft_validation_from_execution_stress(
            _execution_stress(ExecutionFragilityLabel.EXTREME)
        ),
    ]
    report = aggregate_soft_validation(strategy_id="s1", results=results)
    assert report.overall_status is SoftValidationStatus.FRAGILE


def test_inconclusive_dominates_caution_when_no_fragile_exists() -> None:
    results = [
        soft_validation_from_parameter_stability(
            _param_stability(ParameterStabilityLabel.FRAGILE)
        ),
        soft_validation_from_edge_concentration(
            _edge_concentration(EdgeFragilityLabel.INSUFFICIENT_DATA)
        ),
        soft_validation_from_execution_stress(
            _execution_stress(ExecutionFragilityLabel.ROBUST)
        ),
    ]
    report = aggregate_soft_validation(strategy_id="s1", results=results)
    assert report.overall_status is SoftValidationStatus.INCONCLUSIVE


def test_caution_dominates_acceptable() -> None:
    results = [
        soft_validation_from_parameter_stability(
            _param_stability(ParameterStabilityLabel.STABLE_PLATEAU)
        ),
        soft_validation_from_edge_concentration(
            _edge_concentration(EdgeFragilityLabel.MODERATE)
        ),
        soft_validation_from_execution_stress(
            _execution_stress(ExecutionFragilityLabel.ROBUST)
        ),
    ]
    report = aggregate_soft_validation(strategy_id="s1", results=results)
    assert report.overall_status is SoftValidationStatus.CAUTION


def test_all_acceptable_yields_acceptable() -> None:
    report = aggregate_soft_validation(strategy_id="s1", results=_all_acceptable_results())
    assert report.overall_status is SoftValidationStatus.ACCEPTABLE


def test_aggregation_is_order_invariant() -> None:
    results = [
        soft_validation_from_parameter_stability(
            _param_stability(ParameterStabilityLabel.FRAGILE)
        ),
        soft_validation_from_edge_concentration(
            _edge_concentration(EdgeFragilityLabel.INSUFFICIENT_DATA)
        ),
        soft_validation_from_execution_stress(
            _execution_stress(ExecutionFragilityLabel.EXTREME)
        ),
    ]
    forward = aggregate_soft_validation(strategy_id="s1", results=results)
    reversed_report = aggregate_soft_validation(strategy_id="s1", results=list(reversed(results)))
    rotated = aggregate_soft_validation(
        strategy_id="s1", results=[results[2], results[0], results[1]]
    )
    assert forward.overall_status is reversed_report.overall_status is rotated.overall_status
    assert forward.overall_status is SoftValidationStatus.FRAGILE


def test_results_are_canonicalized_regardless_of_input_order() -> None:
    """``overall_status`` was always order-invariant; ``results`` itself
    must now also be canonicalized to the fixed SOFT_VALIDATION_SOURCES
    order, so differently-ordered inputs produce identical, comparable
    reports.
    """

    results = [
        soft_validation_from_parameter_stability(
            _param_stability(ParameterStabilityLabel.FRAGILE)
        ),
        soft_validation_from_edge_concentration(
            _edge_concentration(EdgeFragilityLabel.INSUFFICIENT_DATA)
        ),
        soft_validation_from_execution_stress(
            _execution_stress(ExecutionFragilityLabel.EXTREME)
        ),
    ]
    forward = aggregate_soft_validation(strategy_id="s1", results=results)
    reversed_report = aggregate_soft_validation(strategy_id="s1", results=list(reversed(results)))
    rotated = aggregate_soft_validation(
        strategy_id="s1", results=[results[2], results[0], results[1]]
    )

    expected_order = (
        SoftValidationSource.PARAMETER_STABILITY,
        SoftValidationSource.EDGE_CONCENTRATION,
        SoftValidationSource.EXECUTION_STRESS,
    )
    assert tuple(result.source for result in forward.results) == expected_order
    assert forward.results == reversed_report.results == rotated.results
    assert forward.overall_status is reversed_report.overall_status is rotated.overall_status
    assert forward == reversed_report == rotated


# ---- Fail-closed source integrity ----


def test_missing_source_fails_closed() -> None:
    only_two = _all_acceptable_results()[:2]
    with pytest.raises(ValueError):
        aggregate_soft_validation(strategy_id="s1", results=only_two)


def test_duplicate_source_fails_closed() -> None:
    duplicated = _all_acceptable_results()
    duplicated[2] = soft_validation_from_parameter_stability(
        _param_stability(ParameterStabilityLabel.STABLE_PLATEAU)
    )
    with pytest.raises(ValueError):
        aggregate_soft_validation(strategy_id="s1", results=duplicated)


def test_inconsistent_manually_constructed_overall_status_fails_closed() -> None:
    results = tuple(_all_acceptable_results())  # all ACCEPTABLE
    with pytest.raises(ValueError):
        SoftValidationReport(
            strategy_id="s1",
            overall_status=SoftValidationStatus.FRAGILE,  # inconsistent with results
            results=results,
        )


def test_malformed_unknown_source_cannot_enter_report() -> None:
    with pytest.raises(ValueError):
        SoftValidationResult(
            source="not_a_real_source",  # type: ignore[arg-type]
            status=SoftValidationStatus.ACCEPTABLE,
            label="whatever",
            reason="whatever",
        )


def test_malformed_unknown_status_fails_closed() -> None:
    with pytest.raises(ValueError):
        SoftValidationResult(
            source=SoftValidationSource.PARAMETER_STABILITY,
            status="not_a_real_status",  # type: ignore[arg-type]
            label="whatever",
            reason="whatever",
        )


def test_raw_valid_source_string_rejected_strictly() -> None:
    """Enum fields use strict validation, not coercion: even an
    otherwise-valid raw string must be rejected.
    """

    with pytest.raises(ValueError):
        SoftValidationResult(
            source="parameter_stability",  # type: ignore[arg-type]
            status=SoftValidationStatus.ACCEPTABLE,
            label="whatever",
            reason="whatever",
        )


def test_raw_valid_status_string_rejected_strictly() -> None:
    with pytest.raises(ValueError):
        SoftValidationResult(
            source=SoftValidationSource.PARAMETER_STABILITY,
            status="acceptable",  # type: ignore[arg-type]
            label="whatever",
            reason="whatever",
        )


def test_raw_valid_overall_status_string_rejected_strictly() -> None:
    results = tuple(_all_acceptable_results())
    with pytest.raises(ValueError):
        SoftValidationReport(
            strategy_id="s1",
            overall_status="acceptable",  # type: ignore[arg-type]
            results=results,
        )


def test_malformed_child_result_fails_closed() -> None:
    results = _all_acceptable_results()
    results[1] = "not_a_soft_validation_result"  # type: ignore[assignment]
    with pytest.raises(ValueError):
        SoftValidationReport(
            strategy_id="s1",
            overall_status=SoftValidationStatus.ACCEPTABLE,
            results=tuple(results),
        )


def test_empty_results_fails_closed() -> None:
    with pytest.raises(ValueError):
        aggregate_soft_validation(strategy_id="s1", results=[])


def test_soft_validation_result_requires_nonempty_label_and_reason() -> None:
    with pytest.raises(ValueError):
        SoftValidationResult(
            source=SoftValidationSource.PARAMETER_STABILITY,
            status=SoftValidationStatus.ACCEPTABLE,
            label="",
            reason="x",
        )
    with pytest.raises(ValueError):
        SoftValidationResult(
            source=SoftValidationSource.PARAMETER_STABILITY,
            status=SoftValidationStatus.ACCEPTABLE,
            label="x",
            reason="",
        )


def test_frozen_sources_are_exactly_three() -> None:
    assert set(SOFT_VALIDATION_SOURCES) == {
        SoftValidationSource.PARAMETER_STABILITY,
        SoftValidationSource.EDGE_CONCENTRATION,
        SoftValidationSource.EXECUTION_STRESS,
    }
    assert len(SOFT_VALIDATION_SOURCES) == 3


# ---- Deterministic reason strings ----


def test_reason_strings_are_deterministic() -> None:
    label = ParameterStabilityLabel.STABLE_PLATEAU
    first = soft_validation_from_parameter_stability(_param_stability(label))
    second = soft_validation_from_parameter_stability(_param_stability(label))
    assert first.reason == second.reason


# ---- Hard / Soft independence ----


def test_hard_fail_cannot_be_softened_by_good_soft_evidence() -> None:
    hard_pipeline = _stub_hard_gate_pipeline({"execution_reality": False})
    hard_report = hard_pipeline.evaluate(StrategyValidationCase("strategy-x"))
    assert hard_report.decision is ValidationDecision.FAIL

    soft_report = aggregate_soft_validation(strategy_id="strategy-x", results=_all_acceptable_results())
    assert soft_report.overall_status is SoftValidationStatus.ACCEPTABLE

    # Nothing in this module reads or mutates hard_report -- constructing an
    # all-ACCEPTABLE SoftValidationReport alongside it cannot change it.
    assert hard_report.decision is ValidationDecision.FAIL


def test_hard_pass_does_not_imply_soft_acceptable() -> None:
    hard_pipeline = _stub_hard_gate_pipeline({})
    hard_report = hard_pipeline.evaluate(StrategyValidationCase("strategy-x"))
    assert hard_report.decision is ValidationDecision.PASS

    fragile_results = [
        soft_validation_from_parameter_stability(
            _param_stability(ParameterStabilityLabel.STABLE_PLATEAU)
        ),
        soft_validation_from_edge_concentration(
            _edge_concentration(EdgeFragilityLabel.DIVERSIFIED)
        ),
        soft_validation_from_execution_stress(
            _execution_stress(ExecutionFragilityLabel.EXTREME)
        ),
    ]
    soft_report = aggregate_soft_validation(strategy_id="strategy-x", results=fragile_results)

    assert hard_report.decision is ValidationDecision.PASS
    assert soft_report.overall_status is SoftValidationStatus.FRAGILE
    assert soft_report.overall_status is not SoftValidationStatus.ACCEPTABLE


# ---- Performance isolation ----


def test_no_performance_report_dependency() -> None:
    """Permanent structural test: validation_gate.py must never *import* or
    *reference in code* performance_models / PerformanceReport / any
    absolute-return field. Checked via the AST (import nodes, Name/Attribute
    identifiers), not a raw substring scan, so the module's own docstring
    prose explaining that it has no such dependency does not trip this
    check -- only actual imports/usages would.
    """

    import ast

    from src.services.strategy_lab import validation_gate

    source = Path(validation_gate.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)

    forbidden_identifiers = {
        "performance_models",
        "PerformanceReport",
        "cagr",
        "sharpe",
        "max_drawdown",
        "profit_factor",
        "win_rate",
    }

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name.split(".")[-1] not in forbidden_identifiers
        elif isinstance(node, ast.ImportFrom):
            assert (node.module or "").split(".")[-1] not in forbidden_identifiers
            for alias in node.names:
                assert alias.name not in forbidden_identifiers
        elif isinstance(node, ast.Name):
            assert node.id not in forbidden_identifiers
        elif isinstance(node, ast.Attribute):
            assert node.attr not in forbidden_identifiers
