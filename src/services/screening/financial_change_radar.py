# -*- coding: utf-8 -*-
"""Render persisted financial changes as a research-priority radar."""

from __future__ import annotations

from typing import Any

ATTENTION_ORDER = {"high": 0, "medium": 1, "low": 2, "none": 3}


def build_financial_change_radar(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for candidate in candidates:
        change = candidate.get("financial_change")
        if not isinstance(change, dict) or not change:
            continue
        detail = change.get("detail") if isinstance(change.get("detail"), dict) else {}
        rows.append(
            {
                "code": str(candidate.get("code") or ""),
                "name": str(candidate.get("name") or ""),
                "grade": str(candidate.get("grade") or ""),
                "research_score": _number(candidate.get("score")),
                "status": str(candidate.get("status") or ""),
                "industry": str(candidate.get("industry") or ""),
                "state": str(change.get("state") or "stable"),
                "attention": str(change.get("attention") or "none"),
                "earnings_trend": str(change.get("earnings_trend") or "unknown"),
                "valuation_trend": str(change.get("valuation_trend") or "unknown"),
                "guidance_changed": bool(change.get("guidance_changed")),
                "summary": str(detail.get("summary") or ""),
                "observed_at": change.get("observed_at"),
                "run_id": str(change.get("run_id") or ""),
                "previous_run_id": str(change.get("previous_run_id") or ""),
            }
        )
    rows.sort(
        key=lambda row: (
            ATTENTION_ORDER.get(str(row["attention"]), 9),
            -float(row["research_score"]),
            str(row["code"]),
        )
    )
    return rows


def financial_change_radar_markdown(rows: list[dict[str, Any]]) -> str:
    lines = [
        "# 美股财务变化雷达",
        "",
        "> 对比相邻有效财务快照；盈利趋势、估值趋势与管理层指引分开判断。仅用于研究优先级，不构成交易建议。",
        "",
        "| 股票 | 等级 | 研究分 | 关注级别 | 盈利趋势 | 估值趋势 | 指引变化 | 核心变化 |",
        "|---|---|---:|---|---|---|---|---|",
    ]
    if not rows:
        lines.append("| 暂无可比较数据 | - | - | - | - | - | - | - |")
        return "\n".join(lines) + "\n"
    for row in rows:
        summary = str(row.get("summary") or "-").replace("|", "/").replace("\n", " ")
        lines.append(
            f"| {row.get('code', '')} {row.get('name', '')} | {row.get('grade', '')} | "
            f"{float(row.get('research_score') or 0):.1f} | {row.get('attention', 'none')} | "
            f"{row.get('earnings_trend', 'unknown')} | {row.get('valuation_trend', 'unknown')} | "
            f"{('是' if row.get('guidance_changed') else '否')} | {summary} |"
        )
    return "\n".join(lines) + "\n"


def _number(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0
