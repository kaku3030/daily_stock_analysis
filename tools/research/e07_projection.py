"""Deterministic, research-only E07 Layer-B projection prototype.

This module is deliberately not imported by production runtime code.  It keeps
the raw payload and emits a compact, fetchable view only for explicitly
supported schemas.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any


class E07CompressionIneligible(ValueError):
    """The payload cannot be safely projected under the frozen E07 contract."""


_PROTECTED = {
    "unknown", "indeterminate", "data_unavailable", "stale_or_misaligned",
    "timestamp", "event_time", "available_at", "observed_at",
    "expected_session", "observed_session", "provider_timestamp",
    "provider", "provider_name", "source", "source_id", "status",
    "entitlement", "subscription", "delivery_status", "gate_result",
    "candidate_status", "reason_code", "reason_codes", "risk_flags",
    "portfolio", "quantity", "cost", "available", "frozen",
    "lifecycle_id", "thesis_id", "attempts", "retry", "fallback",
    "cooldown", "error", "exception", "failure", "fixture_id",
}
_PORTFOLIO_KEYS = {"portfolio", "quantity", "cost", "available", "frozen"}


def _walk_keys(value: Any) -> set[str]:
    if isinstance(value, dict):
        return {str(k).lower() for k in value} | set().union(*(_walk_keys(v) for v in value.values()))
    if isinstance(value, list):
        return set().union(*(_walk_keys(v) for v in value)) if value else set()
    return set()


def project_layer_b(payload: dict[str, Any], *, raw_ref: str) -> dict[str, Any]:
    """Return an explicit protected projection; reject unsupported ambiguity."""
    if not isinstance(payload, dict) or not raw_ref:
        raise E07CompressionIneligible("payload and raw_ref are required")
    keys = _walk_keys(payload)
    if keys & _PORTFOLIO_KEYS:
        return {"projection": "passthrough", "raw_ref": raw_ref, "payload": deepcopy(payload)}
    missing = sorted(k for k in (keys & _PROTECTED) if k not in payload and k not in {"provider", "source"})
    if missing:
        raise E07CompressionIneligible(f"nested protected fields require schema support: {missing}")
    protected = {k: deepcopy(v) for k, v in payload.items() if str(k).lower() in _PROTECTED}
    if not protected and not ("narrative" in payload or "repeated_log" in payload):
        raise E07CompressionIneligible("unsupported schema: no protected or compressible fields")
    compact = {"projection": "protected_fields", "raw_ref": raw_ref, "protected": protected}
    for field in ("narrative", "repeated_log"):
        if field in payload:
            text = str(payload[field])
            compact[field] = " ".join(dict.fromkeys(text.splitlines()))
    return compact


def protected_snapshot(payload: dict[str, Any]) -> dict[str, Any]:
    return {k: deepcopy(v) for k, v in payload.items() if str(k).lower() in _PROTECTED}
