"""Research-only Strategy Lab validation foundations."""

from .adversarial_checks import (
    assess_benchmark_alpha,
    assess_cost_robustness,
    assess_edge_concentration,
    assess_no_lookahead,
    assess_parameter_stability,
)
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
    "assess_benchmark_alpha",
    "assess_cost_robustness",
    "assess_edge_concentration",
    "assess_no_lookahead",
    "assess_parameter_stability",
]
