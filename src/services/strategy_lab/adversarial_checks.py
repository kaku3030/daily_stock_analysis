"""Deterministic checks exercised by the permanent adversarial suite.

Thresholds are explicit inputs. Test-fixture values are not production defaults.
"""

from __future__ import annotations

from datetime import datetime
from math import ceil, isfinite
from typing import Sequence

from .validation_models import GateResult


def assess_no_lookahead(
    *,
    signal_confirmed_at: datetime,
    latest_input_at: datetime,
) -> GateResult:
    passed = latest_input_at >= signal_confirmed_at
    return GateResult(
        gate="lookahead",
        passed=passed,
        reason="input_available_at_confirmation" if passed else "future_input_used",
        evidence={
            "signal_confirmed_at": signal_confirmed_at.isoformat(),
            "latest_input_at": latest_input_at.isoformat(),
        },
    )


def assess_parameter_stability(
    *,
    selected_score: float,
    neighboring_scores: Sequence[float],
    minimum_neighbor_score_ratio: float,
    minimum_stable_neighbor_fraction: float,
) -> GateResult:
    selected = _finite_value("selected_score", selected_score)
    neighbors = _finite_series("neighboring_scores", neighboring_scores)
    _require_fraction("minimum_neighbor_score_ratio", minimum_neighbor_score_ratio)
    _require_fraction("minimum_stable_neighbor_fraction", minimum_stable_neighbor_fraction)

    if selected <= 0:
        stable_fraction = 0.0
        passed = False
        reason = "selected_parameter_has_no_positive_edge"
    else:
        floor = selected * minimum_neighbor_score_ratio
        stable_fraction = sum(score >= floor for score in neighbors) / len(neighbors)
        passed = stable_fraction >= minimum_stable_neighbor_fraction
        reason = "parameter_neighborhood_stable" if passed else "parameter_cliff_detected"
    return GateResult(
        gate="parameter_stability",
        passed=passed,
        reason=reason,
        evidence={
            "selected_score": selected,
            "neighbor_count": len(neighbors),
            "stable_neighbor_fraction": stable_fraction,
            "minimum_neighbor_score_ratio": minimum_neighbor_score_ratio,
            "minimum_stable_neighbor_fraction": minimum_stable_neighbor_fraction,
        },
    )


def assess_edge_concentration(
    *,
    trade_pnls: Sequence[float],
    top_fraction: float,
    maximum_top_contribution_ratio: float,
) -> GateResult:
    pnls = _finite_series("trade_pnls", trade_pnls)
    _require_fraction("top_fraction", top_fraction, allow_one=True)
    if top_fraction == 0:
        raise ValueError("top_fraction must be positive")
    maximum_ratio = _finite_value("maximum_top_contribution_ratio", maximum_top_contribution_ratio)
    if maximum_ratio <= 0:
        raise ValueError("maximum_top_contribution_ratio must be positive")

    total_profit = sum(pnls)
    top_count = max(1, ceil(len(pnls) * top_fraction))
    top_profit = sum(sorted(pnls, reverse=True)[:top_count])
    contribution_ratio = top_profit / total_profit if total_profit > 0 else float("inf")
    passed = total_profit > 0 and contribution_ratio <= maximum_ratio
    reason = "edge_not_overconcentrated" if passed else "edge_concentration_detected"
    return GateResult(
        gate="edge_concentration",
        passed=passed,
        reason=reason,
        evidence={
            "trade_count": len(pnls),
            "total_profit": total_profit,
            "top_fraction": top_fraction,
            "top_count": top_count,
            "top_contribution_ratio": contribution_ratio,
            "maximum_top_contribution_ratio": maximum_ratio,
        },
    )


def assess_cost_robustness(
    *,
    baseline_profit: float,
    stressed_profit: float,
    minimum_retained_profit_ratio: float,
) -> GateResult:
    baseline = _finite_value("baseline_profit", baseline_profit)
    stressed = _finite_value("stressed_profit", stressed_profit)
    _require_fraction("minimum_retained_profit_ratio", minimum_retained_profit_ratio)
    retained_ratio = stressed / baseline if baseline > 0 else float("-inf")
    passed = baseline > 0 and stressed > 0 and retained_ratio >= minimum_retained_profit_ratio
    return GateResult(
        gate="cost_robustness",
        passed=passed,
        reason="edge_survives_cost_stress" if passed else "cost_fragility_detected",
        evidence={
            "baseline_profit": baseline,
            "stressed_profit": stressed,
            "retained_profit_ratio": retained_ratio,
            "minimum_retained_profit_ratio": minimum_retained_profit_ratio,
        },
    )


def assess_benchmark_alpha(
    *,
    strategy_returns: Sequence[float],
    benchmark_returns: Sequence[float],
    maximum_abs_alpha_for_beta_only: float,
    minimum_abs_beta_for_beta_only: float,
) -> GateResult:
    strategy = _finite_series("strategy_returns", strategy_returns, minimum_size=2)
    benchmark = _finite_series("benchmark_returns", benchmark_returns, minimum_size=2)
    if len(strategy) != len(benchmark):
        raise ValueError("strategy_returns and benchmark_returns must have equal length")
    max_alpha = _finite_value("maximum_abs_alpha_for_beta_only", maximum_abs_alpha_for_beta_only)
    min_beta = _finite_value("minimum_abs_beta_for_beta_only", minimum_abs_beta_for_beta_only)
    if max_alpha < 0 or min_beta < 0:
        raise ValueError("alpha and beta thresholds must be non-negative")

    benchmark_mean = sum(benchmark) / len(benchmark)
    strategy_mean = sum(strategy) / len(strategy)
    benchmark_variance = sum((value - benchmark_mean) ** 2 for value in benchmark)
    if benchmark_variance == 0:
        raise ValueError("benchmark_returns must have non-zero variance")
    covariance = sum(
        (benchmark_value - benchmark_mean) * (strategy_value - strategy_mean)
        for strategy_value, benchmark_value in zip(strategy, benchmark)
    )
    beta = covariance / benchmark_variance
    alpha = strategy_mean - beta * benchmark_mean
    beta_only = abs(alpha) <= max_alpha and abs(beta) >= min_beta
    return GateResult(
        gate="benchmark_alpha",
        passed=not beta_only,
        reason="independent_alpha_detected" if not beta_only else "beta_disguised_as_alpha",
        evidence={
            "sample_count": len(strategy),
            "alpha": alpha,
            "beta": beta,
            "maximum_abs_alpha_for_beta_only": max_alpha,
            "minimum_abs_beta_for_beta_only": min_beta,
        },
    )


def _finite_series(name: str, values: Sequence[float], *, minimum_size: int = 1) -> tuple[float, ...]:
    normalized = tuple(_finite_value(name, value) for value in values)
    if len(normalized) < minimum_size:
        raise ValueError(f"{name} requires at least {minimum_size} values")
    return normalized


def _finite_value(name: str, value: float) -> float:
    normalized = float(value)
    if not isfinite(normalized):
        raise ValueError(f"{name} must contain only finite values")
    return normalized


def _require_fraction(name: str, value: float, *, allow_one: bool = True) -> None:
    normalized = _finite_value(name, value)
    upper_valid = normalized <= 1 if allow_one else normalized < 1
    if normalized < 0 or not upper_valid:
        boundary = "[0, 1]" if allow_one else "[0, 1)"
        raise ValueError(f"{name} must be in {boundary}")
