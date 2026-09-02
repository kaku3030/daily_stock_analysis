"""Research-only Strategy Lab validation foundations."""

from .hard_gates import HARD_GATE_ORDER, HardGatePipeline, StrategyValidationCase
from .performance_models import PerformanceReport
from .validation_models import GateResult, ValidationDecision, ValidationReport

__all__ = [
    "HARD_GATE_ORDER",
    "GateResult",
    "HardGatePipeline",
    "PerformanceReport",
    "StrategyValidationCase",
    "ValidationDecision",
    "ValidationReport",
]
