"""Typed output contracts for layered technical research."""

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class DataQuality:
    status: str = "missing"
    bars: int = 0
    as_of: Optional[str] = None
    is_partial_bar: bool = False
    warnings: List[str] = field(default_factory=list)


@dataclass
class TimeframeState:
    timeframe: str
    trend: str = "unknown"
    momentum: str = "unknown"
    volume_state: str = "unknown"
    structure_score: int = 0
    confidence: float = 0.0
    summary: str = "数据不足"
    indicators: Dict[str, Optional[float]] = field(default_factory=dict)
    evidence: List[str] = field(default_factory=list)
    quality: DataQuality = field(default_factory=DataQuality)


@dataclass
class PriceStructure:
    trend_sequence: str = "unknown"
    structure_state: str = "unknown"
    support_levels: List[float] = field(default_factory=list)
    resistance_levels: List[float] = field(default_factory=list)
    demand_zones: List[List[float]] = field(default_factory=list)
    supply_zones: List[List[float]] = field(default_factory=list)
    vwap_position: str = "unknown"
    volume_confirmation: str = "unknown"
    atr_risk_percent: Optional[float] = None
    evidence: List[str] = field(default_factory=list)
    confidence: float = 0.0


@dataclass
class MultiTimeframeTechnicalResult:
    code: str
    daily: TimeframeState
    hourly: TimeframeState
    intraday: TimeframeState
    structure: PriceStructure
    alignment: str
    state_summary: str
    research_score: int
    risk_flags: List[str] = field(default_factory=list)
    watch_conditions: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
