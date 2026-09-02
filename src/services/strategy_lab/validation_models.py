"""Validation-only contracts for Strategy Lab.

Performance metrics intentionally do not belong in this module or its report.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping


class ValidationDecision(str, Enum):
    PASS = "pass"
    FAIL = "fail"


@dataclass(frozen=True)
class GateResult:
    gate: str
    passed: bool
    reason: str
    evidence: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.gate.strip():
            raise ValueError("gate must not be empty")
        if not self.reason.strip():
            raise ValueError("gate result reason must not be empty")


@dataclass(frozen=True)
class ValidationReport:
    strategy_id: str
    spec_version: str
    decision: ValidationDecision
    hard_gate_results: tuple[GateResult, ...]
    stopped_at: str | None

    def __post_init__(self) -> None:
        if not self.strategy_id.strip():
            raise ValueError("strategy_id must not be empty")
        if not self.spec_version.strip():
            raise ValueError("spec_version must not be empty")
        failed = tuple(result for result in self.hard_gate_results if not result.passed)
        if self.decision is ValidationDecision.PASS and (failed or self.stopped_at is not None):
            raise ValueError("passing validation report cannot contain a failed or stopped gate")
        if self.decision is ValidationDecision.FAIL:
            if len(failed) != 1 or self.stopped_at != failed[0].gate:
                raise ValueError("failed validation report must stop at its single failed gate")

    @property
    def eligible_for_expensive_validation(self) -> bool:
        """Hard Gates must pass before parameter, stress, or OOS work runs."""

        return self.decision is ValidationDecision.PASS
