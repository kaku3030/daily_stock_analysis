"""Objective price-structure extraction (swings, levels, VWAP and volume)."""

from typing import Optional

import pandas as pd

from .indicators import calculate_indicators
from .models import PriceStructure


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
