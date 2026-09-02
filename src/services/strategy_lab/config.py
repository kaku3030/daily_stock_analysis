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
class StrategyLabValidationConfig:
    version: int
    parameter_stability: ParameterStabilityConfig


def load_strategy_lab_validation_config(
    path: Path | str = CONFIG_PATH,
) -> StrategyLabValidationConfig:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    section = raw["parameter_stability"]
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
    )


def load_parameter_stability_config(path: Path | str = CONFIG_PATH) -> ParameterStabilityConfig:
    """Convenience accessor for callers that only need the parameter-stability section."""

    return load_strategy_lab_validation_config(path).parameter_stability
