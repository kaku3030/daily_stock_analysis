"""Strategy Lab V0.1 -- OOS Consumption Ledger domain layer.

Owns the consumption state model, the resolution model, the event kinds, the
public result/assessment dataclasses, and the deterministic semantic
fingerprints the repository persists. It answers "may this OOS window be
treated as pristine, and what has consumed it", never "is the strategy
profitable".

Pure compute, stdlib plus the two closed contracts it consumes
(``experiment_governance`` for manifests/lineage and ``temporal_contract``
for intervals and canonical UTC text). It does not touch SQLAlchemy, the
repository layer, or the database.

Frozen state model
------------------
``PRISTINE < CONSUMED < BURNED``. PRISTINE is never materialized as a
current-state row: absence of qualifying exposure *is* PRISTINE.
``CLAIMED_FOR_EVALUATION`` implies at least CONSUMED, ``OUTCOME_USED``
implies BURNED. Legal transitions are PRISTINE->CONSUMED,
PRISTINE->BURNED, CONSUMED->BURNED and self-loops; every downgrade is
forbidden and no reset/delete/unconsume/unburn API exists.

Consumption state and resolution are deliberately separate: an assessment
that cannot prove lineage completeness is ``INDETERMINATE + state=None``,
never a fake PRISTINE.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Mapping, Sequence

from .experiment_governance import ExperimentManifest
from .temporal_contract import TemporalInterval, canonical_utc_datetime, canonical_utc_text

_OPERATION_SCHEMA = "oos-ledger-operation-v0.1"
_LINEAGE_BINDING_SCHEMA = "oos-ledger-lineage-binding-v0.1"


def _require_identity(label: str, value: Any) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be a string, got {value!r}")
    if not value:
        raise ValueError(f"{label} must not be empty")
    if value != value.strip():
        raise ValueError(f"{label} must not have leading/trailing whitespace, got {value!r}")
    if not value.strip():
        raise ValueError(f"{label} must not be blank")
    return value


def _require_enum(label: str, value: Any, enum_type: type[Enum]) -> Any:
    if not isinstance(value, enum_type):
        raise ValueError(f"{label} must be a {enum_type.__name__} instance, got {value!r}")
    return value


def _canonical_encode(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, Mapping):
        return {
            _require_identity("canonical mapping key", key): _canonical_encode(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_canonical_encode(item) for item in value]
    raise ValueError(f"value of type {type(value).__name__!r} is not canonically encodable")


def _canonical_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(
        _canonical_encode(payload),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _sha256(payload: str) -> str:
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class OOSConsumptionState(str, Enum):
    """Frozen monotonic severity: PRISTINE < CONSUMED < BURNED."""

    PRISTINE = "pristine"
    CONSUMED = "consumed"
    BURNED = "burned"

    @property
    def severity_rank(self) -> int:
        return _STATE_SEVERITY_RANK[self]


_STATE_SEVERITY_RANK = {
    OOSConsumptionState.PRISTINE: 0,
    OOSConsumptionState.CONSUMED: 1,
    OOSConsumptionState.BURNED: 2,
}


class OOSConsumptionResolution(str, Enum):
    """Whether the ledger is entitled to state a consumption state at all."""

    RESOLVED = "resolved"
    INDETERMINATE = "indeterminate"
    CONFLICT = "conflict"


class OOSConsumptionEventKind(str, Enum):
    """Append-only event vocabulary. Never a reset/downgrade marker."""

    CLAIMED_FOR_EVALUATION = "claimed_for_evaluation"
    OUTCOME_USED = "outcome_used"

    @property
    def implied_state(self) -> OOSConsumptionState:
        return _EVENT_KIND_STATE[self]


_EVENT_KIND_STATE = {
    OOSConsumptionEventKind.CLAIMED_FOR_EVALUATION: OOSConsumptionState.CONSUMED,
    OOSConsumptionEventKind.OUTCOME_USED: OOSConsumptionState.BURNED,
}


class OOSClaimStatus(str, Enum):
    CLAIMED = "claimed"
    IDEMPOTENT_REPLAY = "idempotent_replay"
    ALREADY_EXPOSED = "already_exposed"
    LINEAGE_INDETERMINATE = "lineage_indeterminate"
    LINEAGE_VIOLATION = "lineage_violation"


class OOSBurnStatus(str, Enum):
    """Burn writes are fail-closed: only structural lineage violations block
    recording known pollution; incomplete ancestry never blocks it."""

    BURNED = "burned"
    IDEMPOTENT_REPLAY = "idempotent_replay"
    LINEAGE_VIOLATION = "lineage_violation"


class OOSLedgerIdentityConflictError(Exception):
    """A persistent identity definition was contradicted. Not a new version."""


class OOSLedgerIdempotencyConflictError(Exception):
    """Same operation_id replayed with a different semantic payload."""


@dataclass(frozen=True)
class OOSConsumptionAssessment:
    resolution: OOSConsumptionResolution
    state: OOSConsumptionState | None
    overlapping_event_ids: tuple[int, ...]
    lineage_experiment_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_enum("resolution", self.resolution, OOSConsumptionResolution)
        if self.state is not None:
            _require_enum("state", self.state, OOSConsumptionState)
        if self.resolution is OOSConsumptionResolution.RESOLVED:
            if self.state is None:
                raise ValueError("a RESOLVED assessment must carry a consumption state")
        elif self.state is not None:
            raise ValueError(
                f"{self.resolution.value} assessment must carry state=None, got {self.state!r}"
            )
        for event_id in self.overlapping_event_ids:
            if isinstance(event_id, bool) or not isinstance(event_id, int) or event_id <= 0:
                raise ValueError(
                    f"overlapping_event_ids must be positive ints, got {event_id!r}"
                )
        for experiment_id in self.lineage_experiment_ids:
            _require_identity("lineage experiment_id", experiment_id)
        object.__setattr__(
            self, "overlapping_event_ids", tuple(sorted(self.overlapping_event_ids))
        )
        object.__setattr__(
            self, "lineage_experiment_ids", tuple(sorted(self.lineage_experiment_ids))
        )


@dataclass(frozen=True)
class OOSClaimResult:
    operation_id: str
    status: OOSClaimStatus
    assessment: OOSConsumptionAssessment | None = None
    event_id: int | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "operation_id", _require_identity("operation_id", self.operation_id))
        _require_enum("status", self.status, OOSClaimStatus)
        if self.assessment is not None and not isinstance(self.assessment, OOSConsumptionAssessment):
            raise ValueError(f"assessment must be an OOSConsumptionAssessment, got {self.assessment!r}")
        if self.event_id is not None:
            if isinstance(self.event_id, bool) or not isinstance(self.event_id, int) or self.event_id <= 0:
                raise ValueError(f"event_id must be a positive int or None, got {self.event_id!r}")


@dataclass(frozen=True)
class OOSLedgerWriteResult:
    operation_id: str
    status: OOSBurnStatus
    event_id: int | None = None
    assessment: OOSConsumptionAssessment | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "operation_id", _require_identity("operation_id", self.operation_id))
        _require_enum("status", self.status, OOSBurnStatus)
        if self.event_id is not None:
            if isinstance(self.event_id, bool) or not isinstance(self.event_id, int) or self.event_id <= 0:
                raise ValueError(f"event_id must be a positive int or None, got {self.event_id!r}")
        if self.assessment is not None and not isinstance(self.assessment, OOSConsumptionAssessment):
            raise ValueError(f"assessment must be an OOSConsumptionAssessment, got {self.assessment!r}")


@dataclass(frozen=True)
class OOSConsumptionEvent:
    """Read-side view of one append-only ledger event.

    Added beyond the minimal frozen type list because the repository must
    expose events with aware-UTC datetimes and TemporalIntervals rather than
    raw ORM rows, keeping naive datetimes off the repository/domain boundary.
    """

    event_id: int
    operation_id: str
    experiment_id: str
    manifest_hash: str
    root_experiment_id: str
    lineage_binding_fingerprint: str
    event_kind: OOSConsumptionEventKind
    oos_interval: TemporalInterval
    declared_occurred_at: datetime
    recorded_at: datetime

    def __post_init__(self) -> None:
        if isinstance(self.event_id, bool) or not isinstance(self.event_id, int) or self.event_id <= 0:
            raise ValueError(f"event_id must be a positive int, got {self.event_id!r}")
        object.__setattr__(self, "operation_id", _require_identity("operation_id", self.operation_id))
        object.__setattr__(self, "experiment_id", _require_identity("experiment_id", self.experiment_id))
        object.__setattr__(self, "manifest_hash", _require_identity("manifest_hash", self.manifest_hash))
        object.__setattr__(
            self, "root_experiment_id", _require_identity("root_experiment_id", self.root_experiment_id)
        )
        object.__setattr__(
            self,
            "lineage_binding_fingerprint",
            _require_identity("lineage_binding_fingerprint", self.lineage_binding_fingerprint),
        )
        _require_enum("event_kind", self.event_kind, OOSConsumptionEventKind)
        if not isinstance(self.oos_interval, TemporalInterval):
            raise ValueError(f"oos_interval must be a TemporalInterval, got {self.oos_interval!r}")
        object.__setattr__(
            self, "declared_occurred_at", canonical_utc_datetime(self.declared_occurred_at)
        )
        object.__setattr__(self, "recorded_at", canonical_utc_datetime(self.recorded_at))


def parse_aware_utc_text(value: str) -> datetime:
    """Restore the canonical UTC TEXT the repository persisted as an aware
    UTC datetime. A naive result (or malformed text) raises instead of
    leaking a naive datetime across the repository/domain boundary.
    """

    text = _require_identity("utc text", value)
    return canonical_utc_datetime(datetime.fromisoformat(text))


def derive_state(kinds: Sequence[OOSConsumptionEventKind]) -> OOSConsumptionState:
    """Max severity over qualifying exposure events. Order-invariant."""

    for kind in kinds:
        _require_enum("event kind", kind, OOSConsumptionEventKind)
    if any(kind is OOSConsumptionEventKind.OUTCOME_USED for kind in kinds):
        return OOSConsumptionState.BURNED
    if any(kind is OOSConsumptionEventKind.CLAIMED_FOR_EVALUATION for kind in kinds):
        return OOSConsumptionState.CONSUMED
    return OOSConsumptionState.PRISTINE


def intervals_overlap(
    start_a: datetime, end_a: datetime, start_b: datetime, end_b: datetime
) -> bool:
    """Half-open overlap: [A,B) and [B,C) are adjacent, not overlapping."""

    return start_a < end_b and start_b < end_a


@dataclass(frozen=True)
class TargetLineage:
    """Resolution of the target-reachable ancestry chain.

    Only nodes on the target -> parent -> ... -> root path are reachable;
    every other co-supplied manifest is unrelated and must be ignored by the
    ledger entirely (registration, fingerprinting, inheritance). ``conflict``
    is True when the reachable chain itself is unusable: conflicting
    duplicate definitions for a reachable id, a self-parent, a cycle, or a
    broken root invariant. ``missing_ancestor_experiment_id`` names the first
    reachable parent that is absent from the supplied manifests (None when
    the chain reaches a root).
    """

    reachable: tuple[ExperimentManifest, ...]
    missing_ancestor_experiment_id: str | None
    conflict: bool


def resolve_target_lineage(
    target_manifest: ExperimentManifest,
    lineage_history: Sequence[ExperimentManifest],
) -> TargetLineage:
    """Walk target -> parent -> root over the supplied definitions only.

    Unrelated supplied nodes never appear in the result. Exact duplicate
    definitions collapse; conflicting definitions for a reachable id, a
    self-parent, a cycle, or a broken root invariant all produce
    ``conflict=True`` (the ledger then treats the lineage as a violation).
    """

    if not isinstance(target_manifest, ExperimentManifest):
        raise ValueError(f"target_manifest must be an ExperimentManifest, got {target_manifest!r}")
    by_id: dict[str, list[ExperimentManifest]] = {}
    for manifest in (target_manifest, *lineage_history):
        if not isinstance(manifest, ExperimentManifest):
            raise ValueError(
                f"lineage_history must contain only ExperimentManifest, got {manifest!r}"
            )
        by_id.setdefault(manifest.experiment_id, []).append(manifest)

    def unique_definition(experiment_id: str) -> ExperimentManifest | None:
        definitions = by_id.get(experiment_id)
        if not definitions:
            return None
        distinct = {
            (d.manifest_hash, d.parent_experiment_id, d.root_experiment_id)
            for d in definitions
        }
        return None if len(distinct) > 1 else definitions[0]

    def definitions_ambiguous(experiment_id: str) -> bool:
        definitions = by_id.get(experiment_id)
        if not definitions:
            return False
        distinct = {
            (d.manifest_hash, d.parent_experiment_id, d.root_experiment_id)
            for d in definitions
        }
        return len(distinct) > 1

    reachable: list[ExperimentManifest] = []
    visited: set[str] = set()
    conflict = False
    missing: str | None = None
    current_id = target_manifest.experiment_id

    while True:
        if current_id in visited:
            conflict = True  # cycle inside the reachable chain
            break
        visited.add(current_id)
        manifest = unique_definition(current_id)
        if manifest is None:
            conflict = True  # conflicting duplicate definitions for a reachable id
            break
        if manifest.parent_experiment_id is None:
            if manifest.root_experiment_id != manifest.experiment_id:
                conflict = True  # root node must declare itself as its own root
                break
            reachable.append(manifest)
            break
        if manifest.parent_experiment_id == manifest.experiment_id:
            conflict = True  # self-parent
            break
        if manifest.root_experiment_id == manifest.experiment_id:
            conflict = True  # child must not declare itself as its own root
            break
        parent_defs = by_id.get(manifest.parent_experiment_id)
        if not parent_defs:
            reachable.append(manifest)
            missing = manifest.parent_experiment_id
            break
        if definitions_ambiguous(manifest.parent_experiment_id):
            conflict = True  # conflicting duplicate definitions for a reachable parent
            break
        parent = parent_defs[0]
        if parent.root_experiment_id != manifest.root_experiment_id:
            conflict = True  # child/root mismatch along the reachable chain
            break
        reachable.append(manifest)
        current_id = manifest.parent_experiment_id

    return TargetLineage(
        reachable=tuple(reachable),
        missing_ancestor_experiment_id=missing,
        conflict=conflict,
    )


def compute_lineage_binding_fingerprint(manifests: Sequence[ExperimentManifest]) -> str:
    """Canonical set digest of the supplied (already target-reachable) lineage
    definitions, sorted by experiment_id, so the binding never depends on
    input order. Exact duplicate definitions collapse; conflicting
    definitions for the same experiment_id are a hard error here (the ledger
    resolves them to a lineage violation before fingerprinting).
    """

    by_id: dict[str, tuple[str, str | None, str]] = {}
    for manifest in manifests:
        if not isinstance(manifest, ExperimentManifest):
            raise ValueError(f"manifests must contain only ExperimentManifest, got {manifest!r}")
        definition = (
            manifest.manifest_hash,
            manifest.parent_experiment_id,
            manifest.root_experiment_id,
        )
        existing = by_id.get(manifest.experiment_id)
        if existing is not None and existing != definition:
            raise ValueError(
                f"conflicting duplicate definitions supplied for experiment_id "
                f"{manifest.experiment_id!r}"
            )
        by_id[manifest.experiment_id] = definition

    rows: list[dict[str, Any]] = [
        {
            "experiment_id": experiment_id,
            "manifest_hash": definition[0],
            "parent_experiment_id": definition[1],
            "root_experiment_id": definition[2],
        }
        for experiment_id, definition in sorted(by_id.items())
    ]
    payload = {"schema": _LINEAGE_BINDING_SCHEMA, "lineage": rows}
    return _sha256(_canonical_json(payload))


def compute_operation_fingerprint(
    *,
    event_kind: OOSConsumptionEventKind,
    experiment_id: str,
    manifest_hash: str,
    parent_experiment_id: str | None,
    root_experiment_id: str,
    oos_start: datetime,
    oos_end: datetime,
    declared_occurred_at: datetime,
    lineage_binding_fingerprint: str,
) -> str:
    """Semantic fingerprint of one ledger operation. Deliberately excludes
    ``operation_id``: the id selects the idempotency slot, the fingerprint
    proves the payload did not change underneath it.
    """

    _require_enum("event_kind", event_kind, OOSConsumptionEventKind)
    _require_identity("experiment_id", experiment_id)
    _require_identity("manifest_hash", manifest_hash)
    if parent_experiment_id is not None:
        _require_identity("parent_experiment_id", parent_experiment_id)
    _require_identity("root_experiment_id", root_experiment_id)
    _require_identity("lineage_binding_fingerprint", lineage_binding_fingerprint)
    payload = {
        "schema": _OPERATION_SCHEMA,
        "event_kind": event_kind.value,
        "experiment_id": experiment_id,
        "manifest_hash": manifest_hash,
        "parent_experiment_id": parent_experiment_id,
        "root_experiment_id": root_experiment_id,
        "oos_start": canonical_utc_text(oos_start),
        "oos_end": canonical_utc_text(oos_end),
        "declared_occurred_at": canonical_utc_text(declared_occurred_at),
        "lineage_binding_fingerprint": lineage_binding_fingerprint,
    }
    return _sha256(_canonical_json(payload))
