# -*- coding: utf-8 -*-
"""Transition gate for research-priority notifications."""

from __future__ import annotations

from typing import Any

PRIORITY_RANK = {"low": 0, "normal": 1, "high": 2, "urgent": 3}


def build_research_priority_alerts(
    current_events: list[dict[str, Any]],
    previous_events: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    alerts: list[dict[str, Any]] = []
    for current in current_events:
        code = str(current.get("code") or "").strip().upper()
        if not code:
            continue
        previous = previous_events.get(code)
        decision = evaluate_research_priority_transition(previous, current)
        if not decision["notify"]:
            continue
        alerts.append({
            "code": code,
            "name": str(current.get("name") or ""),
            "transition_type": decision["transition_type"],
            "severity": decision["severity"],
            "reason": decision["reason"],
            "previous_priority": str((previous or {}).get("priority_level") or "none"),
            "current_priority": str(current.get("priority_level") or "low"),
            "previous_event_type": str((previous or {}).get("event_type") or "none"),
            "current_event_type": str(current.get("event_type") or "priority_refresh"),
            "previous_tone": str((previous or {}).get("research_tone") or "none"),
            "current_tone": str(current.get("research_tone") or "neutral"),
            "priority_score": float(current.get("priority_score") or 0.0),
            "financial_attention": str(current.get("financial_attention") or "none"),
            "guidance_changed": bool(current.get("guidance_changed")),
            "reasons": list(current.get("reasons") or []),
        })
    severity_order = {"critical": 0, "warning": 1, "info": 2}
    alerts.sort(key=lambda row: (severity_order.get(str(row["severity"]), 9), -float(row["priority_score"]), str(row["code"])))
    return alerts


def evaluate_research_priority_transition(
    previous: dict[str, Any] | None,
    current: dict[str, Any],
) -> dict[str, Any]:
    current_priority = str(current.get("priority_level") or "low")
    current_type = str(current.get("event_type") or "priority_refresh")
    current_tone = str(current.get("research_tone") or "neutral")
    current_ready = bool(current.get("notification_ready"))

    if previous is None:
        if current_type == "guidance_change" and bool(current.get("guidance_changed")):
            return _decision(True, "new_guidance_change", "warning", "首次记录即发现管理层指引变化")
        if current_ready and current_type != "priority_refresh":
            severity = "critical" if current_tone == "risk_review" else "warning"
            return _decision(True, "new_material_event", severity, "首次记录即满足重大研究事件条件")
        return _decision(False, "baseline", "info", "首次记录仅建立基线")

    previous_priority = str(previous.get("priority_level") or "low")
    previous_type = str(previous.get("event_type") or "priority_refresh")
    previous_tone = str(previous.get("research_tone") or "neutral")

    if previous_tone != current_tone and {previous_tone, current_tone} == {"positive_watch", "risk_review"}:
        return _decision(True, "tone_flip", "critical", f"研究倾向由 {previous_tone} 反转为 {current_tone}")
    if previous_tone == "risk_review" and current_tone != "risk_review":
        return _decision(True, "risk_recovery", "info", "此前风险复核状态已解除或转弱")
    if current_type == "guidance_change" and bool(current.get("guidance_changed")) and previous_type != "guidance_change":
        return _decision(True, "new_guidance_change", "warning", "管理层指引出现新的文本变化")

    previous_rank = PRIORITY_RANK.get(previous_priority, 0)
    current_rank = PRIORITY_RANK.get(current_priority, 0)
    if current_rank > previous_rank and current_ready:
        severity = "critical" if current_priority == "urgent" else "warning"
        return _decision(True, "priority_upgrade", severity, f"研究优先级由 {previous_priority} 升至 {current_priority}")
    if current_type != previous_type and current_ready:
        severity = "critical" if current_tone == "risk_review" else "warning"
        return _decision(True, "material_event_change", severity, f"事件类型由 {previous_type} 变为 {current_type}")
    return _decision(False, "unchanged_or_deescalated", "info", "无新增重大变化或仅为降级/重复事件")


def research_priority_alerts_markdown(alerts: list[dict[str, Any]]) -> str:
    lines = [
        "# 美股研究事件提醒候选",
        "",
        "> 这里只保留真正值得提醒的变化：首次重大事件、优先级升级、指引新变化、事件反转或风险解除。",
        "",
        "| 股票 | 严重度 | 变化类型 | 优先级变化 | 事件变化 | 原因 |",
        "|---|---|---|---|---|---|",
    ]
    if not alerts:
        lines.append("| 暂无需要提醒的新增变化 | - | - | - | - | - |")
        return "\n".join(lines) + "\n"
    for alert in alerts:
        reason = str(alert.get("reason") or "").replace("|", "/")
        lines.append(
            f"| {alert.get('code', '')} {alert.get('name', '')} | {alert.get('severity', '')} | "
            f"{alert.get('transition_type', '')} | {alert.get('previous_priority', '')}→{alert.get('current_priority', '')} | "
            f"{alert.get('previous_event_type', '')}→{alert.get('current_event_type', '')} | {reason} |"
        )
    return "\n".join(lines) + "\n"


def _decision(notify: bool, transition_type: str, severity: str, reason: str) -> dict[str, Any]:
    return {"notify": notify, "transition_type": transition_type, "severity": severity, "reason": reason}
