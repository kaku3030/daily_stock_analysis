"""Independent signal and portfolio confidence calculations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from .config import StockRadarConfig, load_stock_radar_config
from .notifications import RadarNotifier


def _score(components: Mapping[str, float], weights: Mapping[str, float]) -> float:
    missing = set(weights).difference(components)
    if missing:
        raise ValueError(f"missing confidence components: {sorted(missing)}")
    values = {name: float(components[name]) for name in weights}
    if any(value < 0 or value > 100 for value in values.values()):
        raise ValueError("confidence components must be between 0 and 100")
    return round(sum(values[name] * weight for name, weight in weights.items()), 2)


@dataclass(frozen=True)
class SignalConfidence:
    score: float
    components: Mapping[str, float]


@dataclass(frozen=True)
class PortfolioRiskAssessment:
    portfolio_confidence: float
    level: str
    risk_gate: str
    components: Mapping[str, float]


def calculate_signal_confidence(
    components: Mapping[str, float],
    config: StockRadarConfig | None = None,
) -> SignalConfidence:
    resolved = config or load_stock_radar_config()
    return SignalConfidence(
        score=_score(components, resolved.confidence.signal_weights),
        components=dict(components),
    )


def assess_portfolio_confidence(
    components: Mapping[str, float],
    config: StockRadarConfig | None = None,
    *,
    notifier: RadarNotifier | None = None,
) -> PortfolioRiskAssessment:
    resolved = config or load_stock_radar_config()
    score = _score(components, resolved.confidence.portfolio_weights)
    l0_min, l1_min, l2_min = resolved.confidence.portfolio_levels
    if score >= l0_min:
        level, gate = "L0", "ALLOW_RESEARCH_FLOW"
    elif score >= l1_min:
        level, gate = "L1", "WATCH_PORTFOLIO_RISK"
    elif score >= l2_min:
        level, gate = "L2", "RESTRICT_NEW_POSITION"
    else:
        level, gate = "L3", "BLOCK_NEW_POSITION"
    assessment = PortfolioRiskAssessment(
        portfolio_confidence=score,
        level=level,
        risk_gate=gate,
        components=dict(components),
    )
    if level == "L3" and notifier is not None:
        notifier.notify(
            "portfolio_risk_alert",
            {
                "portfolio_confidence": score,
                "level": level,
                "risk_gate": gate,
            },
        )
    return assessment
