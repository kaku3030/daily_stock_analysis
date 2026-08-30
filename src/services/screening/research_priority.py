# -*- coding: utf-8 -*-
"""Deterministic research-priority fusion for candidate monitoring."""

from __future__ import annotations

from typing import Any

GRADE_BONUS = {"A": 20.0, "B": 14.0, "C": 6.0, "D": 0.0}
FINANCIAL_ATTENTION_BONUS = {"high": 20.0, "medium": 12.0, "low": 5.0, "none": 0.0}


def build_research_priority_events(
    candidates: list[dict[str, Any]],
    industry_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Rank candidates by research attention, never by trade desirability."""

    industry_map = {
        str(row.get("industry") or ""): row
        for row in industry_rows
        if str(row.get("industry") or "")
    }
    events: list[dict[str, Any]] = []
    for candidate in candidates:
        status = str(candidate.get("status") or "active")
        if status == "retired":
            continue

        grade = str(candidate.get("grade") or "D").upper()
        research_score = _number(candidate.get("score"))
        financial = candidate.get("financial_change")
        if not isinstance(financial, dict):
            financial = {}
        industry = industry_map.get(str(candidate.get("industry") or ""), {})
        catalysts = _text_list(candidate.get("catalysts"))
        risks = _text_list(candidate.get("risks"))

        score = research_score * 0.30
        score += GRADE_BONUS.get(grade, 0.0)
        score += 5.0 if status == "active" else 0.0

        industry_bonus, industry_signal = _industry_bonus(industry)
        score += industry_bonus

        financial_attention = str(financial.get("attention") or "none")
        score += FINANCIAL_ATTENTION_BONUS.get(financial_attention, 0.0)
        score += min(6.0, len(catalysts) * 2.0)
        # Risks increase research urgency; they are not treated as bullish points.
        score += min(4.0, len(risks) * 1.0)
        score = round(max(0.0, min(100.0, score)), 2)

        event_type, tone = _event_type(
            grade=grade,
            financial=financial,
            industry=industry,
            catalysts=catalysts,
        )
        reasons = _reasons(
            grade=grade,
            research_score=research_score,
            financial=financial,
            industry=industry,
            catalysts=catalysts,
            risks=risks,
        )
        priority = _priority_level(score)
        material_signal_count = sum(
            [
                financial_attention in {"high", "medium"},
                bool(financial.get("guidance_changed")),
                industry_signal,
                bool(catalysts),
                bool(risks),
            ]
        )
        notification_ready = bool(
            financial_attention == "high"
            or (priority in {"urgent", "high"} and material_signal_count >= 2)
        )

        events.append(
            {
                "code": str(candidate.get("code") or ""),
                "name": str(candidate.get("name") or ""),
                "grade": grade,
                "status": status,
                "industry": str(candidate.get("industry") or ""),
                "research_score": round(research_score, 2),
                "priority_score": score,
                "priority_level": priority,
                "event_type": event_type,
                "research_tone": tone,
                "notification_ready": notification_ready,
                "financial_attention": financial_attention,
                "earnings_trend": str(financial.get("earnings_trend") or "unknown"),
                "valuation_trend": str(financial.get("valuation_trend") or "unknown"),
                "guidance_changed": bool(financial.get("guidance_changed")),
                "industry_strength_score": industry.get("combined_strength_score"),
                "industry_market_score": industry.get("market_strength_score"),
                "industry_data_mode": str(industry.get("market_data_mode") or "none"),
                "catalysts": catalysts[:5],
                "risks": risks[:5],
                "reasons": reasons,
            }
        )

    priority_order = {"urgent": 0, "high": 1, "normal": 2, "low": 3}
    events.sort(
        key=lambda row: (
            priority_order.get(str(row["priority_level"]), 9),
            -float(row["priority_score"]),
            str(row["code"]),
        )
    )
    for rank, event in enumerate(events, start=1):
        event["priority_rank"] = rank
    return events


def research_priority_markdown(events: list[dict[str, Any]]) -> str:
    lines = [
        "# 美股研究优先级事件",
        "",
        "> 优先级表示“多快需要重新研究”，不是看多/看空，也不是交易指令。",
        "",
        "| 排名 | 股票 | 优先级 | 分数 | 类型 | 研究倾向 | 财务 | 行业 | 催化/风险 | 是否提醒 |",
        "|---:|---|---|---:|---|---|---|---:|---|---|",
    ]
    if not events:
        lines.append("| - | 暂无事件 | - | - | - | - | - | - | - | - |")
        return "\n".join(lines) + "\n"

    for event in events:
        signals = []
        if event.get("catalysts"):
            signals.append(f"催化{len(event['catalysts'])}")
        if event.get("risks"):
            signals.append(f"风险{len(event['risks'])}")
        industry_score = event.get("industry_market_score")
        lines.append(
            f"| {event.get('priority_rank', '')} | {event.get('code', '')} {event.get('name', '')} | "
            f"{event.get('priority_level', '')} | {float(event.get('priority_score') or 0):.1f} | "
            f"{event.get('event_type', '')} | {event.get('research_tone', '')} | "
            f"{event.get('financial_attention', 'none')} | "
            f"{('-' if industry_score is None else f'{float(industry_score):.1f}')} | "
            f"{('/'.join(signals) if signals else '-')} | "
            f"{('是' if event.get('notification_ready') else '否')} |"
        )
    return "\n".join(lines) + "\n"


def _industry_bonus(industry: dict[str, Any]) -> tuple[float, bool]:
    if not industry:
        return 0.0, False
    mode = str(industry.get("market_data_mode") or "candidate_only")
    if mode == "blended" and industry.get("market_strength_score") is not None:
        market_score = _number(industry.get("market_strength_score"))
        return min(15.0, market_score * 0.15), market_score >= 70.0
    # Candidate-only industry strength mostly reuses stock research scores, so keep
    # its contribution small to avoid double counting.
    research_strength = _number(industry.get("research_strength_score"))
    return min(5.0, research_strength * 0.05), False


def _event_type(
    *,
    grade: str,
    financial: dict[str, Any],
    industry: dict[str, Any],
    catalysts: list[str],
) -> tuple[str, str]:
    earnings = str(financial.get("earnings_trend") or "unknown")
    market_score = _number(industry.get("market_strength_score"))
    if earnings == "deteriorating":
        return "financial_risk", "risk_review"
    if bool(financial.get("guidance_changed")):
        return "guidance_change", "mixed"
    if grade in {"A", "B"} and earnings == "improving" and market_score >= 70:
        return "positive_convergence", "positive_watch"
    if grade in {"A", "B"} and catalysts:
        return "catalyst_focus", "positive_watch"
    if market_score >= 75:
        return "industry_focus", "neutral"
    if str(financial.get("valuation_trend") or "") == "expanding":
        return "valuation_watch", "mixed"
    return "priority_refresh", "neutral"


def _reasons(
    *,
    grade: str,
    research_score: float,
    financial: dict[str, Any],
    industry: dict[str, Any],
    catalysts: list[str],
    risks: list[str],
) -> list[str]:
    reasons = [f"候选等级 {grade} / 研究分 {research_score:.1f}"]
    attention = str(financial.get("attention") or "none")
    if attention != "none":
        reasons.append(
            f"财务变化 {attention}: {financial.get('earnings_trend', 'unknown')} / "
            f"{financial.get('valuation_trend', 'unknown')}"
        )
    if financial.get("guidance_changed"):
        reasons.append("管理层指引文本发生变化")
    if industry.get("market_strength_score") is not None:
        reasons.append(f"行业市场强度 {_number(industry.get('market_strength_score')):.1f}")
    if catalysts:
        reasons.append(f"存在 {len(catalysts)} 条催化线索")
    if risks:
        reasons.append(f"存在 {len(risks)} 条风险线索")
    return reasons


def _priority_level(score: float) -> str:
    if score >= 75:
        return "urgent"
    if score >= 58:
        return "high"
    if score >= 40:
        return "normal"
    return "low"


def _text_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _number(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0
