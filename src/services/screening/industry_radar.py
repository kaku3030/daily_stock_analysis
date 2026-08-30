# -*- coding: utf-8 -*-
"""Industry radar combining candidate quality with available market heat data."""

from __future__ import annotations

from collections import defaultdict
from statistics import mean
from typing import Any

MARKET_SIGNAL_FIELDS = (
    "industry_heat_score",
    "board_heat_score",
    "board_heat_latest_score",
    "board_heat_trend_score",
    "board_heat_persistence_score",
)


def build_industry_radar(
    candidates: list[dict[str, Any]],
    *,
    include_watching: bool = True,
    top_stocks_per_industry: int = 5,
) -> list[dict[str, Any]]:
    allowed_status = {"active", "watching"} if include_watching else {"active"}
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for candidate in candidates:
        if str(candidate.get("status") or "active") not in allowed_status:
            continue
        industry = str(candidate.get("industry") or "").strip()
        if industry:
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
        persistence_score = mean(min(count, 5) / 5 * 100 for count in selected_counts) if selected_counts else 0.0
        research_strength = _clamp(0.65 * average_score + 0.20 * quality_share * 100 + 0.15 * persistence_score)

        market_values = []
        market_field_coverage: dict[str, int] = {}
        for field in MARKET_SIGNAL_FIELDS:
            values = [_optional_number(item.get(field)) for item in members]
            values = [value for value in values if value is not None]
            if values:
                market_field_coverage[field] = len(values)
                market_values.append(mean(_clamp(value) for value in values))
        market_strength = mean(market_values) if market_values else None
        combined_strength = research_strength if market_strength is None else _clamp(0.55 * research_strength + 0.45 * market_strength)

        industry_change_values = [_optional_number(item.get("industry_change_pct")) for item in members]
        industry_change_values = [value for value in industry_change_values if value is not None]
        avg_industry_change = mean(industry_change_values) if industry_change_values else None
        source_ranks = [_optional_number(item.get("industry_rank")) for item in members]
        source_ranks = [value for value in source_ranks if value is not None]
        source_rank = min(source_ranks) if source_ranks else None

        sorted_members = sorted(members, key=lambda item: (-_number(item.get("score")), -int(item.get("selected_count") or 0), str(item.get("code") or "")))
        top_candidates = []
        for item in sorted_members[: max(1, top_stocks_per_industry)]:
            top_candidates.append({
                "code": str(item.get("code") or ""),
                "name": str(item.get("name") or ""),
                "grade": str(item.get("grade") or ""),
                "score": round(_number(item.get("score")), 2),
                "status": str(item.get("status") or ""),
                "selected_count": int(item.get("selected_count") or 0),
            })

        rows.append({
            "industry": industry,
            "combined_strength_score": round(combined_strength, 2),
            "research_strength_score": round(research_strength, 2),
            "market_strength_score": round(market_strength, 2) if market_strength is not None else None,
            "market_data_mode": "blended" if market_strength is not None else "candidate_only",
            "market_field_coverage": market_field_coverage,
            "source_industry_rank": int(source_rank) if source_rank is not None else None,
            "industry_change_pct": round(avg_industry_change, 2) if avg_industry_change is not None else None,
            "average_candidate_score": round(average_score, 2),
            "candidate_count": len(members),
            "active_count": active_count,
            "watching_count": watching_count,
            "grade_a_count": grade_a_count,
            "grade_ab_count": grade_ab_count,
            "quality_share_pct": round(quality_share * 100, 1),
            "persistence_score": round(persistence_score, 1),
            "confidence": _confidence(len(members), grade_ab_count, market_strength is not None),
            "top_candidates": top_candidates,
        })

    rows.sort(key=lambda row: (-float(row["combined_strength_score"]), -int(row["candidate_count"]), str(row["industry"])))
    for index, row in enumerate(rows, start=1):
        row["rank"] = index
        for stock_rank, candidate in enumerate(row["top_candidates"], start=1):
            candidate["industry_rank"] = stock_rank
    return rows


def industry_radar_markdown(rows: list[dict[str, Any]]) -> str:
    lines = [
        "# 美股行业研究雷达",
        "",
        "> 综合分优先融合候选池研究强度与已有行业/板块热度数据；缺少市场层数据时自动退化为 candidate_only。",
        "",
        "| 排名 | 行业 | 综合分 | 研究分 | 市场分 | 行业涨跌 | 候选数 | A/B占比 | 置信度 | 领先候选 |",
        "|---:|---|---:|---:|---:|---:|---:|---:|---|---|",
    ]
    if not rows:
        lines.append("| - | 暂无可用行业数据 | - | - | - | - | - | - | - | - |")
        return "\n".join(lines) + "\n"

    for row in rows:
        leaders = ", ".join(f"{item.get('code', '')}({float(item.get('score') or 0):.1f})" for item in row.get("top_candidates", [])[:3])
        market_score = row.get("market_strength_score")
        change_pct = row.get("industry_change_pct")
        lines.append(
            f"| {row.get('rank', '')} | {row.get('industry', '')} | {float(row.get('combined_strength_score') or 0):.1f} | "
            f"{float(row.get('research_strength_score') or 0):.1f} | {('-' if market_score is None else f'{float(market_score):.1f}')} | "
            f"{('-' if change_pct is None else f'{float(change_pct):+.2f}%')} | {int(row.get('candidate_count') or 0)} | "
            f"{float(row.get('quality_share_pct') or 0):.1f}% | {row.get('confidence', '')} | {leaders} |"
        )
    return "\n".join(lines) + "\n"


def _confidence(candidate_count: int, grade_ab_count: int, has_market_data: bool) -> str:
    if candidate_count >= 3 and grade_ab_count >= 2 and has_market_data:
        return "high"
    if candidate_count >= 2 or has_market_data:
        return "medium"
    return "low"


def _optional_number(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _number(value: Any) -> float:
    return _optional_number(value) or 0.0


def _clamp(value: float) -> float:
    return max(0.0, min(100.0, value))
