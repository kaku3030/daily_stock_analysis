# -*- coding: utf-8 -*-
"""Add material news transitions to deterministic research-priority events."""

from __future__ import annotations

from typing import Any

from src.services.screening.research_priority import build_research_priority_events


def build_research_priority_events_with_news(
    candidates: list[dict[str, Any]], industry_rows: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    events = build_research_priority_events(candidates, industry_rows)
    candidate_map = {str(row.get("code") or ""): row for row in candidates}
    for event in events:
        change = candidate_map.get(str(event.get("code") or ""), {}).get("news_change")
        if not isinstance(change, dict):
            continue
        state = str(change.get("state") or "unchanged")
        event["news_change_state"] = state
        event["new_catalysts"] = change.get("new_catalysts") or []
        event["new_risks"] = change.get("new_risks") or []
        if state == "new_risk":
            event["priority_score"] = min(100.0, round(float(event.get("priority_score") or 0) + 18.0, 2))
            if event.get("event_type") not in {"financial_risk", "guidance_change"}:
                event["event_type"] = "news_risk"
                event["research_tone"] = "risk_review"
            event["notification_ready"] = True
            event.setdefault("reasons", []).append(f"新增 {len(event['new_risks'])} 条风险事件")
        elif state == "new_catalyst":
            event["priority_score"] = min(100.0, round(float(event.get("priority_score") or 0) + 8.0, 2))
            if event.get("event_type") == "priority_refresh":
                event["event_type"] = "new_catalyst"
                event["research_tone"] = "positive_watch"
            event.setdefault("reasons", []).append(f"新增 {len(event['new_catalysts'])} 条催化事件")
        event["priority_level"] = _priority_level(float(event.get("priority_score") or 0))

    priority_order = {"urgent": 0, "high": 1, "normal": 2, "low": 3}
    events.sort(key=lambda row: (priority_order.get(str(row.get("priority_level")), 9), -float(row.get("priority_score") or 0), str(row.get("code") or "")))
    for rank, event in enumerate(events, start=1):
        event["priority_rank"] = rank
    return events


def _priority_level(score: float) -> str:
    if score >= 75:
        return "urgent"
    if score >= 58:
        return "high"
    if score >= 40:
        return "normal"
    return "low"
