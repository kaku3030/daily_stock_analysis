"""Data shapes for the Futu/Moomoo provider-semantics harness.

This module is deliberately isolated from `src/` and `data_provider/`.
Nothing in production imports from here, and nothing here imports from
production. It exists purely to give raw-evidence recording and
semantic-result reporting a stable, typed shape.

Two shapes only, by design:

- ``RawEvent`` / ``raw_event()``: one row of unmodified provider evidence.
  Every field the SDK/callback exposed is kept -- no field is dropped for
  looking irrelevant, and no interpretation is applied.
- ``SemanticTestResult`` / ``TestStatus``: the *separate* interpretation
  layer. A result never contains raw SDK objects; it only ever points at
  raw evidence files by path, and its ``status`` is restricted to the four
  values the harness is allowed to self-assign. Escalating a result beyond
  ``PARTIALLY_VERIFIED`` requires evidence a short harness run is unlikely
  to produce; the harness must not talk itself into ``VERIFIED``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping, Sequence

# Keys that must never appear with a real value in any evidence file. This
# is a defensive scrub, not a claim that the harness ever handles trading
# credentials -- Wave 1 is quote/market-data only.
_SECRET_KEY_PATTERN = re.compile(
    r"(token|password|passwd|secret|api[_-]?key|rsa|private[_-]?key|access[_-]?key)",
    re.IGNORECASE,
)
_REDACTED = "<redacted-by-harness>"


def scrub_secrets(value: Any) -> Any:
    """Recursively redact values under obviously secret-shaped keys.

    Never raises on unknown types -- unknown/unserializable leaf values are
    coerced with ``repr`` by the JSONL encoder, not here.
    """

    if isinstance(value, Mapping):
        return {
            key: (_REDACTED if _SECRET_KEY_PATTERN.search(str(key)) else scrub_secrets(item))
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [scrub_secrets(item) for item in value]
    return value


class TestStatus(str, Enum):
    VERIFIED = "VERIFIED"
    PARTIALLY_VERIFIED = "PARTIALLY_VERIFIED"
    UNRESOLVED = "UNRESOLVED"
    CONFLICTING = "CONFLICTING"


def raw_event(
    *,
    observed_at_utc: str,
    monotonic_ns: int,
    thread_id: int,
    event_seq_local: int,
    provider: str,
    market: str | None,
    symbol: str | None,
    stream_type: str,
    event_type: str,
    raw_sdk_ret: Any = None,
    raw_sdk_err_text: str | None = None,
    raw_payload: Any = None,
) -> dict:
    """Build one raw-evidence record. Every field below is always present,
    even when ``None`` -- a present-but-null field is distinguishable from a
    field the recorder forgot to populate, which matters when this file is
    read back for adjudication later.
    """

    return {
        "observed_at_utc": observed_at_utc,
        "monotonic_ns": monotonic_ns,
        "thread_id": thread_id,
        "event_seq_local": event_seq_local,
        "provider": provider,
        "market": market,
        "symbol": symbol,
        "stream_type": stream_type,
        "event_type": event_type,
        "raw_sdk_ret": raw_sdk_ret,
        "raw_sdk_err_text": raw_sdk_err_text,
        "raw_payload": scrub_secrets(raw_payload),
    }


@dataclass(frozen=True)
class SemanticTestResult:
    test_id: str
    provider: str
    sdk_version: str
    opend_version: str | None
    started_at_utc: str
    ended_at_utc: str
    market: str | None
    symbol: str | None
    stream_type: str | None
    precondition: str
    action: str
    raw_evidence_paths: Sequence[str]
    status: TestStatus
    observations: Sequence[str]
    limitations: Sequence[str]
    implementation_consequence: str
    extra: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.status, TestStatus):
            raise ValueError(f"status must be a TestStatus, got {self.status!r}")
        if not self.test_id:
            raise ValueError("test_id must not be empty")
        if not self.raw_evidence_paths:
            raise ValueError(
                f"{self.test_id}: a SemanticTestResult must reference at least one raw "
                f"evidence path -- interpretation without a pointer to raw evidence is "
                f"exactly what this harness exists to prevent"
            )

    def to_dict(self) -> dict:
        return {
            "test_id": self.test_id,
            "provider": self.provider,
            "sdk_version": self.sdk_version,
            "opend_version": self.opend_version,
            "started_at_utc": self.started_at_utc,
            "ended_at_utc": self.ended_at_utc,
            "market": self.market,
            "symbol": self.symbol,
            "stream_type": self.stream_type,
            "precondition": self.precondition,
            "action": self.action,
            "raw_evidence_paths": list(self.raw_evidence_paths),
            "semantic_result": {
                "status": self.status.value,
                "observations": list(self.observations),
                "limitations": list(self.limitations),
                "implementation_consequence": self.implementation_consequence,
            },
            "extra": dict(scrub_secrets(self.extra)),
        }
