# -*- coding: utf-8 -*-
"""Candidate-derived research industry radar.

This module ranks industries from the persistent research candidate pool.  The
score is deliberately framed as *research strength*, not full-market performance:
it answers which industries currently contain the strongest, most persistent
research candidates.  Full market/ETF breadth can be layered on later without
changing this contract.
"""

from __future__ import annotations

from collections import defaultdict
from statistics import mean
from typing import Any


def build_industry_radar(
    candidates: list[dict[str, Any]],
    *,
    include_watching: bool = True,
    top_stocks_per_industry: int = 5,
) -> list[dict[str, Any]]:
    """Aggregate candidate-pool rows into ranked industry research states."""

    allowed_status = {"active"}
    if include_watching:
        allowed_status.add("watching")

    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for candidate in candidates:
        if str(candidate.get("status") or "active") not in allowed_status:
            continue
        industry = str(candidate.get("industry") or "").strip()
        if not industry:
            continue
        groups[industry].append(candidate)

    rows: list[dict[str, Any]] = []
    for industry, members in groups.items():
        scores = [_number(item.get("score")) for item in members]
        selected_counts = [max(0, int(item.get("selected_count") or 0)) for item in members]
        active_count = sum(str(item.get("status") or "") == "active" for item in members)
        watching_count = sum(str(item.get("status") or "") == "watching" for item in members)
        grade_a_count = sum(str(item.get("grade") or "") == "A" for item in members)
        grade_ab_count = sum(str(item.get("grade") or "") in {"A", "B"} for item in members)

        average_score = mean(scores) if scores else 0.0
        quality_share = grade_ab_count / len(members) if members else 0.0
        persistence_score = (
            mean(min(count, 5) / 5 * 100 for count in selected_counts)
            if selected_counts
            else 0.0
        )
        research_strength = _clamp(
            0.65 * average_score
            + 0.20 * (quality_share * 100)
            + 0.15 * persistence_score
        )

        sorted_members = sorted(
            members,
            key=lambda item: (
                -_number(item.get("score")),
                -int(item.get("selected_count") or 0),
                str(item.get("code") or ""),
            ),
        )
        top_candidates = [
            {
                "code": str(item.get("code") or ""),
                "name": str(item.get("name") or ""),
                "grade": str(item.get("grade") or ""),
                "score": round(_number(item.get("score")), 2),
                "status": str(item.get("status") or ""),
                "selected_count": int(item.get("selected_count") or 0),
            }
            for item in sorted_members[: max(1, top_stocks_per_industry)]
        ]

        rows.append(
            {
                "industry": industry,
                "research_strength_score": round(research_strength, 2),
                "average_candidate_score": round(average_score, 2),
                "candidate_count": len(members),
                "active_count": active_count,
                "watching_count": watching_count,
                "grade_a_count": grade_a_count,
                "grade_ab_count": grade_ab_count,
                "quality_share_pct": round(quality_share * 100, 1),
                "persistence_score": round(persistence_score, 1),
                "confidence": _confidence(len(members), grade_ab_count),
                "top_candidates": top_candidates,
            }
        )

    rows.sort(
        key=lambda row: (
            -float(row["research_strength_score"]),
            -int(row["candidate_count"]),
            str(row["industry"]),
        )
    )
    for index, row in enumerate(rows, start=1):
        row["rank"] = index
        for stock_rank, candidate in enumerate(row["top_candidates"], start=1):
            candidate["industry_rank"] = stock_rank
    return rows


def industry_radar_markdown(rows: list[dict[str, Any]]) -> str:
    """Render the research industry radar as compact Markdown."""

    lines = [
        "# 美股行业研究雷达",
        "",
        "> 当前版本基于长期候选池聚合，衡量的是“研究候选强度”，不是完整行业指数涨跌排名。",
        "",
        "| 排名 | 行业 | 强度分 | 候选数 | A/B占比 | 持续度 | 置信度 | 领先候选 |",
        "|---:|---|---:|---:|---:|---:|---|---|",
    ]
    if not rows:
        lines.append("| - | 暂无可用行业数据 | - | - | - | - | - | - |")
        return "\n".join(lines) + "\n"

    for row in rows:
        leaders = ", ".join(
            f"{item.get('code', '')}({float(item.get('score') or 0):.1f})"
            for item in row.get("top_candidates", [])[:3]
        )
        lines.append(
            f"| {row.get('rank', '')} | {row.get('industry', '')} | "
            f"{float(row.get('research_strength_score') or 0):.1f} | "
            f"{int(row.get('candidate_count') or 0)} | "
            f"{float(row.get('quality_share_pct') or 0):.1f}% | "
            f"{float(row.get('persistence_score') or 0):.1f} | "
            f"{row.get('confidence', '')} | {leaders} |"
        )
    return "\n".join(lines) + "\n"


def _confidence(candidate_count: int, grade_ab_count: int) -> str:
    if candidate_count >= 3 and grade_ab_count >= 2:
        return "high"
    if candidate_count >= 2:
        return "medium"
    return "low"


def _number(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _clamp(value: float) -> float:
    return max(0.0, min(100.0, value))
