# -*- coding: utf-8 -*-
"""Notification adapter for material research-priority transitions."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

SEVERITY_ORDER = {"critical": 0, "warning": 1, "info": 2}


def format_research_priority_alert(alert: dict[str, Any]) -> str:
    severity = str(alert.get("severity") or "info")
    emoji = {"critical": "🚨", "warning": "⚠️", "info": "ℹ️"}.get(severity, "📌")
    code = str(alert.get("code") or "")
    name = str(alert.get("name") or "").strip()
    display = f"{name} ({code})" if name else code
    reasons = [str(item).strip() for item in alert.get("reasons", []) if str(item).strip()]

    lines = [
        f"{emoji} **美股研究状态变化：{display}**",
        "",
        f"- 变化：{alert.get('transition_type', 'unknown')}",
        f"- 研究优先级：{alert.get('previous_priority', 'none')} → {alert.get('current_priority', 'low')}",
        f"- 事件：{alert.get('previous_event_type', 'none')} → {alert.get('current_event_type', 'priority_refresh')}",
        f"- 研究倾向：{alert.get('previous_tone', 'none')} → {alert.get('current_tone', 'neutral')}",
        f"- 原因：{alert.get('reason', '研究状态发生重要变化')}",
    ]
    if reasons:
        lines.extend(["", "**本轮证据：**", *[f"- {item}" for item in reasons[:4]]])
    lines.extend([
        "",
        "> 这是研究优先级提醒，不是买卖建议或交易指令。",
    ])
    return "\n".join(lines)


def dispatch_research_priority_alerts(
    alerts: list[dict[str, Any]],
    *,
    market: str = "us",
    run_id: str = "",
    max_alerts: int = 5,
    notifier: Any | None = None,
) -> list[dict[str, Any]]:
    """Dispatch material transitions through the existing notification stack.

    This function is fail-open for the research scan: one channel or notifier failure
    is recorded in the returned diagnostics and never raises into the caller.
    """

    if not alerts:
        return []
    max_alerts = max(1, int(max_alerts))
    selected = sorted(
        alerts,
        key=lambda row: (
            SEVERITY_ORDER.get(str(row.get("severity") or "info"), 9),
            -float(row.get("priority_score") or 0.0),
            str(row.get("code") or ""),
        ),
    )[:max_alerts]

    if notifier is None:
        try:
            from src.notification import get_notification_service

            notifier = get_notification_service()
        except Exception as exc:
            logger.warning("Research alert notifier unavailable: %s", exc)
            return [
                _failed_result(alert, "notifier_unavailable", str(exc))
                for alert in selected
            ]

    results: list[dict[str, Any]] = []
    for alert in selected:
        code = str(alert.get("code") or "").strip().upper()
        severity = str(alert.get("severity") or "info")
        transition_type = str(alert.get("transition_type") or "unknown")
        current_type = str(alert.get("current_event_type") or "priority_refresh")
        current_priority = str(alert.get("current_priority") or "low")
        content = format_research_priority_alert(alert)
        dedup_key = ":".join(
            [
                "research_priority",
                market,
                code,
                run_id or "no_run",
                transition_type,
                current_type,
                current_priority,
            ]
        )
        cooldown_key = f"research_priority:{market}:{code}:{severity}"
        try:
            dispatch = notifier.send_with_results(
                content,
                email_stock_codes=[code] if code else None,
                route_type="alert",
                severity=severity,
                dedup_key=dedup_key,
                cooldown_key=cooldown_key,
            )
            channel_results = []
            for item in getattr(dispatch, "channel_results", []) or []:
                channel_results.append(
                    {
                        "channel": getattr(item, "channel", ""),
                        "success": bool(getattr(item, "success", False)),
                        "error_code": getattr(item, "error_code", None),
                        "retryable": bool(getattr(item, "retryable", False)),
                    }
                )
            results.append(
                {
                    "code": code,
                    "severity": severity,
                    "transition_type": transition_type,
                    "dispatched": bool(getattr(dispatch, "dispatched", False)),
                    "success": bool(getattr(dispatch, "success", False)),
                    "status": str(getattr(dispatch, "status", "unknown")),
                    "message": getattr(dispatch, "message", None),
                    "channels": channel_results,
                }
            )
        except Exception as exc:
            logger.warning("Research priority alert dispatch failed for %s: %s", code, exc)
            results.append(_failed_result(alert, "dispatch_exception", str(exc)))
    return results


def _failed_result(alert: dict[str, Any], status: str, message: str) -> dict[str, Any]:
    return {
        "code": str(alert.get("code") or "").strip().upper(),
        "severity": str(alert.get("severity") or "info"),
        "transition_type": str(alert.get("transition_type") or "unknown"),
        "dispatched": False,
        "success": False,
        "status": status,
        "message": message,
        "channels": [],
    }
