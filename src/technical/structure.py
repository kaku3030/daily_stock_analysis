"""Objective price-structure extraction and PIT-safe Structure Break V0.2."""

from dataclasses import dataclass, field
from typing import Any, Iterable, Optional

import pandas as pd

from .indicators import calculate_indicators
from .models import PriceStructure


RECLAIM_PENDING = "RECLAIM_PENDING"
RECLAIM_CONFIRMED = "RECLAIM_CONFIRMED"
RECLAIM_FAILED = "RECLAIM_FAILED"


@dataclass(frozen=True)
class StructureEvidence:
    """Typed, timestamped evidence; timestamps describe knowledge, not hindsight."""

    kind: str
    status: str
    pivot_time: Optional[Any] = None
    confirmed_at: Optional[Any] = None
    decision_available_at: Optional[Any] = None
    details: tuple[tuple[str, Any], ...] = ()


@dataclass(frozen=True)
class LeadershipPoolSnapshot:
    snapshot_id: str
    effective_at: Any
    members: frozenset[str]
    definition_version: str = "v1"


@dataclass(frozen=True)
class StructureBreakResult:
    state: str
    evidence: tuple[StructureEvidence, ...] = ()
    leadership_pool_snapshot_id: Optional[str] = None
    idempotency_key: Optional[str] = None


def detect_structure_break(
    snapshot: pd.DataFrame,
    *,
    decision_available_at: Any,
    data_quality: str = "PASS",
    leadership_pool: Optional[LeadershipPoolSnapshot] = None,
    reclaim_window_bars: int = 3,
    idempotency_key: Optional[str] = None,
) -> StructureBreakResult:
    """Pure, PIT-safe detector over an already supplied historical snapshot.

    The detector never fetches data or consults current membership.  Insufficient
    quality is UNKNOWN, and a lower high alone is only typed evidence.
    """
    if data_quality.upper() != "PASS":
        return StructureBreakResult("UNKNOWN", idempotency_key=idempotency_key)
    if snapshot is None or snapshot.empty or reclaim_window_bars < 1:
        return StructureBreakResult("UNKNOWN", idempotency_key=idempotency_key)
    required = {"high", "low", "close"}
    if not required.issubset(snapshot.columns) or len(snapshot) < 3:
        return StructureBreakResult("UNKNOWN", idempotency_key=idempotency_key)
    frame = snapshot.copy()
    evidence: list[StructureEvidence] = []
    highs = frame["high"].astype(float)
    lows = frame["low"].astype(float)
    if highs.iloc[-1] < highs.iloc[-2] and highs.iloc[-2] > highs.iloc[-3]:
        evidence.append(StructureEvidence("LOWER_HIGH_FORMED", "OBSERVED", decision_available_at=decision_available_at))
    if len(frame) >= 4 and lows.iloc[-1] < lows.iloc[-2] < lows.iloc[-3]:
        evidence.append(StructureEvidence("LOWER_LOW_CONFIRMED", "CONFIRMED", decision_available_at=decision_available_at))
    if len(frame) >= reclaim_window_bars + 1:
        prior = float(frame["close"].iloc[-reclaim_window_bars - 1])
        window = frame["close"].iloc[-reclaim_window_bars:]
        if (window < prior).all():
            evidence.append(StructureEvidence(RECLAIM_FAILED, "CONFIRMED", decision_available_at=decision_available_at))
        elif (window >= prior).any():
            evidence.append(StructureEvidence(RECLAIM_CONFIRMED, "CONFIRMED", decision_available_at=decision_available_at))
        else:
            evidence.append(StructureEvidence(RECLAIM_PENDING, "PENDING", decision_available_at=decision_available_at))
    state = "BREAK_CONFIRMED" if any(e.kind in {"LOWER_LOW_CONFIRMED", RECLAIM_FAILED} for e in evidence) else "NO_BREAK"
    return StructureBreakResult(state, tuple(evidence), leadership_pool.snapshot_id if leadership_pool else None, idempotency_key)


def reduce_leadership_structure(
    member_evidence: Iterable[tuple[str, StructureBreakResult]],
    *,
    leadership_pool: LeadershipPoolSnapshot,
) -> StructureBreakResult:
    """Reduce only members in the supplied historical pool snapshot."""
    selected = tuple(result for symbol, result in member_evidence if symbol in leadership_pool.members)
    evidence = tuple(e for result in selected for e in result.evidence)
    state = "BREAK_CONFIRMED" if any(result.state == "BREAK_CONFIRMED" for result in selected) else "NO_BREAK"
    return StructureBreakResult(state, evidence, leadership_pool.snapshot_id)


def _levels(series: pd.Series, *, largest: bool, count: int = 2) -> list[float]:
    values = series.dropna().astype(float)
    if values.empty:
        return []
    selected = values.nlargest(count) if largest else values.nsmallest(count)
    return sorted({round(float(value), 4) for value in selected})


def analyze_price_structure(df: Optional[pd.DataFrame]) -> PriceStructure:
    if df is None or df.empty:
        return PriceStructure(evidence=["structure_data_missing"])
    table = calculate_indicators(df, include_vwap=True)
    if len(table) < 20:
        return PriceStructure(evidence=["structure_insufficient_bars"], confidence=0.2)
    window = table.iloc[-40:].copy()
    latest = window.iloc[-1]
    midpoint = max(3, len(window) // 2)
    first, second = window.iloc[:midpoint], window.iloc[midpoint:]
    higher_high = second["high"].max() > first["high"].max()
    higher_low = second["low"].min() > first["low"].min()
    if higher_high and higher_low:
        sequence, state = "HH → HL", "bullish"
    elif not higher_high and not higher_low:
        sequence, state = "LH → LL", "bearish"
    else:
        sequence, state = "mixed", "range"

    close = float(latest["close"])
    vwap = latest.get("vwap")
    vwap_position = "unknown" if pd.isna(vwap) else "above" if close > float(vwap) else "below"
    ratio = latest.get("volume_ratio")
    if pd.isna(ratio):
        volume_confirmation = "unknown"
    elif float(ratio) >= 1.3:
        volume_confirmation = "confirmed"
    elif float(ratio) <= 0.7:
        volume_confirmation = "weak"
    else:
        volume_confirmation = "normal"
    atr = latest.get("atr14")
    atr_percent = None if pd.isna(atr) or not close else round(float(atr) / close * 100, 2)
    supports = [level for level in _levels(window["low"], largest=False, count=5) if level < close][-2:]
    resistances = [level for level in _levels(window["high"], largest=True, count=5) if level > close][:2]
    evidence = [f"结构={sequence}", f"VWAP位置={vwap_position}", f"量能确认={volume_confirmation}"]
    return PriceStructure(
        trend_sequence=sequence,
        structure_state=state,
        support_levels=supports,
        resistance_levels=resistances,
        vwap_position=vwap_position,
        volume_confirmation=volume_confirmation,
        atr_risk_percent=atr_percent,
        evidence=evidence,
        confidence=min(0.9, 0.5 + len(window) / 100),
    )
