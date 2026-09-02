"""Deterministic comparison for point-in-time technical research states."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping

from .technical_state import StockRadarTechnicalState


PERMISSION_RANK = {
    "normal": 3,
    "watch_only": 2,
    "record_only": 1,
    "blocked": 0,
}


def technical_state_evidence(state: StockRadarTechnicalState) -> dict[str, Any]:
    """Return the full point-in-time evidence without adding signal semantics."""

    return state.to_dict()


def technical_state_fingerprint(evidence: Mapping[str, Any]) -> str:
    """Fingerprint categorical state, excluding timestamps and small value drift."""

    stable = _stable_state(evidence)
    encoded = json.dumps(stable, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:20]


def compare_technical_states(
    previous: Mapping[str, Any] | None,
    current: Mapping[str, Any],
) -> dict[str, Any]:
    current_state = _stable_state(current)
    current_fingerprint = technical_state_fingerprint(current)
    if previous is None:
        return {
            "state": "unchanged",
            "attention": "none",
            "material": False,
            "baseline": True,
            "previous_fingerprint": "",
            "current_fingerprint": current_fingerprint,
            "changes": [],
            "can_confirm_signal": False,
        }

    previous_state = _stable_state(previous)
    previous_fingerprint = technical_state_fingerprint(previous)
    changes: list[str] = []

    old_permission = str(previous_state.get("signal_permission") or "blocked")
    new_permission = str(current_state.get("signal_permission") or "blocked")
    if PERMISSION_RANK.get(new_permission, 0) < PERMISSION_RANK.get(old_permission, 0):
        changes.append("permission_downgrade")
    elif PERMISSION_RANK.get(new_permission, 0) > PERMISSION_RANK.get(old_permission, 0):
        changes.append("permission_recovery")

    previous_timeframes = previous_state["timeframes"]
    current_timeframes = current_state["timeframes"]
    old_daily = previous_timeframes["1d"]["trend"]
    new_daily = current_timeframes["1d"]["trend"]
    if old_daily != new_daily:
        if "unknown" not in {old_daily, new_daily}:
            changes.append("daily_trend_change")
        else:
            changes.append("daily_data_availability_change")
    elif any(
        previous_timeframes["1d"][key] != current_timeframes["1d"][key]
        for key in ("momentum", "volume_state")
    ):
        changes.append("daily_state_change")

    if previous_state["alignment"] != current_state["alignment"]:
        changes.append("alignment_change")
    if any(
        any(
            previous_timeframes[timeframe][key] != current_timeframes[timeframe][key]
            for key in ("trend", "momentum", "volume_state")
        )
        for timeframe in ("1h", "15m")
    ):
        changes.append("lower_timeframe_change")
    if previous_state["structure"] != current_state["structure"]:
        changes.append("structure_change")
    if any(
        previous_timeframes[timeframe]["quality"] != current_timeframes[timeframe]["quality"]
        for timeframe in ("1d", "1h", "15m")
    ) or previous_state["quality_flags"] != current_state["quality_flags"]:
        changes.append("data_quality_change")

    if not changes and previous_fingerprint == current_fingerprint:
        state, attention, material = "unchanged", "none", False
    elif "permission_downgrade" in changes:
        state = "permission_downgrade"
        attention = "high" if new_permission == "blocked" else "medium"
        material = True
    elif "daily_trend_change" in changes:
        state, attention, material = "daily_trend_change", "medium", True
    elif "permission_recovery" in changes:
        state, attention, material = "permission_recovery", "low", False
    elif "daily_data_availability_change" in changes:
        state, attention, material = "daily_data_availability_change", "low", False
    elif "daily_state_change" in changes:
        state, attention, material = "daily_state_change", "low", False
    elif "alignment_change" in changes:
        state, attention, material = "alignment_change", "low", False
    elif "lower_timeframe_change" in changes:
        state, attention, material = "lower_timeframe_change", "low", False
    elif "structure_change" in changes:
        state, attention, material = "structure_change", "low", False
    else:
        state, attention, material = "data_quality_change", "low", False

    return {
        "state": state,
        "attention": attention,
        "material": material,
        "baseline": False,
        "previous_fingerprint": previous_fingerprint,
        "current_fingerprint": current_fingerprint,
        "changes": changes,
        "can_confirm_signal": False,
    }


def _stable_state(evidence: Mapping[str, Any]) -> dict[str, Any]:
    technical = evidence.get("technical")
    technical = technical if isinstance(technical, Mapping) else {}
    timeframes = {}
    for key, name in (("daily", "1d"), ("hourly", "1h"), ("intraday", "15m")):
        value = technical.get(key)
        value = value if isinstance(value, Mapping) else {}
        quality = value.get("quality")
        quality = quality if isinstance(quality, Mapping) else {}
        timeframes[name] = {
            "trend": str(value.get("trend") or "unknown"),
            "momentum": str(value.get("momentum") or "unknown"),
            "volume_state": str(value.get("volume_state") or "unknown"),
            "quality": {
                "status": str(quality.get("status") or "missing"),
                "is_partial_bar": bool(quality.get("is_partial_bar")),
                "warnings": sorted(str(item) for item in quality.get("warnings") or []),
            },
        }
    structure = technical.get("structure")
    structure = structure if isinstance(structure, Mapping) else {}
    return {
        "signal_permission": str(evidence.get("signal_permission") or "blocked"),
        "quality_flags": sorted(str(item) for item in evidence.get("quality_flags") or []),
        "alignment": str(technical.get("alignment") or "unknown"),
        "timeframes": timeframes,
        "structure": {
            "state": str(structure.get("structure_state") or "unknown"),
            "vwap_position": str(structure.get("vwap_position") or "unknown"),
            "volume_confirmation": str(structure.get("volume_confirmation") or "unknown"),
        },
    }
