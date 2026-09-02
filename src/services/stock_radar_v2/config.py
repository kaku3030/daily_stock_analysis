"""Validated configuration loader for Stock Radar V2."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


CONFIG_PATH = Path(__file__).with_name("stock_radar_v2.yaml")


def _value(section: dict[str, Any], name: str) -> Any:
    item = section[name]
    return item["value"] if isinstance(item, dict) and "value" in item else item


@dataclass(frozen=True)
class FallbackConfig:
    fail_count: int
    recovery_success_count: int
    health_check_interval_seconds: int
    cooldown_seconds: int


@dataclass(frozen=True)
class CriticalConfig:
    timeout_seconds: float
    timeout_count: int
    empty_or_parse_count: int
    closed_bar_integrity_count: int


@dataclass(frozen=True)
class ConfidenceConfig:
    portfolio_levels: tuple[int, int, int]
    signal_weights: dict[str, float]
    portfolio_weights: dict[str, float]


@dataclass(frozen=True)
class QAConfig:
    same_type_window: int
    failure_alert_count: int
    minimum_samples_for_weight_candidate: int
    auto_update_production_weights: bool


@dataclass(frozen=True)
class RuntimeConfig:
    minute_history_limit: int
    history_lookback_days: int
    daily_history_limit: int
    freshness_limit_seconds: int


@dataclass(frozen=True)
class StockRadarConfig:
    version: int
    fallback: FallbackConfig
    critical: CriticalConfig
    confidence: ConfidenceConfig
    qa: QAConfig
    runtime: RuntimeConfig


def _weights(raw: dict[str, Any], name: str) -> dict[str, float]:
    values = {str(key): float(_value(raw[name], key)) for key in raw[name]}
    if not values or abs(sum(values.values()) - 1.0) > 1e-9:
        raise ValueError(f"{name} weights must sum to 1")
    if any(value < 0 for value in values.values()):
        raise ValueError(f"{name} weights cannot be negative")
    return values


def load_stock_radar_config(path: Path | str = CONFIG_PATH) -> StockRadarConfig:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    fallback = raw["fallback"]
    critical = raw["critical"]
    confidence = raw["confidence"]
    qa = raw["qa"]
    runtime = raw["runtime"]
    levels = confidence["portfolio_levels"]
    result = StockRadarConfig(
        version=int(raw["version"]),
        fallback=FallbackConfig(
            fail_count=int(_value(fallback, "fail_count")),
            recovery_success_count=int(_value(fallback, "recovery_success_count")),
            health_check_interval_seconds=int(_value(fallback, "health_check_interval_seconds")),
            cooldown_seconds=int(_value(fallback, "cooldown_seconds")),
        ),
        critical=CriticalConfig(
            timeout_seconds=float(_value(critical, "timeout_seconds")),
            timeout_count=int(_value(critical, "timeout_count")),
            empty_or_parse_count=int(_value(critical, "empty_or_parse_count")),
            closed_bar_integrity_count=int(_value(critical, "closed_bar_integrity_count")),
        ),
        confidence=ConfidenceConfig(
            portfolio_levels=(
                int(_value(levels, "l0_min")),
                int(_value(levels, "l1_min")),
                int(_value(levels, "l2_min")),
            ),
            signal_weights=_weights(confidence, "signal_weights"),
            portfolio_weights=_weights(confidence, "portfolio_weights"),
        ),
        qa=QAConfig(
            same_type_window=int(_value(qa, "same_type_window")),
            failure_alert_count=int(_value(qa, "failure_alert_count")),
            minimum_samples_for_weight_candidate=int(
                _value(qa, "minimum_samples_for_weight_candidate")
            ),
            auto_update_production_weights=bool(_value(qa, "auto_update_production_weights")),
        ),
        runtime=RuntimeConfig(
            minute_history_limit=int(_value(runtime, "minute_history_limit")),
            history_lookback_days=int(_value(runtime, "history_lookback_days")),
            daily_history_limit=int(_value(runtime, "daily_history_limit")),
            freshness_limit_seconds=int(_value(runtime, "freshness_limit_seconds")),
        ),
    )
    if min(vars(result.fallback).values()) <= 0 or min(vars(result.critical).values()) <= 0:
        raise ValueError("fallback and critical thresholds must be positive")
    l0, l1, l2 = result.confidence.portfolio_levels
    if not (100 >= l0 > l1 > l2 >= 0):
        raise ValueError("portfolio confidence levels must descend within 0..100")
    if result.qa.failure_alert_count > result.qa.same_type_window:
        raise ValueError("QA failure threshold cannot exceed its window")
    if result.qa.minimum_samples_for_weight_candidate < result.qa.same_type_window:
        raise ValueError("weight-candidate sample minimum cannot be smaller than QA window")
    if result.qa.auto_update_production_weights:
        raise ValueError("Stock Radar V2 forbids automatic production-weight updates")
    if result.runtime.minute_history_limit < 60:
        raise ValueError("runtime minute history must include at least 60 bars")
    if (
        result.runtime.history_lookback_days <= 0
        or result.runtime.daily_history_limit < 20
        or result.runtime.freshness_limit_seconds <= 0
    ):
        raise ValueError("runtime daily history and freshness defaults must be positive and usable")
    return result
