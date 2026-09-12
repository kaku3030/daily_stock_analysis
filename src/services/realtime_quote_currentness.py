# -*- coding: utf-8 -*-
"""Fail-closed timestamp-currentness evidence for realtime quote consumers.

This module deliberately does not decide market/session liveness, delivery
entitlement, continuity, or final actionability.  It answers one narrower
question: is the provider timestamp evidence current enough under a max-age
policy supplied by the consumer?

Provider timestamps and upstream health fields are evidence.  Missing,
malformed, timezone-naive, stale, or implausibly future evidence is blocked
rather than silently treated as fresh.  ``fetched_at`` is intentionally not a
substitute for provider/source progress.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional


_ACCEPTED_DATA_QUALITY = frozenset({"ok", "partial"})


class QuoteCurrentnessStatus(str, Enum):
    FRESH = "FRESH"
    STALE_QUOTE_BLOCKED = "STALE_QUOTE_BLOCKED"
    DATA_UNHEALTHY = "DATA_UNHEALTHY"


@dataclass(frozen=True)
class QuoteCurrentnessDecision:
    """Timestamp-currentness evidence only; not final action authority."""

    currentness_passed: bool
    status: QuoteCurrentnessStatus
    reason: str
    provider_timestamp: Optional[datetime] = None
    age_seconds: Optional[float] = None
    max_age_seconds: int = 0
    source: Optional[str] = None
    data_quality: Optional[str] = None


def _read(quote: Any, field_name: str) -> Any:
    if quote is None:
        return None
    if isinstance(quote, dict):
        return quote.get(field_name)
    value = getattr(quote, field_name, None)
    if value is not None:
        return value
    to_dict = getattr(quote, "to_dict", None)
    if callable(to_dict):
        try:
            payload = to_dict()
        except Exception:
            return None
        if isinstance(payload, dict):
            return payload.get(field_name)
    return None


def _source_name(quote: Any) -> Optional[str]:
    source = _read(quote, "source")
    if source is None:
        return None
    value = getattr(source, "value", source)
    text = str(value).strip()
    return text or None


def _parse_aware_timestamp(value: Any) -> tuple[Optional[datetime], str]:
    if value in (None, ""):
        return None, "MISSING_PROVIDER_TIMESTAMP"

    if isinstance(value, datetime):
        parsed = value
    else:
        text = str(value).strip()
        if not text:
            return None, "MISSING_PROVIDER_TIMESTAMP"
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            return None, "INVALID_PROVIDER_TIMESTAMP"

    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None, "NAIVE_PROVIDER_TIMESTAMP"
    return parsed.astimezone(timezone.utc), ""


def _normalize_data_quality(quote: Any) -> tuple[Optional[str], str]:
    raw = _read(quote, "data_quality")
    if raw in (None, ""):
        return None, "MISSING_DATA_QUALITY"
    value = str(raw).strip().lower()
    if not value:
        return None, "MISSING_DATA_QUALITY"
    if value not in _ACCEPTED_DATA_QUALITY:
        return value, "DATA_QUALITY_NOT_ACCEPTED"
    return value, ""


def _normalize_stale_seconds(quote: Any) -> tuple[Optional[float], str]:
    raw = _read(quote, "stale_seconds")
    if raw is None:
        return None, ""
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None, "INVALID_UPSTREAM_STALE_SECONDS"
    if not math.isfinite(value) or value < 0:
        return None, "INVALID_UPSTREAM_STALE_SECONDS"
    return value, ""


def _normalize_stale_flag(quote: Any) -> tuple[Optional[bool], str]:
    raw = _read(quote, "is_stale")
    if raw is None:
        return None, ""
    if isinstance(raw, bool):
        return raw, ""
    return None, "INVALID_UPSTREAM_STALE_FLAG"


def evaluate_quote_currentness(
    quote: Any,
    *,
    max_age_seconds: int,
    now_utc: Optional[datetime] = None,
) -> QuoteCurrentnessDecision:
    """Evaluate quote timestamp-currentness under a caller-owned age policy.

    ``currentness_passed`` means only that this currentness gate passed.  It is
    not permission to alert, trade, or promote a feed to LIVE.  Delivery mode,
    entitlement, session expectation, broader Data Health, and Continuity stay
    separate gates.
    """

    max_age = int(max_age_seconds)
    if max_age <= 0:
        raise ValueError("max_age_seconds must be positive")
    source = _source_name(quote)

    if quote is None:
        return QuoteCurrentnessDecision(
            currentness_passed=False,
            status=QuoteCurrentnessStatus.DATA_UNHEALTHY,
            reason="MISSING_QUOTE",
            max_age_seconds=max_age,
            source=source,
        )

    data_quality, quality_reason = _normalize_data_quality(quote)
    if quality_reason:
        return QuoteCurrentnessDecision(
            currentness_passed=False,
            status=QuoteCurrentnessStatus.DATA_UNHEALTHY,
            reason=quality_reason,
            max_age_seconds=max_age,
            source=source,
            data_quality=data_quality,
        )

    provider_dt, parse_reason = _parse_aware_timestamp(
        _read(quote, "provider_timestamp")
    )
    if provider_dt is None:
        return QuoteCurrentnessDecision(
            currentness_passed=False,
            status=QuoteCurrentnessStatus.DATA_UNHEALTHY,
            reason=parse_reason,
            max_age_seconds=max_age,
            source=source,
            data_quality=data_quality,
        )

    now = now_utc or datetime.now(timezone.utc)
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now_utc must be timezone-aware")
    now = now.astimezone(timezone.utc)
    age_seconds = (now - provider_dt).total_seconds()

    if age_seconds < 0:
        return QuoteCurrentnessDecision(
            currentness_passed=False,
            status=QuoteCurrentnessStatus.DATA_UNHEALTHY,
            reason="PROVIDER_TIMESTAMP_IN_FUTURE",
            provider_timestamp=provider_dt,
            age_seconds=age_seconds,
            max_age_seconds=max_age,
            source=source,
            data_quality=data_quality,
        )

    stale_flag, stale_flag_reason = _normalize_stale_flag(quote)
    if stale_flag_reason:
        return QuoteCurrentnessDecision(
            currentness_passed=False,
            status=QuoteCurrentnessStatus.DATA_UNHEALTHY,
            reason=stale_flag_reason,
            provider_timestamp=provider_dt,
            age_seconds=age_seconds,
            max_age_seconds=max_age,
            source=source,
            data_quality=data_quality,
        )
    if stale_flag is True:
        return QuoteCurrentnessDecision(
            currentness_passed=False,
            status=QuoteCurrentnessStatus.STALE_QUOTE_BLOCKED,
            reason="UPSTREAM_STALE_FLAG",
            provider_timestamp=provider_dt,
            age_seconds=age_seconds,
            max_age_seconds=max_age,
            source=source,
            data_quality=data_quality,
        )

    stale_seconds_value, stale_seconds_reason = _normalize_stale_seconds(quote)
    if stale_seconds_reason:
        return QuoteCurrentnessDecision(
            currentness_passed=False,
            status=QuoteCurrentnessStatus.DATA_UNHEALTHY,
            reason=stale_seconds_reason,
            provider_timestamp=provider_dt,
            age_seconds=age_seconds,
            max_age_seconds=max_age,
            source=source,
            data_quality=data_quality,
        )
    if stale_seconds_value is not None and stale_seconds_value > max_age:
        return QuoteCurrentnessDecision(
            currentness_passed=False,
            status=QuoteCurrentnessStatus.STALE_QUOTE_BLOCKED,
            reason="UPSTREAM_STALE_SECONDS_EXCEEDED",
            provider_timestamp=provider_dt,
            age_seconds=age_seconds,
            max_age_seconds=max_age,
            source=source,
            data_quality=data_quality,
        )

    if age_seconds > max_age:
        return QuoteCurrentnessDecision(
            currentness_passed=False,
            status=QuoteCurrentnessStatus.STALE_QUOTE_BLOCKED,
            reason="PROVIDER_TIMESTAMP_TOO_OLD",
            provider_timestamp=provider_dt,
            age_seconds=age_seconds,
            max_age_seconds=max_age,
            source=source,
            data_quality=data_quality,
        )

    return QuoteCurrentnessDecision(
        currentness_passed=True,
        status=QuoteCurrentnessStatus.FRESH,
        reason="CURRENTNESS_OK",
        provider_timestamp=provider_dt,
        age_seconds=age_seconds,
        max_age_seconds=max_age,
        source=source,
        data_quality=data_quality,
    )
