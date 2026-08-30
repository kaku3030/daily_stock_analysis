# -*- coding: utf-8 -*-
"""Presentation helpers for deterministic news/catalyst change observations."""

from __future__ import annotations

from typing import Any


def build_news_change_radar(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    radar = []
    for row in rows:
        change = row.get("change") if isinstance(row.get("change"), dict) else {}
        radar.append({
            "code": str(row.get("code") or ""),
            "run_id": str(row.get("run_id") or ""),
            "captured_at": row.get("captured_at"),
            "state": str(change.get("state") or "unchanged"),
            "baseline": bool(change.get("baseline")),
            "attention": str(change.get("attention") or "none"),
            "events": change.get("events") or [],
            "new_catalysts": change.get("new_catalysts") or [],
            "new_risks": change.get("new_risks") or [],
            "resolved_or_missing": change.get("resolved_or_missing") or [],
            "news_evidence": change.get("news_evidence") or [],
        })
    attention_order = {"high": 0, "medium": 1, "low": 2, "none": 3}
    return sorted(radar, key=lambda row: (attention_order.get(row["attention"], 9), row["code"]))


def news_change_radar_markdown(rows: list[dict[str, Any]]) -> str:
    lines = [
        "# 美股新闻与催化变化雷达",
        "",
        "> 变化只调整研究复核优先级，不表示利多/利空结论，也不构成交易指令。",
        "",
        "| 股票 | 状态 | 关注度 | 新催化 | 新风险 | 消失/待确认 |",
        "|---|---|---|---:|---:|---:|",
    ]
    if not rows:
        lines.append("| - | 暂无快照 | - | - | - | - |")
        return "\n".join(lines) + "\n"
    for row in rows:
        state = "baseline" if row.get("baseline") else row.get("state", "unchanged")
        lines.append(
            f"| {row.get('code', '')} | {state} | {row.get('attention', 'none')} | "
            f"{len(row.get('new_catalysts') or [])} | {len(row.get('new_risks') or [])} | "
            f"{len(row.get('resolved_or_missing') or [])} |"
        )
    return "\n".join(lines) + "\n"

