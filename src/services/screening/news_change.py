# -*- coding: utf-8 -*-
"""Deterministic normalization and change detection for research event evidence."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from typing import Any

_TOKEN_RE = re.compile(r"[a-z0-9]+|[\u3400-\u9fff]+")
_STOP_WORDS = {
    "a", "an", "and", "are", "as", "at", "be", "continues", "for", "in",
    "is", "of", "on", "remains", "the", "to", "with",
}
_HIGH_RISK_TERMS = {
    "bankruptcy", "criminal", "default", "doj", "fraud", "investigation",
    "lawsuit", "recall", "sanction", "subpoena",
    "刑事", "欺诈", "调查", "破产", "制裁", "召回",
}
_MEDIUM_RISK_TERMS = {
    "delay", "downgrade", "export", "restriction", "shortage", "warning",
    "下调", "延期", "短缺", "警告", "限制",
}


def normalize_text(value: Any) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).casefold()
    tokens = [token for token in _TOKEN_RE.findall(text) if token not in _STOP_WORDS]
    return " ".join(sorted(set(tokens)))


def text_fingerprint(value: Any) -> str:
    normalized = normalize_text(value)
    if not normalized:
        return ""
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:24]


def build_event_snapshot(candidate: dict[str, Any]) -> dict[str, Any]:
    catalysts = _fact_rows(candidate.get("llm_catalysts"))
    risks = _fact_rows(candidate.get("llm_risks"))
    news = _news_rows(candidate.get("dsa_news"))
    return {
        "catalysts": catalysts,
        "risks": risks,
        "news_evidence": news,
        "fingerprints": {
            "catalysts": [row["fingerprint"] for row in catalysts],
            "risks": [row["fingerprint"] for row in risks],
            "news_evidence": [row["fingerprint"] for row in news],
        },
    }


def compare_event_snapshots(
    previous: dict[str, Any] | None,
    current: dict[str, Any],
) -> dict[str, Any]:
    if not previous:
        return {
            "state": "unchanged",
            "baseline": True,
            "events": [],
            "new_catalysts": [],
            "new_risks": [],
            "resolved_or_missing": [],
            "news_evidence": current.get("news_evidence") or [],
            "attention": "none",
        }

    previous_catalysts = _by_fingerprint(previous.get("catalysts"))
    previous_risks = _by_fingerprint(previous.get("risks"))
    current_catalysts = _by_fingerprint(current.get("catalysts"))
    current_risks = _by_fingerprint(current.get("risks"))

    new_catalysts = _new_rows(current_catalysts, previous_catalysts, "new_catalyst")
    new_risks = _new_rows(current_risks, previous_risks, "new_risk", risk=True)
    missing = _missing_rows(previous_catalysts, current_catalysts, "catalyst")
    missing.extend(_missing_rows(previous_risks, current_risks, "risk"))
    events = [*new_catalysts, *new_risks, *missing]
    if new_risks:
        attention = "high" if any(row["severity"] == "high" for row in new_risks) else "medium"
    elif new_catalysts or missing:
        attention = "low"
    else:
        attention = "none"
    return {
        "state": "unchanged" if not events else "changed",
        "baseline": False,
        "events": events,
        "new_catalysts": new_catalysts,
        "new_risks": new_risks,
        "resolved_or_missing": missing,
        "news_evidence": current.get("news_evidence") or [],
        "attention": attention,
    }


def _fact_rows(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in value:
        text = str(item or "").strip()
        fingerprint = text_fingerprint(text)
        if not text or not fingerprint or fingerprint in seen:
            continue
        rows.append({"text": text, "fingerprint": fingerprint})
        seen.add(fingerprint)
    return rows


def _news_rows(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in value:
        if isinstance(item, dict):
            title = str(item.get("title") or item.get("name") or item.get("summary") or "").strip()
            url = str(item.get("url") or item.get("link") or "").strip()
            source = str(item.get("source") or "").strip()
            published_at = str(item.get("published_at") or item.get("date") or "").strip()
        else:
            title, url, source, published_at = str(item or "").strip(), "", "", ""
        fingerprint = text_fingerprint(url or title)
        if not title or not fingerprint or fingerprint in seen:
            continue
        rows.append({
            "title": title,
            "url": url,
            "source": source,
            "published_at": published_at,
            "fingerprint": fingerprint,
        })
        seen.add(fingerprint)
    return rows


def _by_fingerprint(value: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(value, list):
        return {}
    return {
        str(row.get("fingerprint")): row
        for row in value
        if isinstance(row, dict) and row.get("fingerprint")
    }


def _new_rows(
    current: dict[str, dict[str, Any]],
    previous: dict[str, dict[str, Any]],
    event_type: str,
    *,
    risk: bool = False,
) -> list[dict[str, Any]]:
    rows = []
    for fingerprint in sorted(set(current) - set(previous)):
        text = str(current[fingerprint].get("text") or "")
        row = {"type": event_type, "text": text, "fingerprint": fingerprint}
        if risk:
            row["severity"] = _risk_severity(text)
        rows.append(row)
    return rows


def _missing_rows(
    previous: dict[str, dict[str, Any]],
    current: dict[str, dict[str, Any]],
    category: str,
) -> list[dict[str, str]]:
    return [
        {
            "type": "resolved_or_missing",
            "category": category,
            "text": str(previous[fingerprint].get("text") or ""),
            "fingerprint": fingerprint,
        }
        for fingerprint in sorted(set(previous) - set(current))
    ]


def _risk_severity(text: str) -> str:
    normalized = normalize_text(text)
    tokens = set(normalized.split())
    if tokens & _HIGH_RISK_TERMS or any(term in normalized for term in _HIGH_RISK_TERMS if len(term) > 1):
        return "high"
    if tokens & _MEDIUM_RISK_TERMS or any(term in normalized for term in _MEDIUM_RISK_TERMS if len(term) > 1):
        return "medium"
    return "low"

