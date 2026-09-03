"""Research-only Strategy Lab validation foundations."""

from .adversarial_checks import (
    assess_benchmark_alpha,
    assess_cost_robustness,
    assess_edge_concentration,
    assess_no_lookahead,
    assess_parameter_stability,
)
from .config import (
    EdgeConcentrationConfig,
    ParameterStabilityConfig,
    StrategyLabValidationConfig,
    load_edge_concentration_config,
    load_parameter_stability_config,
    load_strategy_lab_validation_config,
)
from .edge_concentration import (
    EdgeConcentrationResult,
    EdgeFragilityLabel,
    TradeObservation,
    evaluate_edge_concentration,
)
from .hard_gates import HARD_GATE_ORDER, HardGatePipeline, StrategyValidationCase
from .parameter_stability import (
    MetricDirection,
    ParameterObservation,
    ParameterStabilityLabel,
    ParameterStabilityResult,
    evaluate_parameter_stability,
)
from .performance_models import PerformanceReport
from .validation_models import GateResult, ValidationDecision, ValidationReport

__all__ = [
    "HARD_GATE_ORDER",
    "EdgeConcentrationConfig",
    "EdgeConcentrationResult",
    "EdgeFragilityLabel",
    "GateResult",
    "HardGatePipeline",
    "MetricDirection",
    "ParameterObservation",
    "ParameterStabilityConfig",
    "ParameterStabilityLabel",
    "ParameterStabilityResult",
    "PerformanceReport",
    "StrategyLabValidationConfig",
    "StrategyValidationCase",
    "TradeObservation",
    "ValidationDecision",
    "ValidationReport",
    "assess_benchmark_alpha",
    "assess_cost_robustness",
    "assess_edge_concentration",
    "assess_no_lookahead",
    "assess_parameter_stability",
    "evaluate_edge_concentration",
    "evaluate_parameter_stability",
    "load_edge_concentration_config",
    "load_parameter_stability_config",
    "load_strategy_lab_validation_config",
]
