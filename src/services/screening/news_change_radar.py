# -*- coding: utf-8 -*-
"""Presentation helpers for research news/catalyst changes."""

from __future__ import annotations

from typing import Any


def build_news_change_radar(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    order = {"new_risk": 0, "new_catalyst": 1, "unchanged": 2, "baseline": 3}
    for candidate in candidates:
        change = candidate.get("news_change")
        if not isinstance(change, dict):
            continue
        rows.append({
            "code": str(candidate.get("code") or ""),
            "name": str(candidate.get("name") or ""),
            "grade": str(candidate.get("grade") or ""),
            "state": str(change.get("state") or "unchanged"),
            "new_catalysts": change.get("new_catalysts") or [],
            "new_risks": change.get("new_risks") or [],
            "evidence_present": bool(change.get("evidence_present")),
        })
    rows.sort(key=lambda row: (order.get(row["state"], 9), row["code"]))
    return rows


def news_change_radar_markdown(rows: list[dict[str, Any]]) -> str:
    lines = [
        "# 美股新闻 / 催化剂变化雷达",
        "",
        "> 仅表示相对上一轮有效研究证据的变化，不构成交易建议。缺少新证据不会自动判定风险解除。",
        "",
        "| 股票 | 等级 | 状态 | 新催化 | 新风险 |",
        "|---|---|---|---:|---:|",
    ]
    if not rows:
        lines.append("| 暂无数据 | - | - | - | - |")
    for row in rows:
        lines.append(
            f"| {row.get('code', '')} {row.get('name', '')} | {row.get('grade', '')} | "
            f"{row.get('state', '')} | {len(row.get('new_catalysts') or [])} | {len(row.get('new_risks') or [])} |"
        )
    return "\n".join(lines) + "\n"
