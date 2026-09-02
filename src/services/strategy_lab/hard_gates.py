"""Ordered, fail-closed Hard Gate pipeline for Strategy Lab V0.1."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Mapping

from .validation_models import GateResult, ValidationDecision, ValidationReport


HARD_GATE_ORDER = (
    "logic_integrity",
    "execution_causality",
    "lookahead",
    "execution_reality",
)
SPEC_VERSION = "strategy-lab-v0.1"


@dataclass(frozen=True)
class StrategyValidationCase:
    strategy_id: str
    evidence: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.strategy_id.strip():
            raise ValueError("strategy_id must not be empty")


HardGateCheck = Callable[[StrategyValidationCase], GateResult]


class HardGatePipeline:
    """Run every required Hard Gate in frozen order and stop on first failure."""

    def __init__(self, checks: Mapping[str, HardGateCheck]) -> None:
        names = set(checks)
        required = set(HARD_GATE_ORDER)
        if names != required:
            missing = sorted(required - names)
            extra = sorted(names - required)
            raise ValueError(f"hard gate checks mismatch: missing={missing}, extra={extra}")
        self._checks = dict(checks)

    def evaluate(self, case: StrategyValidationCase) -> ValidationReport:
        results: list[GateResult] = []
        for gate in HARD_GATE_ORDER:
            result = self._checks[gate](case)
            if result.gate != gate:
                raise ValueError(f"hard gate {gate} returned result for {result.gate}")
            results.append(result)
            if not result.passed:
                return ValidationReport(
                    strategy_id=case.strategy_id,
                    spec_version=SPEC_VERSION,
                    decision=ValidationDecision.FAIL,
                    hard_gate_results=tuple(results),
                    stopped_at=gate,
                )
        return ValidationReport(
            strategy_id=case.strategy_id,
            spec_version=SPEC_VERSION,
            decision=ValidationDecision.PASS,
            hard_gate_results=tuple(results),
            stopped_at=None,
        )
