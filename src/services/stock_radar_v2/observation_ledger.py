"""Append-only research observations and their latency provenance."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any, Mapping


class SourceEventAtQuality(StrEnum):
    EXACT = "EXACT"
    DERIVED = "DERIVED"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class LatencyTrace:
    source_event_at: float | None = None
    source_event_at_quality: SourceEventAtQuality = SourceEventAtQuality.UNKNOWN
    data_received_at: float | None = None
    knowledge_available_at: float | None = None
    detected_at: float | None = None
    strategy_decided_at: float | None = None
    risk_decided_at: float | None = None
    execution_ready_at: float | None = None
    order_sent_at: float | None = None
    fill_at: float | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.source_event_at_quality, SourceEventAtQuality):
            raise TypeError("source_event_at_quality must be a SourceEventAtQuality")
        values = [getattr(self, name) for name in _TIMESTAMP_FIELDS]
        present = [value for value in values if value is not None]
        if any(value < 0 for value in present) or any(a > b for a, b in zip(present, present[1:])):
            raise ValueError("latency timestamps must be non-negative and monotonic")
        if self.source_event_at_quality is SourceEventAtQuality.UNKNOWN and self.source_event_at is not None:
            raise ValueError("UNKNOWN source_event_at quality requires a missing source_event_at")
        if self.source_event_at_quality is not SourceEventAtQuality.UNKNOWN and self.source_event_at is None:
            raise ValueError("EXACT or DERIVED source_event_at quality requires source_event_at")

    def to_dict(self) -> dict[str, Any]:
        return {**asdict(self), "source_event_at_quality": self.source_event_at_quality.value}

    def system_latency(self) -> float | None:
        segments = (
            (self.data_received_at, self.knowledge_available_at),
            (self.strategy_decided_at, self.risk_decided_at),
            (self.risk_decided_at, self.execution_ready_at),
        )
        durations = [end - start for start, end in segments if start is not None and end is not None]
        return sum(durations) if durations else None

    def policy_wait(self) -> float | None:
        if self.knowledge_available_at is None or self.strategy_decided_at is None:
            return None
        return self.strategy_decided_at - self.knowledge_available_at

    def catalyst_latency(self) -> float | None:
        if self.source_event_at is None or self.detected_at is None:
            return None
        return self.detected_at - self.source_event_at


_TIMESTAMP_FIELDS = (
    "source_event_at",
    "data_received_at",
    "knowledge_available_at",
    "detected_at",
    "strategy_decided_at",
    "risk_decided_at",
    "execution_ready_at",
    "order_sent_at",
    "fill_at",
)


@dataclass(frozen=True)
class Observation:
    observation_id: str
    detector_status: str
    evidence_ids: tuple[str, ...] = ()
    strategy_gate_results: Mapping[str, str] = field(default_factory=dict)
    strategy_eligible: bool | None = None
    portfolio_admissible: bool | None = None
    portfolio_block_reasons: tuple[str, ...] = ()
    execution_feasible: bool | None = None
    execution_record_id: str | None = None
    interrupted_reason: str | None = None
    decision_available_at: float | None = None
    confirmed_at: float | None = None
    earliest_executable_at: float | None = None
    canonical_permission: str = "UNKNOWN"
    later_outcome_label: str | None = None
    censored: bool = False
    mfe: float | None = None
    mae: float | None = None
    universe_snapshot_id: str | None = None
    latency: LatencyTrace = field(default_factory=LatencyTrace)

    def __post_init__(self) -> None:
        known = [value for value in (self.decision_available_at, self.confirmed_at) if value is not None]
        if self.earliest_executable_at is not None and known:
            if self.earliest_executable_at < max(known):
                raise ValueError("earliest_executable_at cannot precede decision availability")

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["latency"] = self.latency.to_dict()
        value["evidence_ids"] = list(self.evidence_ids)
        value["portfolio_block_reasons"] = list(self.portfolio_block_reasons)
        return value

    def serialize(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


class ObservationLedger:
    """Small append-only ledger; identical replay keys are idempotent."""

    def __init__(self) -> None:
        self._records: dict[str, Observation] = {}

    def append(self, observation: Observation) -> Observation:
        previous = self._records.get(observation.observation_id)
        if previous is not None and previous.serialize() != observation.serialize():
            raise ValueError("observation replay conflicts with existing record")
        self._records.setdefault(observation.observation_id, observation)
        return self._records[observation.observation_id]

    def records(self) -> tuple[Observation, ...]:
        return tuple(self._records.values())
