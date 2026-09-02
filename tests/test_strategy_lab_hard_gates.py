from dataclasses import fields

import pytest

from src.services.strategy_lab import (
    HARD_GATE_ORDER,
    GateResult,
    HardGatePipeline,
    PerformanceReport,
    StrategyValidationCase,
    ValidationDecision,
    ValidationReport,
)


def _checks(
    outcomes: dict[str, bool],
    calls: list[str],
) -> dict[str, object]:
    def build(gate: str):
        def check(case: StrategyValidationCase) -> GateResult:
            calls.append(gate)
            return GateResult(
                gate=gate,
                passed=outcomes.get(gate, True),
                reason=f"{gate}_checked",
                evidence={"strategy_id": case.strategy_id},
            )

        return check

    return {gate: build(gate) for gate in HARD_GATE_ORDER}


def test_hard_gates_run_in_frozen_order_before_expensive_validation() -> None:
    calls: list[str] = []
    report = HardGatePipeline(_checks({}, calls)).evaluate(StrategyValidationCase("breakout-v1"))

    assert HARD_GATE_ORDER == (
        "logic_integrity",
        "execution_causality",
        "lookahead",
        "execution_reality",
    )
    assert calls == list(HARD_GATE_ORDER)
    assert tuple(result.gate for result in report.hard_gate_results) == HARD_GATE_ORDER
    assert report.decision is ValidationDecision.PASS
    assert report.eligible_for_expensive_validation is True


def test_first_hard_gate_failure_stops_later_work() -> None:
    calls: list[str] = []
    report = HardGatePipeline(
        _checks({"execution_causality": False}, calls)
    ).evaluate(StrategyValidationCase("lookahead-fill"))

    assert calls == ["logic_integrity", "execution_causality"]
    assert report.decision is ValidationDecision.FAIL
    assert report.stopped_at == "execution_causality"
    assert report.eligible_for_expensive_validation is False


def test_attractive_performance_cannot_override_hard_gate_failure() -> None:
    performance = PerformanceReport(
        strategy_id="too-good-to-trust",
        cagr=8.0,
        sharpe=12.0,
        max_drawdown=0.01,
        profit_factor=20.0,
        win_rate=0.99,
    )
    report = HardGatePipeline(
        _checks({"lookahead": False}, [])
    ).evaluate(StrategyValidationCase(performance.strategy_id))

    validation_fields = {item.name for item in fields(ValidationReport)}
    performance_fields = {item.name for item in fields(PerformanceReport)} - {"strategy_id", "observations"}
    assert validation_fields.isdisjoint(performance_fields)
    assert report.decision is ValidationDecision.FAIL
    assert report.eligible_for_expensive_validation is False


def test_pipeline_requires_exact_frozen_hard_gate_set() -> None:
    checks = _checks({}, [])
    checks.pop("lookahead")

    with pytest.raises(ValueError, match=r"missing=\['lookahead'\]"):
        HardGatePipeline(checks)


def test_pipeline_rejects_result_for_wrong_gate() -> None:
    checks = _checks({}, [])
    checks["logic_integrity"] = lambda _case: GateResult(
        gate="lookahead",
        passed=True,
        reason="wrong gate",
    )

    with pytest.raises(ValueError, match="returned result for lookahead"):
        HardGatePipeline(checks).evaluate(StrategyValidationCase("bad-contract"))
