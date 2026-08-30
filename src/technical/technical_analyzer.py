"""Facade combining timeframe and price-structure evidence."""

from typing import Optional

import pandas as pd

from .models import MultiTimeframeTechnicalResult, TimeframeState
from .structure import analyze_price_structure
from .timeframe import analyze_timeframe


def _alignment(states: list[TimeframeState]) -> str:
    known = [state.trend for state in states if state.trend != "unknown"]
    if not known:
        return "unknown"
    if len(set(known)) == 1:
        return f"aligned_{known[0]}"
    return "mixed"


class TechnicalAnalyzer:
    """Describe multi-timeframe state without producing buy/sell orders."""

    def analyze(
        self,
        code: str,
        daily: pd.DataFrame,
        hourly: Optional[pd.DataFrame] = None,
        intraday: Optional[pd.DataFrame] = None,
        *,
        hourly_partial: bool = False,
        intraday_partial: bool = False,
    ) -> MultiTimeframeTechnicalResult:
        daily_state = analyze_timeframe(daily, "1d")
        hourly_state = analyze_timeframe(hourly, "1h", is_partial_bar=hourly_partial)
        intraday_state = analyze_timeframe(
            intraday,
            "15m",
            include_vwap=True,
            is_partial_bar=intraday_partial,
        )
        structure = analyze_price_structure(intraday if intraday is not None and not intraday.empty else daily)
        states = [daily_state, hourly_state, intraday_state]
        alignment = _alignment(states)

        # Daily evidence dominates research quality; lower timeframes only add
        # confirmation when present and never turn into an order by themselves.
        weighted = [(daily_state, 0.7), (hourly_state, 0.2), (intraday_state, 0.1)]
        available = [(state, weight) for state, weight in weighted if state.quality.status != "missing"]
        denominator = sum(weight for _, weight in available) or 1.0
        score = round(sum(state.structure_score * weight for state, weight in available) / denominator)
        risks = []
        if daily_state.trend == "bearish":
            risks.append("daily_trend_bearish")
        if alignment == "mixed":
            risks.append("timeframe_disagreement")
        for state in states:
            risks.extend(state.quality.warnings)
        watch = []
        if structure.resistance_levels:
            watch.append(f"观察是否有效突破压力 {structure.resistance_levels[0]}")
        if structure.support_levels:
            watch.append(f"观察支撑 {structure.support_levels[-1]} 是否保持")
        summary = f"日线{daily_state.trend}，1小时{hourly_state.trend}，15分钟{intraday_state.trend}；多周期{alignment}"
        return MultiTimeframeTechnicalResult(
            code=code,
            daily=daily_state,
            hourly=hourly_state,
            intraday=intraday_state,
            structure=structure,
            alignment=alignment,
            state_summary=summary,
            research_score=max(0, min(100, score)),
            risk_flags=list(dict.fromkeys(risks)),
            watch_conditions=watch,
        )
