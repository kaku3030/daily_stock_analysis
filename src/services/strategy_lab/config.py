"""Validated configuration loader for Strategy Lab.

Mirrors the ``src/services/stock_radar_v2/config.py`` pattern: every
governed, configurable threshold lives in the sibling YAML file with a
value/reason/evidence/introduced_in/last_changed record, so magic numbers
never sit directly in engine code. "Governed" does not imply the value has
been empirically calibrated against real backtest data -- see each entry's
own ``evidence`` field for its actual basis.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


CONFIG_PATH = Path(__file__).with_name("strategy_lab_validation.yaml")


def _value(section: dict[str, Any], name: str) -> Any:
    item = section[name]
    return item["value"] if isinstance(item, dict) and "value" in item else item


@dataclass(frozen=True)
class ParameterStabilityConfig:
    minimum_neighborhood_size: int
    plateau_relative_tolerance: float
    plateau_absolute_tolerance: float
    minimum_plateau_width: int
    plateau_score_saturation_width: int
    cliff_relative_drop_threshold: float
    cliff_minimum_scale: float
    stability_score_stable_floor: float
    stability_score_fragile_ceiling: float

    def __post_init__(self) -> None:
        if self.minimum_neighborhood_size < 2:
            raise ValueError("minimum_neighborhood_size must be at least 2")
        if not (0 < self.plateau_relative_tolerance <= 1):
            raise ValueError("plateau_relative_tolerance must be in (0, 1]")
        if self.plateau_absolute_tolerance < 0:
            raise ValueError("plateau_absolute_tolerance must be non-negative")
        if self.minimum_plateau_width < 2:
            raise ValueError("minimum_plateau_width must be at least 2")
        if self.plateau_score_saturation_width < self.minimum_plateau_width:
            raise ValueError(
                "plateau_score_saturation_width must be at least minimum_plateau_width"
            )
        if self.cliff_relative_drop_threshold <= 0:
            raise ValueError("cliff_relative_drop_threshold must be positive")
        if self.cliff_minimum_scale <= 0:
            raise ValueError("cliff_minimum_scale must be positive")
        if not (0 <= self.stability_score_fragile_ceiling < self.stability_score_stable_floor <= 1):
            raise ValueError(
                "stability score thresholds must satisfy "
                "0 <= fragile_ceiling < stable_floor <= 1"
            )


@dataclass(frozen=True)
class EdgeConcentrationConfig:
    minimum_trade_count: int
    minimum_positive_trade_count: int
    minimum_metadata_coverage: float
    top_fraction_small: float
    top_fraction_large: float
    top_months_window: int
    top_symbols_count: int
    fragility_moderate_floor: float
    fragility_concentrated_floor: float
    fragility_extreme_floor: float

    def __post_init__(self) -> None:
        if self.minimum_trade_count < 1:
            raise ValueError("minimum_trade_count must be at least 1")
        if self.minimum_positive_trade_count < 1:
            raise ValueError("minimum_positive_trade_count must be at least 1")
        if self.minimum_trade_count < self.minimum_positive_trade_count:
            raise ValueError(
                "minimum_trade_count must be at least minimum_positive_trade_count"
            )
        if not (0 < self.minimum_metadata_coverage <= 1):
            raise ValueError("minimum_metadata_coverage must be in (0, 1]")
        if not (0 < self.top_fraction_small <= 1):
            raise ValueError("top_fraction_small must be in (0, 1]")
        if not (0 < self.top_fraction_large <= 1):
            raise ValueError("top_fraction_large must be in (0, 1]")
        if self.top_fraction_small > self.top_fraction_large:
            raise ValueError("top_fraction_small must be at most top_fraction_large")
        if self.top_months_window < 1:
            raise ValueError("top_months_window must be at least 1")
        if self.top_symbols_count < 1:
            raise ValueError("top_symbols_count must be at least 1")
        if not (
            0 <= self.fragility_moderate_floor
            < self.fragility_concentrated_floor
            < self.fragility_extreme_floor
            <= 1
        ):
            raise ValueError(
                "fragility thresholds must satisfy "
                "0 <= moderate_floor < concentrated_floor < extreme_floor <= 1"
            )


@dataclass(frozen=True)
class ExecutionStressConfig:
    minimum_trade_count: int
    cost_multipliers: tuple[float, ...]
    delay_levels: tuple[int, ...]
    minimum_delay_price_coverage: float
    fragile_retention_floor: float
    moderate_retention_floor: float
    robust_retention_floor: float

    def __post_init__(self) -> None:
        if self.minimum_trade_count < 1:
            raise ValueError("minimum_trade_count must be at least 1")
        if not self.cost_multipliers:
            raise ValueError("cost_multipliers must not be empty")
        for multiplier in self.cost_multipliers:
            if multiplier < 1.0:
                raise ValueError("every cost_multiplier must be >= 1.0")
        if 1.0 not in self.cost_multipliers:
            raise ValueError("cost_multipliers must include the 1.0 reference multiplier")
        if len(set(self.cost_multipliers)) != len(self.cost_multipliers):
            raise ValueError("cost_multipliers must not contain duplicates")
        if not self.delay_levels:
            raise ValueError("delay_levels must not be empty")
        for delay in self.delay_levels:
            if not isinstance(delay, int) or delay < 0:
                raise ValueError("every delay level must be a non-negative integer")
        if 0 not in self.delay_levels:
            raise ValueError("delay_levels must include the 0-bar reference delay")
        if len(set(self.delay_levels)) != len(self.delay_levels):
            raise ValueError("delay_levels must not contain duplicates")
        if not (0 < self.minimum_delay_price_coverage <= 1):
            raise ValueError("minimum_delay_price_coverage must be in (0, 1]")
        if not (
            0 <= self.fragile_retention_floor
            < self.moderate_retention_floor
            < self.robust_retention_floor
        ):
            raise ValueError(
                "retention thresholds must satisfy "
                "0 <= fragile_floor < moderate_floor < robust_floor"
            )


@dataclass(frozen=True)
class StrategyLabValidationConfig:
    version: int
    parameter_stability: ParameterStabilityConfig
    edge_concentration: EdgeConcentrationConfig
    execution_stress: ExecutionStressConfig


def load_strategy_lab_validation_config(
    path: Path | str = CONFIG_PATH,
) -> StrategyLabValidationConfig:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    section = raw["parameter_stability"]
    edge_section = raw["edge_concentration"]
    execution_section = raw["execution_stress"]
    return StrategyLabValidationConfig(
        version=int(raw["version"]),
        parameter_stability=ParameterStabilityConfig(
            minimum_neighborhood_size=int(_value(section, "minimum_neighborhood_size")),
            plateau_relative_tolerance=float(_value(section, "plateau_relative_tolerance")),
            plateau_absolute_tolerance=float(_value(section, "plateau_absolute_tolerance")),
            minimum_plateau_width=int(_value(section, "minimum_plateau_width")),
            plateau_score_saturation_width=int(_value(section, "plateau_score_saturation_width")),
            cliff_relative_drop_threshold=float(_value(section, "cliff_relative_drop_threshold")),
            cliff_minimum_scale=float(_value(section, "cliff_minimum_scale")),
            stability_score_stable_floor=float(_value(section, "stability_score_stable_floor")),
            stability_score_fragile_ceiling=float(_value(section, "stability_score_fragile_ceiling")),
        ),
        edge_concentration=EdgeConcentrationConfig(
            minimum_trade_count=int(_value(edge_section, "minimum_trade_count")),
            minimum_positive_trade_count=int(_value(edge_section, "minimum_positive_trade_count")),
            minimum_metadata_coverage=float(_value(edge_section, "minimum_metadata_coverage")),
            top_fraction_small=float(_value(edge_section, "top_fraction_small")),
            top_fraction_large=float(_value(edge_section, "top_fraction_large")),
            top_months_window=int(_value(edge_section, "top_months_window")),
            top_symbols_count=int(_value(edge_section, "top_symbols_count")),
            fragility_moderate_floor=float(_value(edge_section, "fragility_moderate_floor")),
            fragility_concentrated_floor=float(_value(edge_section, "fragility_concentrated_floor")),
            fragility_extreme_floor=float(_value(edge_section, "fragility_extreme_floor")),
        ),
        execution_stress=ExecutionStressConfig(
            minimum_trade_count=int(_value(execution_section, "minimum_trade_count")),
            cost_multipliers=tuple(
                float(item) for item in _value(execution_section, "cost_multipliers")
            ),
            delay_levels=tuple(int(item) for item in _value(execution_section, "delay_levels")),
            minimum_delay_price_coverage=float(
                _value(execution_section, "minimum_delay_price_coverage")
            ),
            fragile_retention_floor=float(_value(execution_section, "fragile_retention_floor")),
            moderate_retention_floor=float(_value(execution_section, "moderate_retention_floor")),
            robust_retention_floor=float(_value(execution_section, "robust_retention_floor")),
        ),
    )


def load_parameter_stability_config(path: Path | str = CONFIG_PATH) -> ParameterStabilityConfig:
    """Convenience accessor for callers that only need the parameter-stability section."""

    return load_strategy_lab_validation_config(path).parameter_stability


def load_edge_concentration_config(path: Path | str = CONFIG_PATH) -> EdgeConcentrationConfig:
    """Convenience accessor for callers that only need the edge-concentration section."""

    return load_strategy_lab_validation_config(path).edge_concentration


def load_execution_stress_config(path: Path | str = CONFIG_PATH) -> ExecutionStressConfig:
    """Convenience accessor for callers that only need the execution-stress section."""

    return load_strategy_lab_validation_config(path).execution_stress
