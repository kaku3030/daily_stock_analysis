# -*- coding: utf-8 -*-
"""Deterministic comparison for point-in-time research financial snapshots."""

from __future__ import annotations

from typing import Any

QUALITY_FIELDS = (
    "revenue_growth",
    "eps_growth",
    "net_income_growth",
    "gross_margin",
    "operating_margin",
    "free_cash_flow",
)
VALUATION_FIELDS = (
    "pe_ratio",
    "forward_pe",
    "peg_ratio",
    "price_to_sales",
)
SIGNIFICANT_RELATIVE_CHANGE = 0.05


def compare_financial_snapshots(
    previous: dict[str, Any] | None,
    current: dict[str, Any] | None,
) -> dict[str, Any]:
    """Compare two normalized snapshots without inventing missing evidence.

    Numeric changes smaller than 5% relative to the previous magnitude are kept out
    of the headline trend to reduce provider noise. Guidance is only marked changed;
    free-text guidance is not classified as an upgrade or downgrade here.
    """

    if not previous:
        return {
            "state": "insufficient_history",
            "attention": "none",
            "earnings_trend": "unknown",
            "valuation_trend": "unknown",
            "guidance_changed": False,
            "quality_changes": [],
            "valuation_changes": [],
            "guidance": {},
            "summary": "首次财务快照，等待下一次有效数据后比较。",
        }

    previous = previous or {}
    current = current or {}
    prev_earnings = _mapping(previous.get("earnings"))
    curr_earnings = _mapping(current.get("earnings"))
    prev_valuation = _mapping(previous.get("valuation"))
    curr_valuation = _mapping(current.get("valuation"))

    quality_changes = _numeric_changes(
        prev_earnings,
        curr_earnings,
        QUALITY_FIELDS,
        higher_is="improved",
        lower_is="deteriorated",
    )
    valuation_changes = _numeric_changes(
        prev_valuation,
        curr_valuation,
        VALUATION_FIELDS,
        higher_is="expanded",
        lower_is="compressed",
    )

    guidance = _guidance_change(
        prev_earnings.get("guidance"),
        curr_earnings.get("guidance"),
    )
    earnings_trend = _trend_from_changes(
        quality_changes,
        positive="improved",
        negative="deteriorated",
    )
    valuation_trend = _trend_from_changes(
        valuation_changes,
        positive="expanded",
        negative="compressed",
        positive_label="expanding",
        negative_label="compressing",
    )
    state, attention = _overall_state(
        earnings_trend,
        valuation_trend,
        bool(guidance.get("changed")),
    )

    return {
        "state": state,
        "attention": attention,
        "earnings_trend": earnings_trend,
        "valuation_trend": valuation_trend,
        "guidance_changed": bool(guidance.get("changed")),
        "quality_changes": quality_changes,
        "valuation_changes": valuation_changes,
        "guidance": guidance,
        "summary": _summary(
            earnings_trend,
            valuation_trend,
            bool(guidance.get("changed")),
            quality_changes,
            valuation_changes,
        ),
    }


def _numeric_changes(
    previous: dict[str, Any],
    current: dict[str, Any],
    fields: tuple[str, ...],
    *,
    higher_is: str,
    lower_is: str,
) -> list[dict[str, Any]]:
    changes: list[dict[str, Any]] = []
    for field in fields:
        prev = _number(previous.get(field))
        curr = _number(current.get(field))
        if prev is None or curr is None:
            continue
        delta = curr - prev
        if not _significant(prev, curr):
            continue
        relative_change = None if prev == 0 else delta / abs(prev)
        changes.append(
            {
                "field": field,
                "previous": prev,
                "current": curr,
                "delta": delta,
                "relative_change": relative_change,
                "direction": higher_is if delta > 0 else lower_is,
            }
        )
    return changes


def _significant(previous: float, current: float) -> bool:
    if previous == current:
        return False
    if previous == 0:
        return current != 0
    return abs(current - previous) / abs(previous) >= SIGNIFICANT_RELATIVE_CHANGE


def _guidance_change(previous: Any, current: Any) -> dict[str, Any]:
    prev_text = _clean_text(previous)
    curr_text = _clean_text(current)
    if not prev_text or not curr_text:
        return {
            "changed": False,
            "comparable": False,
            "previous": prev_text or None,
            "current": curr_text or None,
        }
    return {
        "changed": prev_text.casefold() != curr_text.casefold(),
        "comparable": True,
        "previous": prev_text,
        "current": curr_text,
    }


def _trend_from_changes(
    changes: list[dict[str, Any]],
    *,
    positive: str,
    negative: str,
    positive_label: str = "improving",
    negative_label: str = "deteriorating",
) -> str:
    positive_count = sum(item.get("direction") == positive for item in changes)
    negative_count = sum(item.get("direction") == negative for item in changes)
    if positive_count and negative_count:
        return "mixed"
    if positive_count:
        return positive_label
    if negative_count:
        return negative_label
    return "stable"


def _overall_state(
    earnings_trend: str,
    valuation_trend: str,
    guidance_changed: bool,
) -> tuple[str, str]:
    if earnings_trend == "deteriorating":
        return "deteriorating", "high"
    if earnings_trend == "mixed":
        return "mixed", "medium"
    if earnings_trend == "improving" and valuation_trend == "expanding":
        return "mixed", "medium"
    if earnings_trend == "improving":
        return "improving", "low"
    if guidance_changed:
        return "guidance_changed", "medium"
    if valuation_trend != "stable":
        return "valuation_changed", "low"
    return "stable", "none"


def _summary(
    earnings_trend: str,
    valuation_trend: str,
    guidance_changed: bool,
    quality_changes: list[dict[str, Any]],
    valuation_changes: list[dict[str, Any]],
) -> str:
    parts: list[str] = []
    if quality_changes:
        labels = {
            "improving": "盈利/质量改善",
            "deteriorating": "盈利/质量恶化",
            "mixed": "盈利指标分化",
        }
        parts.append(f"{labels.get(earnings_trend, '盈利指标变化')} {len(quality_changes)} 项")
    if valuation_changes:
        labels = {
            "expanding": "估值扩张",
            "compressing": "估值压缩",
            "mixed": "估值指标分化",
        }
        parts.append(f"{labels.get(valuation_trend, '估值变化')} {len(valuation_changes)} 项")
    if guidance_changed:
        parts.append("管理层指引文本发生变化")
    return "；".join(parts) if parts else "未发现达到阈值的财务或估值变化。"


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _number(value: Any) -> float | None:
    if value in (None, "") or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).split()).strip()
