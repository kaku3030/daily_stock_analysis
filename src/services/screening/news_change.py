# -*- coding: utf-8 -*-
"""Deterministic change detection for research catalysts, risks and news evidence."""

from __future__ import annotations

import hashlib
import re
from typing import Any

_TOKEN_RE = re.compile(r"[a-z0-9]+|[\u4e00-\u9fff]+", re.IGNORECASE)
_STOPWORDS = {"a", "an", "the", "and", "or", "of", "to", "for", "in", "on", "with", "is", "are", "remains", "continues"}


def normalize_event_text(value: Any) -> str:
    text = str(value or "").strip().lower()
    tokens = [token for token in _TOKEN_RE.findall(text) if token not in _STOPWORDS]
    return " ".join(tokens)


def event_fingerprint(value: Any) -> str:
    normalized = normalize_event_text(value)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:20] if normalized else ""


def event_items(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    result: list[dict[str, str]] = []
    seen: set[str] = set()
    for raw in value:
        text = str(raw or "").strip()
        normalized = normalize_event_text(text)
        fingerprint = event_fingerprint(text)
        if not text or not normalized or fingerprint in seen:
            continue
        result.append({"text": text, "normalized": normalized, "fingerprint": fingerprint})
        seen.add(fingerprint)
    return result


def compare_event_snapshots(previous: dict[str, Any] | None, current: dict[str, Any]) -> dict[str, Any]:
    """Compare snapshots conservatively; missing evidence never proves resolution."""
    current_catalysts = event_items(current.get("catalysts"))
    current_risks = event_items(current.get("risks"))
    previous_catalysts = event_items((previous or {}).get("catalysts"))
    previous_risks = event_items((previous or {}).get("risks"))
    first_observation = previous is None

    prev_cat = {item["fingerprint"] for item in previous_catalysts}
    prev_risk = {item["fingerprint"] for item in previous_risks}
    new_catalysts = [item for item in current_catalysts if item["fingerprint"] not in prev_cat]
    new_risks = [item for item in current_risks if item["fingerprint"] not in prev_risk]

    if first_observation:
        state = "baseline"
        new_catalysts = []
        new_risks = []
    elif new_risks:
        state = "new_risk"
    elif new_catalysts:
        state = "new_catalyst"
    else:
        state = "unchanged"

    return {
        "state": state,
        "first_observation": first_observation,
        "new_catalysts": new_catalysts,
        "new_risks": new_risks,
        "catalysts": current_catalysts,
        "risks": current_risks,
        "resolved_or_missing": [],
        "evidence_present": bool(current_catalysts or current_risks or current.get("news_evidence")),
    }
