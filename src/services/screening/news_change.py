# -*- coding: utf-8 -*-
"""Deterministic news/catalyst change detection for research candidates."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from difflib import SequenceMatcher
from typing import Any

_STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "has", "have",
    "in", "is", "it", "of", "on", "or", "that", "the", "to", "was", "were", "with",
    "remains", "remain", "continued", "continues", "continue", "still",
}
_WORD_RE = re.compile(r"[^\W_]+", re.UNICODE)


def normalize_event_text(value: Any) -> str:
    """Return a stable normalized form used only for research-event dedupe."""
    text = unicodedata.normalize("NFKC", str(value or "")).casefold()
    tokens = [token for token in _WORD_RE.findall(text) if token not in _STOPWORDS]
    return " ".join(tokens)


def event_fingerprint(value: Any) -> str:
    normalized = normalize_event_text(value)
    if not normalized:
        return ""
    canonical = " ".join(sorted(set(normalized.split())))
    return hashlib.sha1(canonical.encode("utf-8")).hexdigest()[:16]


def events_equivalent(left: Any, right: Any) -> bool:
    """Conservatively identify repeated/paraphrased event text."""
    left_norm = normalize_event_text(left)
    right_norm = normalize_event_text(right)
    if not left_norm or not right_norm:
        return False
    if left_norm == right_norm or event_fingerprint(left_norm) == event_fingerprint(right_norm):
        return True

    left_tokens = set(left_norm.split())
    right_tokens = set(right_norm.split())
    shared = left_tokens & right_tokens
    union = left_tokens | right_tokens
    if len(shared) >= 2 and union:
        jaccard = len(shared) / len(union)
        containment = len(shared) / min(len(left_tokens), len(right_tokens))
        if jaccard >= 0.60 or containment >= 0.80:
            return True

    # Keep this threshold high: SequenceMatcher is only a fallback for wording drift,
    # not a semantic classifier.
    return SequenceMatcher(None, left_norm, right_norm).ratio() >= 0.86


def build_event_evidence(pick: dict[str, Any]) -> dict[str, Any]:
    catalysts = _text_list(pick.get("llm_catalysts") or pick.get("catalysts"))
    risks = _text_list(pick.get("llm_risks") or pick.get("risks"))
    news = pick.get("dsa_news")
    news_items = news if isinstance(news, list) else []
    news_texts = _news_texts(news_items)
    return {
        "catalysts": catalysts,
        "risks": risks,
        "news": news_items[:20],
        "news_texts": news_texts[:20],
        "fingerprints": {
            "catalysts": [event_fingerprint(item) for item in catalysts if event_fingerprint(item)],
            "risks": [event_fingerprint(item) for item in risks if event_fingerprint(item)],
            "news": [event_fingerprint(item) for item in news_texts if event_fingerprint(item)],
        },
        "has_evidence": bool(catalysts or risks or news_texts),
    }


def compare_event_evidence(
    previous: dict[str, Any] | None,
    current: dict[str, Any],
) -> dict[str, Any]:
    """Compare adjacent event snapshots without turning absence into confirmed recovery."""
    current = current if isinstance(current, dict) else {}
    if previous is None:
        return {
            "state": "unchanged",
            "attention": "none",
            "material": False,
            "baseline": True,
            "resolution_confirmed": False,
            "new_catalysts": [],
            "new_risks": [],
            "missing_catalysts": [],
            "missing_risks": [],
        }

    previous = previous if isinstance(previous, dict) else {}
    previous_news = _text_list(previous.get("news_texts"))
    current_news = _text_list(current.get("news_texts"))

    previous_catalysts = _text_list(previous.get("catalysts"))
    previous_risks = _text_list(previous.get("risks"))
    current_catalysts = _text_list(current.get("catalysts"))
    current_risks = _text_list(current.get("risks"))

    new_catalysts = _unmatched(current_catalysts, previous_catalysts + previous_news)
    new_risks = _unmatched(current_risks, previous_risks + previous_news)
    missing_catalysts = _unmatched(previous_catalysts, current_catalysts + current_news)
    missing_risks = _unmatched(previous_risks, current_risks + current_news)

    if new_risks:
        state, attention, material = "new_risk", "high", True
    elif new_catalysts:
        state, attention, material = "new_catalyst", "medium", True
    elif missing_catalysts or missing_risks:
        # Missing evidence is deliberately not called a resolution. It is surfaced
        # for review but cannot generate a positive recovery signal by itself.
        state, attention, material = "resolved_or_missing", "low", False
    else:
        state, attention, material = "unchanged", "none", False

    return {
        "state": state,
        "attention": attention,
        "material": material,
        "baseline": False,
        "resolution_confirmed": False,
        "new_catalysts": new_catalysts,
        "new_risks": new_risks,
        "missing_catalysts": missing_catalysts,
        "missing_risks": missing_risks,
    }


def news_change_radar_markdown(rows: list[dict[str, Any]]) -> str:
    lines = [
        "# 美股新闻 / 催化剂变化雷达",
        "",
        "> 仅比较相邻研究快照中的新增与重复事件；缺失旧线索不会被自动解释为风险解除。",
        "",
        "| 股票 | 状态 | 关注度 | 新催化 | 新风险 | 缺失线索 |",
        "|---|---|---|---:|---:|---:|",
    ]
    if not rows:
        lines.append("| 暂无事件快照 | - | - | - | - | - |")
        return "\n".join(lines) + "\n"

    for row in rows:
        detail = row.get("detail") if isinstance(row.get("detail"), dict) else {}
        missing = len(detail.get("missing_catalysts") or []) + len(detail.get("missing_risks") or [])
        lines.append(
            f"| {row.get('code', '')} | {detail.get('state', 'unchanged')} | "
            f"{detail.get('attention', 'none')} | {len(detail.get('new_catalysts') or [])} | "
            f"{len(detail.get('new_risks') or [])} | {missing} |"
        )
    return "\n".join(lines) + "\n"


def _unmatched(current: list[str], prior: list[str]) -> list[str]:
    return [
        item
        for item in current
        if not any(events_equivalent(item, previous) for previous in prior)
    ]


def _text_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value:
        text = str(item or "").strip()
        if text and text not in result:
            result.append(text)
    return result


def _news_texts(items: list[Any]) -> list[str]:
    result: list[str] = []
    for item in items:
        if isinstance(item, dict):
            parts = []
            for key in ("title", "summary", "snippet", "content"):
                value = str(item.get(key) or "").strip()
                if value and value not in parts:
                    parts.append(value)
            text = " ".join(parts[:2]).strip()
        else:
            text = str(item or "").strip()
        if text and text not in result:
            result.append(text)
    return result
