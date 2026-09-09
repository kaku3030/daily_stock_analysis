# -*- coding: utf-8 -*-
"""Fail-closed currentness gate for actionable realtime quote consumers.

This module deliberately does not decide market/session liveness and does not
promote a feed to LIVE.  It answers one narrower question: is this individual
quote current enough to be used by an actionable realtime consumer such as a
price/percent alert?

Provider timestamps are evidence.  Missing, malformed, timezone-naive, stale,
or implausibly future timestamps are blocked rather than silently treated as
fresh.  This keeps Data Health as a hard gate while the broader Live Feed
Currentness/Continuity state machine is implemented separately.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional


DEFAULT_ACTIONABLE_QUOTE_MAX_AGE_SECONDS = 600
DEFAULT_MAX_FUTURE_SKEW_SECONDS = 5


class QuoteCurrentnessStatus(str, Enum):
    FRESH = "FRESH"
    STALE_QUOTE_BLOCKED = "STALE_QUOTE_BLOCKED"
    DATA_UNHEALTHY = "DATA_UNHEALTHY"


@dataclass(frozen=True)
class QuoteCurrentnessDecision:
    allowed: bool
    status: QuoteCurrentnessStatus
    reason: str
    provider_timestamp: Optional[datetime] = None
    age_seconds: Optional[float] = None
    max_age_seconds: int = DEFAULT_ACTIONABLE_QUOTE_MAX_AGE_SECONDS
    source: Optional[str] = None


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


def evaluate_actionable_quote_currentness(
    quote: Any,
    *,
    now_utc: Optional[datetime] = None,
    max_age_seconds: int = DEFAULT_ACTIONABLE_QUOTE_MAX_AGE_SECONDS,
    max_future_skew_seconds: int = DEFAULT_MAX_FUTURE_SKEW_SECONDS,
) -> QuoteCurrentnessDecision:
    """Return whether ``quote`` may be used by an actionable realtime rule.

    The contract is intentionally fail-closed.  A numeric price alone is never
    enough.  Callers should record ``status`` and ``reason`` when blocked.
    """

    max_age = max(1, int(max_age_seconds))
    max_future_skew = max(0, int(max_future_skew_seconds))
    source = _source_name(quote)

    if quote is None:
        return QuoteCurrentnessDecision(
            allowed=False,
            status=QuoteCurrentnessStatus.DATA_UNHEALTHY,
            reason="MISSING_QUOTE",
            max_age_seconds=max_age,
            source=source,
        )

    data_quality = str(_read(quote, "data_quality") or "").strip().lower()
    if data_quality == "unavailable":
        return QuoteCurrentnessDecision(
            allowed=False,
            status=QuoteCurrentnessStatus.DATA_UNHEALTHY,
            reason="DATA_QUALITY_UNAVAILABLE",
            max_age_seconds=max_age,
            source=source,
        )

    provider_dt, parse_reason = _parse_aware_timestamp(
        _read(quote, "provider_timestamp")
    )
    if provider_dt is None:
        return QuoteCurrentnessDecision(
            allowed=False,
            status=QuoteCurrentnessStatus.DATA_UNHEALTHY,
            reason=parse_reason,
            max_age_seconds=max_age,
            source=source,
        )

    now = now_utc or datetime.now(timezone.utc)
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now_utc must be timezone-aware")
    now = now.astimezone(timezone.utc)
    age_seconds = (now - provider_dt).total_seconds()

    if age_seconds < -max_future_skew:
        return QuoteCurrentnessDecision(
            allowed=False,
            status=QuoteCurrentnessStatus.DATA_UNHEALTHY,
            reason="PROVIDER_TIMESTAMP_IN_FUTURE",
            provider_timestamp=provider_dt,
            age_seconds=age_seconds,
            max_age_seconds=max_age,
            source=source,
        )

    if bool(_read(quote, "is_stale")):
        return QuoteCurrentnessDecision(
            allowed=False,
            status=QuoteCurrentnessStatus.STALE_QUOTE_BLOCKED,
            reason="UPSTREAM_STALE_FLAG",
            provider_timestamp=provider_dt,
            age_seconds=age_seconds,
            max_age_seconds=max_age,
            source=source,
        )

    stale_seconds = _read(quote, "stale_seconds")
    try:
        stale_seconds_value = float(stale_seconds) if stale_seconds is not None else None
    except (TypeError, ValueError):
        stale_seconds_value = None
    if stale_seconds_value is not None and stale_seconds_value > max_age:
        return QuoteCurrentnessDecision(
            allowed=False,
            status=QuoteCurrentnessStatus.STALE_QUOTE_BLOCKED,
            reason="UPSTREAM_STALE_SECONDS_EXCEEDED",
            provider_timestamp=provider_dt,
            age_seconds=age_seconds,
            max_age_seconds=max_age,
            source=source,
        )

    if age_seconds > max_age:
        return QuoteCurrentnessDecision(
            allowed=False,
            status=QuoteCurrentnessStatus.STALE_QUOTE_BLOCKED,
            reason="PROVIDER_TIMESTAMP_TOO_OLD",
            provider_timestamp=provider_dt,
            age_seconds=age_seconds,
            max_age_seconds=max_age,
            source=source,
        )

    return QuoteCurrentnessDecision(
        allowed=True,
        status=QuoteCurrentnessStatus.FRESH,
        reason="CURRENTNESS_OK",
        provider_timestamp=provider_dt,
        age_seconds=max(0.0, age_seconds),
        max_age_seconds=max_age,
        source=source,
    )
