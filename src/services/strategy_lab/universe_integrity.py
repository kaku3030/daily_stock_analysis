"""Strategy Lab V0.1 -- Universe Integrity Foundation.

Owns point-in-time (PIT) universe membership, instrument lifecycle, and
classification history reconstruction: given a set of causally-timestamped
facts (anchors and events), what did a subject's state actually look like at
some historical instant, as knowable by some (possibly later) decision time --
and how confident can we be that we have seen *all* the facts that could have
changed that answer.

It answers "what was true, and do we know we have the complete picture",
never "what should the strategy do about it".

Pure compute, stdlib only, and a leaf within the package: depends on nothing
but ``src.services.strategy_lab.temporal_contract`` and the standard library.
It does not own ticker aliasing, security-master identity resolution,
provider timestamp parsing, trading calendar/session logic, source trust
ranking, persistence, Walk-Forward verdicts, index methodology, or taxonomy
mapping -- callers hand this module already-resolved, opaque identity strings
and already-parsed, already-aware datetimes.

The PIT fact model
-------------------
Every domain (membership, lifecycle, classification) is expressed as an
**anchor** plus a stream of **events**, both timestamped with the Temporal
Contract's ``effective_at``/``available_at`` pair -- reused here exactly as
``TemporalEvidence``/``is_available_by`` define it, with no additional
ordering constraint between the two instants.

An **anchor** is a complete, absolute state assertion at one instant: for
membership, the *entire* member set at ``effective_at``, not a delta; for
lifecycle and classification, the subject's absolute state. An **event** is
also an absolute assertion -- ``MEMBER``/``NON_MEMBER``, ``LISTED``/
``NOT_LISTED``, or a full ``ClassificationValue`` -- never an add/remove
command and never a delta to fold sequentially. Because every fact is
absolute, reconstruction never needs to replay history in order: only the
single latest-effective, latest-visible revision for a subject ever matters.

Visibility is filtered before effective-group selection
----------------------------------------------------------
For both anchors and events, an item is *visible* when
``available_at <= decision_time``. Selection always filters to visible items
**first**, then picks the highest ``effective_at`` among what remains, then
(within that effective-time group) the latest-visible-``available_at``
subgroup. A later-effective item that is entirely invisible must never mask
an earlier-effective item that *is* visible -- an invisible revision simply
does not exist yet, from the decision-maker's point of view, and the search
for "what is the latest thing I can see" continues to the next-lower
effective time exactly as if the invisible item were absent.

Anchor selection (exact precedence)
------------------------------------
Eligible anchors (``effective_at <= as_of``) are grouped by ``effective_at``;
for each group, only the latest-*visible* revision subgroup (max
``available_at`` among visible members) is inspected, and exact duplicates
within that subgroup collapse before any conflict check. A subgroup
containing more than one distinct value is an ``ANCHOR_CONFLICT`` for that
group. Among all eligible groups that have at least one visible anchor, the
**highest-effective** group is selected -- regardless of whether it resolves
or conflicts. An older resolved group can never be used to bypass a
later-effective conflict, but a later-effective resolved group can supersede
an earlier conflicting one. If the winning group conflicts, or if no eligible
group has any visible anchor at all, there is no selected anchor:
``ANCHOR_CONFLICT`` -> ``CONFLICT``; ``NO_VISIBLE_ANCHOR`` -> ``INDETERMINATE``.

Anchor-boundary events are checked, never applied
--------------------------------------------------
For the selected anchor at instant ``A``, an event with
``effective_at == A`` is neither ignored nor applied as a state change --
doing either would require inventing a precedence between two structurally
different record types (an anchor's complete baseline versus an event's
incremental assertion) that this design deliberately does not define. Instead
each such "boundary" subject's latest-visible revision subgroup is resolved
exactly like an anchor group (collapse duplicates, detect internal
contradiction), then *compared* against the anchor's own implied value for
that subject: agreement is a harmless confirmation, disagreement is an
``ANCHOR_EVENT_CONFLICT``, and internal contradiction within the boundary
subgroup itself is an ``EVENT_CONFLICT`` (checked first, before any
comparison to the anchor). A correction to the anchor's own value at ``A``
must be expressed as a new anchor revision -- same ``effective_at``, later
``available_at`` -- never as a same-instant event.

Normal event reconstruction
----------------------------
Only events with ``selected_anchor.effective_at < event.effective_at <=
as_of`` participate at all. Per subject, candidates are filtered to visible
items (``available_at <= decision_time``) **first**; only the maximum
``effective_at`` among the *visible* candidates is then selected, and the
full group at that effective time (visible and invisible members alike) is
handed to the same latest-visible-subgroup resolution used everywhere else --
so a same-instant invisible revision cannot silently suppress an otherwise
valid visible one. Internal contradiction is an ``EVENT_CONFLICT``. A
resolved value overrides the anchor's value for that subject.

Coverage is positive-only, anchored at the selected anchor
------------------------------------------------------------
A ``*CoverageCertificate`` is a caller-supplied assertion that "the exact
event slice ``[coverage_start, coverage_end)`` for this scope, fingerprinted
as X, is complete" -- it carries no ``available_at``, no ``complete`` flag,
and no source/revision metadata, because those would let a certificate assert
its own trustworthiness rather than being verified. Every certificate is
independently re-fingerprinted from the facts actually in hand and compared
against ``certified_event_slice_fingerprint``; a wrong scope or a mismatched
fingerprint makes the whole certificate unusable and increments a diagnostic
counter, without poisoning any other, otherwise-sufficient valid certificate.

Coverage is required exactly when ``as_of > selected_anchor.effective_at``;
when ``as_of == selected_anchor.effective_at`` the anchor is itself a
complete baseline and no certificate is needed at all -- but
``required_start``/``required_through`` are still populated (both equal to
that instant), since they describe the window in question regardless of
whether it happens to be empty. When required, the merged valid interval
that contains ``A`` (not the globally furthest merged interval -- an
unrelated, later, disconnected certificate proves nothing about the gap
between ``A`` and ``as_of``) must extend *strictly* past ``as_of``;
``coverage_end == as_of`` is insufficient by construction, since event
eligibility for reconstruction is defined as ``effective_at <= as_of`` and a
certificate ending exactly at ``as_of`` cannot certify events *at* ``as_of``
were seen.

Event-slice fingerprints
--------------------------
``compute_*_event_slice_fingerprint`` are narrow, deterministic SHA-256
digests over exactly: the frozen schema tag
``"universe-integrity-event-slice-v0.1"``, the domain, the exact scope
identity, the coverage window, and every event (never the anchor) whose
``effective_at`` falls in ``[coverage_start, coverage_end)`` -- including
each event's own ``available_at``, so a late-arriving correction inside an
already-certified window invalidates that certificate. Each event is encoded
as its actual named semantic fields (never an undocumented positional row
with placeholder slots). Exact semantic duplicates collapse before hashing
and input order never matters; a change strictly outside the window never
changes the fingerprint. These helpers only compute a binding digest -- they
never certify that a slice is complete, and never consult decision time.

Identity is opaque
--------------------
``instrument_id``, ``universe_id``, ``taxonomy_id``, and ``classification_id``
are exact-match opaque strings: non-empty, non-blank, with no leading or
trailing whitespace, never normalized, aliased, or coerced. A raw string is
never accepted where an enum member is required.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Mapping, Sequence, TypeVar

from .temporal_contract import (
    TemporalEvidence,
    TemporalInterval,
    canonical_utc_datetime,
    canonical_utc_text,
    is_available_by,
)

_EVENT_SLICE_SCHEMA = "universe-integrity-event-slice-v0.1"


class UniverseIntegrityResolutionStatus(str, Enum):
    """Distinct from -- and never aliased with -- information_dependency's
    ResolutionStatus. This module does not import that module at all.
    """

    RESOLVED = "resolved"
    INDETERMINATE = "indeterminate"
    CONFLICT = "conflict"


class MembershipState(str, Enum):
    MEMBER = "member"
    NON_MEMBER = "non_member"


class LifecycleState(str, Enum):
    LISTED = "listed"
    NOT_LISTED = "not_listed"


class ClassificationState(str, Enum):
    CLASSIFIED = "classified"
    UNCLASSIFIED = "unclassified"
    NOT_APPLICABLE = "not_applicable"


class IntegrityFindingCode(str, Enum):
    NO_VISIBLE_ANCHOR = "no_visible_anchor"
    ANCHOR_CONFLICT = "anchor_conflict"
    ANCHOR_EVENT_CONFLICT = "anchor_event_conflict"
    COVERAGE_NOT_CERTIFIED = "coverage_not_certified"
    COVERAGE_GAP = "coverage_gap"
    COVERAGE_BOUNDARY_NOT_REACHED = "coverage_boundary_not_reached"
    EVENT_CONFLICT = "event_conflict"


_CONFLICT_CODES = frozenset(
    {
        IntegrityFindingCode.ANCHOR_CONFLICT,
        IntegrityFindingCode.ANCHOR_EVENT_CONFLICT,
        IntegrityFindingCode.EVENT_CONFLICT,
    }
)
_INDETERMINATE_CODES = frozenset(
    {
        IntegrityFindingCode.NO_VISIBLE_ANCHOR,
        IntegrityFindingCode.COVERAGE_NOT_CERTIFIED,
        IntegrityFindingCode.COVERAGE_GAP,
        IntegrityFindingCode.COVERAGE_BOUNDARY_NOT_REACHED,
    }
)

# Primary sort order for canonical finding ordering -- see module docstring.
_FINDING_CODE_ORDER = {
    IntegrityFindingCode.ANCHOR_CONFLICT: 0,
    IntegrityFindingCode.ANCHOR_EVENT_CONFLICT: 1,
    IntegrityFindingCode.EVENT_CONFLICT: 2,
    IntegrityFindingCode.NO_VISIBLE_ANCHOR: 3,
    IntegrityFindingCode.COVERAGE_NOT_CERTIFIED: 4,
    IntegrityFindingCode.COVERAGE_GAP: 5,
    IntegrityFindingCode.COVERAGE_BOUNDARY_NOT_REACHED: 6,
}

T = TypeVar("T")


# --------------------------------------------------------------------------
# Validation primitives
# --------------------------------------------------------------------------


def _require_identity(label: str, value: Any) -> str:
    """Opaque exact-match identity: non-empty, non-blank, no surrounding
    whitespace, no normalization, no coercion.
    """

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


def _require_tuple(label: str, value: Any, element_type: type) -> tuple:
    if not isinstance(value, tuple):
        raise ValueError(f"{label} must be a tuple, got {type(value).__name__!r}")
    for item in value:
        if not isinstance(item, element_type):
            raise ValueError(
                f"{label} must contain only {element_type.__name__} instances, got {item!r}"
            )
    return value


def _is_visible(effective_at: datetime, available_at: datetime, decision_time: datetime) -> bool:
    """Genuine reuse of the Temporal Contract's own causality primitive."""

    return is_available_by(
        TemporalEvidence(effective_at=effective_at, available_at=available_at), decision_time
    )


def _none_safe_sort_key(row: Sequence[Any]) -> tuple:
    """Total order over a row that may contain None (e.g. classification_id),
    without ever comparing None to a string directly.
    """

    return tuple((0, "") if value is None else (1, value) for value in row)


# --------------------------------------------------------------------------
# Canonicalization (narrow, local -- not a general JSON framework)
# --------------------------------------------------------------------------


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


# --------------------------------------------------------------------------
# Membership fact model
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class UniverseMembershipAnchor:
    """A complete, absolute member set for one universe at one instant."""

    universe_id: str
    members: frozenset[str]
    effective_at: datetime
    available_at: datetime

    def __post_init__(self) -> None:
        object.__setattr__(self, "universe_id", _require_identity("universe_id", self.universe_id))
        if not isinstance(self.members, frozenset):
            raise ValueError(f"members must be a frozenset, got {self.members!r}")
        for instrument_id in self.members:
            _require_identity("member instrument_id", instrument_id)
        object.__setattr__(
            self, "effective_at", canonical_utc_datetime(self.effective_at)
        )
        object.__setattr__(
            self, "available_at", canonical_utc_datetime(self.available_at)
        )


@dataclass(frozen=True)
class UniverseMembershipEvent:
    """An absolute membership assertion for one instrument at one instant --
    never an add/remove command.
    """

    universe_id: str
    instrument_id: str
    state: MembershipState
    effective_at: datetime
    available_at: datetime

    def __post_init__(self) -> None:
        object.__setattr__(self, "universe_id", _require_identity("universe_id", self.universe_id))
        object.__setattr__(
            self, "instrument_id", _require_identity("instrument_id", self.instrument_id)
        )
        _require_enum("state", self.state, MembershipState)
        object.__setattr__(
            self, "effective_at", canonical_utc_datetime(self.effective_at)
        )
        object.__setattr__(
            self, "available_at", canonical_utc_datetime(self.available_at)
        )


@dataclass(frozen=True)
class UniverseMembershipFacts:
    """A scope-coherent bundle of membership anchors and events for one
    universe. Constructor-level fail-fast: every contained anchor/event must
    share this exact ``universe_id``, or construction raises.
    """

    universe_id: str
    anchors: tuple[UniverseMembershipAnchor, ...]
    events: tuple[UniverseMembershipEvent, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "universe_id", _require_identity("universe_id", self.universe_id))
        _require_tuple("anchors", self.anchors, UniverseMembershipAnchor)
        _require_tuple("events", self.events, UniverseMembershipEvent)
        for anchor in self.anchors:
            if anchor.universe_id != self.universe_id:
                raise ValueError(
                    f"anchor universe_id {anchor.universe_id!r} does not match facts "
                    f"universe_id {self.universe_id!r}"
                )
        for event in self.events:
            if event.universe_id != self.universe_id:
                raise ValueError(
                    f"event universe_id {event.universe_id!r} does not match facts "
                    f"universe_id {self.universe_id!r}"
                )


# --------------------------------------------------------------------------
# Lifecycle fact model
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class InstrumentLifecycleAnchor:
    instrument_id: str
    state: LifecycleState
    effective_at: datetime
    available_at: datetime

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "instrument_id", _require_identity("instrument_id", self.instrument_id)
        )
        _require_enum("state", self.state, LifecycleState)
        object.__setattr__(
            self, "effective_at", canonical_utc_datetime(self.effective_at)
        )
        object.__setattr__(
            self, "available_at", canonical_utc_datetime(self.available_at)
        )


@dataclass(frozen=True)
class InstrumentLifecycleEvent:
    instrument_id: str
    state: LifecycleState
    effective_at: datetime
    available_at: datetime

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "instrument_id", _require_identity("instrument_id", self.instrument_id)
        )
        _require_enum("state", self.state, LifecycleState)
        object.__setattr__(
            self, "effective_at", canonical_utc_datetime(self.effective_at)
        )
        object.__setattr__(
            self, "available_at", canonical_utc_datetime(self.available_at)
        )


@dataclass(frozen=True)
class InstrumentLifecycleFacts:
    instrument_id: str
    anchors: tuple[InstrumentLifecycleAnchor, ...]
    events: tuple[InstrumentLifecycleEvent, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "instrument_id", _require_identity("instrument_id", self.instrument_id)
        )
        _require_tuple("anchors", self.anchors, InstrumentLifecycleAnchor)
        _require_tuple("events", self.events, InstrumentLifecycleEvent)
        for anchor in self.anchors:
            if anchor.instrument_id != self.instrument_id:
                raise ValueError(
                    f"anchor instrument_id {anchor.instrument_id!r} does not match facts "
                    f"instrument_id {self.instrument_id!r}"
                )
        for event in self.events:
            if event.instrument_id != self.instrument_id:
                raise ValueError(
                    f"event instrument_id {event.instrument_id!r} does not match facts "
                    f"instrument_id {self.instrument_id!r}"
                )


# --------------------------------------------------------------------------
# Classification fact model
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class ClassificationValue:
    """``classification_id is not None`` iff ``state is CLASSIFIED``."""

    state: ClassificationState
    classification_id: str | None = None

    def __post_init__(self) -> None:
        _require_enum("state", self.state, ClassificationState)
        if self.state is ClassificationState.CLASSIFIED:
            if self.classification_id is None:
                raise ValueError("CLASSIFIED requires a classification_id")
            object.__setattr__(
                self,
                "classification_id",
                _require_identity("classification_id", self.classification_id),
            )
        else:
            if self.classification_id is not None:
                raise ValueError(
                    f"{self.state.value} must not carry a classification_id"
                )


@dataclass(frozen=True)
class ClassificationAnchor:
    instrument_id: str
    taxonomy_id: str
    value: ClassificationValue
    effective_at: datetime
    available_at: datetime

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "instrument_id", _require_identity("instrument_id", self.instrument_id)
        )
        object.__setattr__(self, "taxonomy_id", _require_identity("taxonomy_id", self.taxonomy_id))
        if not isinstance(self.value, ClassificationValue):
            raise ValueError(f"value must be a ClassificationValue instance, got {self.value!r}")
        object.__setattr__(
            self, "effective_at", canonical_utc_datetime(self.effective_at)
        )
        object.__setattr__(
            self, "available_at", canonical_utc_datetime(self.available_at)
        )


@dataclass(frozen=True)
class ClassificationEvent:
    instrument_id: str
    taxonomy_id: str
    value: ClassificationValue
    effective_at: datetime
    available_at: datetime

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "instrument_id", _require_identity("instrument_id", self.instrument_id)
        )
        object.__setattr__(self, "taxonomy_id", _require_identity("taxonomy_id", self.taxonomy_id))
        if not isinstance(self.value, ClassificationValue):
            raise ValueError(f"value must be a ClassificationValue instance, got {self.value!r}")
        object.__setattr__(
            self, "effective_at", canonical_utc_datetime(self.effective_at)
        )
        object.__setattr__(
            self, "available_at", canonical_utc_datetime(self.available_at)
        )


@dataclass(frozen=True)
class ClassificationFacts:
    instrument_id: str
    taxonomy_id: str
    anchors: tuple[ClassificationAnchor, ...]
    events: tuple[ClassificationEvent, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "instrument_id", _require_identity("instrument_id", self.instrument_id)
        )
        object.__setattr__(self, "taxonomy_id", _require_identity("taxonomy_id", self.taxonomy_id))
        _require_tuple("anchors", self.anchors, ClassificationAnchor)
        _require_tuple("events", self.events, ClassificationEvent)
        for anchor in self.anchors:
            if anchor.instrument_id != self.instrument_id or anchor.taxonomy_id != self.taxonomy_id:
                raise ValueError(
                    f"anchor scope ({anchor.instrument_id!r}, {anchor.taxonomy_id!r}) does not "
                    f"match facts scope ({self.instrument_id!r}, {self.taxonomy_id!r})"
                )
        for event in self.events:
            if event.instrument_id != self.instrument_id or event.taxonomy_id != self.taxonomy_id:
                raise ValueError(
                    f"event scope ({event.instrument_id!r}, {event.taxonomy_id!r}) does not "
                    f"match facts scope ({self.instrument_id!r}, {self.taxonomy_id!r})"
                )


# --------------------------------------------------------------------------
# Coverage certificates and diagnostics
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class UniverseMembershipCoverageCertificate:
    universe_id: str
    coverage_start: datetime
    coverage_end: datetime
    certified_event_slice_fingerprint: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "universe_id", _require_identity("universe_id", self.universe_id))
        _canonicalize_coverage_window(self)
        _require_identity(
            "certified_event_slice_fingerprint", self.certified_event_slice_fingerprint
        )


@dataclass(frozen=True)
class InstrumentLifecycleCoverageCertificate:
    instrument_id: str
    coverage_start: datetime
    coverage_end: datetime
    certified_event_slice_fingerprint: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "instrument_id", _require_identity("instrument_id", self.instrument_id)
        )
        _canonicalize_coverage_window(self)
        _require_identity(
            "certified_event_slice_fingerprint", self.certified_event_slice_fingerprint
        )


@dataclass(frozen=True)
class ClassificationCoverageCertificate:
    instrument_id: str
    taxonomy_id: str
    coverage_start: datetime
    coverage_end: datetime
    certified_event_slice_fingerprint: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "instrument_id", _require_identity("instrument_id", self.instrument_id)
        )
        object.__setattr__(self, "taxonomy_id", _require_identity("taxonomy_id", self.taxonomy_id))
        _canonicalize_coverage_window(self)
        _require_identity(
            "certified_event_slice_fingerprint", self.certified_event_slice_fingerprint
        )


def _canonicalize_coverage_window(certificate: Any) -> None:
    start = canonical_utc_datetime(certificate.coverage_start)
    end = canonical_utc_datetime(certificate.coverage_end)
    if not start < end:
        raise ValueError(f"coverage_start must be strictly before coverage_end ({start!r} >= {end!r})")
    object.__setattr__(certificate, "coverage_start", start)
    object.__setattr__(certificate, "coverage_end", end)


@dataclass(frozen=True)
class CoverageDiagnostics:
    """Positive-only coverage evidence: the detailed, structured source of
    truth behind a coverage-related ``IntegrityFinding``.

    ``required_start``/``required_through`` are always populated datetimes,
    even when ``required`` is ``False`` -- they describe the window in
    question regardless of whether that window happens to be empty
    (``as_of == selected_anchor.effective_at``).
    """

    required: bool
    satisfied: bool
    required_start: datetime
    required_through: datetime
    valid_certificate_count: int
    scope_mismatch_count: int
    fingerprint_mismatch_count: int
    merged_intervals: tuple[TemporalInterval, ...]
    furthest_contiguous_end: datetime | None

    def __post_init__(self) -> None:
        if not isinstance(self.required, bool):
            raise ValueError(f"required must be a bool, got {self.required!r}")
        if not isinstance(self.satisfied, bool):
            raise ValueError(f"satisfied must be a bool, got {self.satisfied!r}")
        for label, value in (
            ("valid_certificate_count", self.valid_certificate_count),
            ("scope_mismatch_count", self.scope_mismatch_count),
            ("fingerprint_mismatch_count", self.fingerprint_mismatch_count),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{label} must be a non-negative int, got {value!r}")
        for interval in self.merged_intervals:
            if not isinstance(interval, TemporalInterval):
                raise ValueError(
                    f"merged_intervals must contain only TemporalInterval instances, "
                    f"got {interval!r}"
                )

        required_start = canonical_utc_datetime(self.required_start)
        required_through = canonical_utc_datetime(self.required_through)
        object.__setattr__(self, "required_start", required_start)
        object.__setattr__(self, "required_through", required_through)

        if self.required:
            if not required_start < required_through:
                raise ValueError("required coverage must have required_start < required_through")
            if self.furthest_contiguous_end is not None:
                object.__setattr__(
                    self, "furthest_contiguous_end", canonical_utc_datetime(self.furthest_contiguous_end)
                )
        else:
            if required_start != required_through:
                raise ValueError(
                    "non-required coverage must have required_start == required_through"
                )
            if self.furthest_contiguous_end is not None:
                raise ValueError("non-required coverage must not declare furthest_contiguous_end")

        derived_satisfied = (not self.required) or (
            self.furthest_contiguous_end is not None
            and self.furthest_contiguous_end > self.required_through
        )
        if self.satisfied is not derived_satisfied:
            raise ValueError(
                f"satisfied={self.satisfied!r} does not match the derived value "
                f"{derived_satisfied!r} for the given required/furthest_contiguous_end/"
                f"required_through"
            )


# --------------------------------------------------------------------------
# Event-slice fingerprints
# --------------------------------------------------------------------------


def compute_universe_membership_event_slice_fingerprint(
    *,
    universe_id: str,
    coverage_start: datetime,
    coverage_end: datetime,
    events: Sequence[UniverseMembershipEvent],
) -> str:
    universe_id = _require_identity("universe_id", universe_id)
    start = canonical_utc_datetime(coverage_start)
    end = canonical_utc_datetime(coverage_end)
    if not start < end:
        raise ValueError(f"coverage_start must be strictly before coverage_end ({start!r} >= {end!r})")

    rows: set[tuple[str, str, str, str]] = set()
    for event in events:
        if not isinstance(event, UniverseMembershipEvent):
            raise ValueError(f"events must contain only UniverseMembershipEvent, got {event!r}")
        if event.universe_id != universe_id:
            raise ValueError(
                f"event universe_id {event.universe_id!r} does not match scope {universe_id!r}"
            )
        if start <= event.effective_at < end:
            rows.add(
                (
                    event.instrument_id,
                    canonical_utc_text(event.effective_at),
                    canonical_utc_text(event.available_at),
                    event.state.value,
                )
            )

    ordered_rows = sorted(rows, key=_none_safe_sort_key)
    events_payload = [
        {
            "instrument_id": row[0],
            "effective_at": row[1],
            "available_at": row[2],
            "state": row[3],
        }
        for row in ordered_rows
    ]
    return _event_slice_fingerprint(
        domain="universe_membership",
        scope={"universe_id": universe_id},
        start=start,
        end=end,
        events_payload=events_payload,
    )


def compute_instrument_lifecycle_event_slice_fingerprint(
    *,
    instrument_id: str,
    coverage_start: datetime,
    coverage_end: datetime,
    events: Sequence[InstrumentLifecycleEvent],
) -> str:
    instrument_id = _require_identity("instrument_id", instrument_id)
    start = canonical_utc_datetime(coverage_start)
    end = canonical_utc_datetime(coverage_end)
    if not start < end:
        raise ValueError(f"coverage_start must be strictly before coverage_end ({start!r} >= {end!r})")

    rows: set[tuple[str, str, str, str]] = set()
    for event in events:
        if not isinstance(event, InstrumentLifecycleEvent):
            raise ValueError(f"events must contain only InstrumentLifecycleEvent, got {event!r}")
        if event.instrument_id != instrument_id:
            raise ValueError(
                f"event instrument_id {event.instrument_id!r} does not match scope {instrument_id!r}"
            )
        if start <= event.effective_at < end:
            rows.add(
                (
                    instrument_id,
                    canonical_utc_text(event.effective_at),
                    canonical_utc_text(event.available_at),
                    event.state.value,
                )
            )

    ordered_rows = sorted(rows, key=_none_safe_sort_key)
    events_payload = [
        {
            "instrument_id": row[0],
            "effective_at": row[1],
            "available_at": row[2],
            "state": row[3],
        }
        for row in ordered_rows
    ]
    return _event_slice_fingerprint(
        domain="instrument_lifecycle",
        scope={"instrument_id": instrument_id},
        start=start,
        end=end,
        events_payload=events_payload,
    )


def compute_classification_event_slice_fingerprint(
    *,
    instrument_id: str,
    taxonomy_id: str,
    coverage_start: datetime,
    coverage_end: datetime,
    events: Sequence[ClassificationEvent],
) -> str:
    instrument_id = _require_identity("instrument_id", instrument_id)
    taxonomy_id = _require_identity("taxonomy_id", taxonomy_id)
    start = canonical_utc_datetime(coverage_start)
    end = canonical_utc_datetime(coverage_end)
    if not start < end:
        raise ValueError(f"coverage_start must be strictly before coverage_end ({start!r} >= {end!r})")

    rows: set[tuple[str, str, str, str, str, str | None]] = set()
    for event in events:
        if not isinstance(event, ClassificationEvent):
            raise ValueError(f"events must contain only ClassificationEvent, got {event!r}")
        if event.instrument_id != instrument_id or event.taxonomy_id != taxonomy_id:
            raise ValueError(
                f"event scope ({event.instrument_id!r}, {event.taxonomy_id!r}) does not match "
                f"scope ({instrument_id!r}, {taxonomy_id!r})"
            )
        if start <= event.effective_at < end:
            rows.add(
                (
                    instrument_id,
                    taxonomy_id,
                    canonical_utc_text(event.effective_at),
                    canonical_utc_text(event.available_at),
                    event.value.state.value,
                    event.value.classification_id,
                )
            )

    ordered_rows = sorted(rows, key=_none_safe_sort_key)
    events_payload = [
        {
            "instrument_id": row[0],
            "taxonomy_id": row[1],
            "effective_at": row[2],
            "available_at": row[3],
            "classification_state": row[4],
            "classification_id": row[5],
        }
        for row in ordered_rows
    ]
    return _event_slice_fingerprint(
        domain="classification",
        scope={"instrument_id": instrument_id, "taxonomy_id": taxonomy_id},
        start=start,
        end=end,
        events_payload=events_payload,
    )


def _event_slice_fingerprint(
    *,
    domain: str,
    scope: Mapping[str, str],
    start: datetime,
    end: datetime,
    events_payload: list[dict[str, Any]],
) -> str:
    payload = {
        "schema": _EVENT_SLICE_SCHEMA,
        "domain": domain,
        "scope": dict(scope),
        "coverage_start": canonical_utc_text(start),
        "coverage_end": canonical_utc_text(end),
        "events": events_payload,
    }
    return _sha256(_canonical_json(payload))


# --------------------------------------------------------------------------
# Findings
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class IntegrityFinding:
    code: IntegrityFindingCode
    subject_id: str | None
    effective_at: datetime | None
    available_at: datetime | None

    def __post_init__(self) -> None:
        _require_enum("code", self.code, IntegrityFindingCode)
        if self.subject_id is not None:
            object.__setattr__(self, "subject_id", _require_identity("subject_id", self.subject_id))
        if self.effective_at is not None:
            object.__setattr__(self, "effective_at", canonical_utc_datetime(self.effective_at))
        if self.available_at is not None:
            object.__setattr__(self, "available_at", canonical_utc_datetime(self.available_at))


def _finding_sort_key(
    finding: IntegrityFinding,
) -> tuple[int, tuple[int, str], tuple[int, str], tuple[int, str]]:
    def _rank_str(value: str | None) -> tuple[int, str]:
        return (0, "") if value is None else (1, value)

    def _rank_dt(value: datetime | None) -> tuple[int, str]:
        return (0, "") if value is None else (1, value.isoformat(timespec="microseconds"))

    return (
        _FINDING_CODE_ORDER[finding.code],
        _rank_str(finding.subject_id),
        _rank_dt(finding.effective_at),
        _rank_dt(finding.available_at),
    )


def _derive_status(
    findings: Sequence[IntegrityFinding],
) -> UniverseIntegrityResolutionStatus:
    codes = {finding.code for finding in findings}
    if codes & _CONFLICT_CODES:
        return UniverseIntegrityResolutionStatus.CONFLICT
    if codes & _INDETERMINATE_CODES:
        return UniverseIntegrityResolutionStatus.INDETERMINATE
    return UniverseIntegrityResolutionStatus.RESOLVED


# --------------------------------------------------------------------------
# Shared revision-resolution primitive
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class _RevisionOutcome:
    value: Any | None
    conflicted: bool
    latest_available_at: datetime | None


def _resolve_latest_revision(
    items: Sequence[T],
    *,
    available_at_of: Callable[[T], datetime],
    value_of: Callable[[T], Any],
    decision_time: datetime,
) -> _RevisionOutcome:
    """Latest-visible-subgroup resolution: the one primitive shared by anchor
    selection, boundary-event resolution, and normal-event resolution. Every
    item passed in is assumed to already share the scope/effective_at this
    outcome is being computed for.
    """

    visible = [item for item in items if available_at_of(item) <= decision_time]
    if not visible:
        return _RevisionOutcome(value=None, conflicted=False, latest_available_at=None)
    max_available_at = max(available_at_of(item) for item in visible)
    latest = [item for item in visible if available_at_of(item) == max_available_at]
    distinct_values = {value_of(item) for item in latest}
    if len(distinct_values) > 1:
        return _RevisionOutcome(value=None, conflicted=True, latest_available_at=max_available_at)
    return _RevisionOutcome(
        value=next(iter(distinct_values)), conflicted=False, latest_available_at=max_available_at
    )


def _latest_visible_effective_group(
    items: Sequence[T],
    *,
    effective_at_of: Callable[[T], datetime],
    available_at_of: Callable[[T], datetime],
    decision_time: datetime,
) -> list[T]:
    """Filter to visible items first, then return the full group (visible and
    invisible members alike) at the highest effective_at among the visible
    ones. An entirely-invisible later-effective group can never suppress an
    earlier-effective group that does have a visible member -- this is the
    only function that decides "what is the latest thing I can see", and it
    is used identically for anchors and for normal-event reconstruction.
    """

    visible = [item for item in items if available_at_of(item) <= decision_time]
    if not visible:
        return []
    max_effective_at = max(effective_at_of(item) for item in visible)
    return [item for item in items if effective_at_of(item) == max_effective_at]


def _merge_intervals(intervals: Sequence[TemporalInterval]) -> tuple[TemporalInterval, ...]:
    ordered = sorted(intervals, key=lambda interval: (interval.start, interval.end))
    merged: list[TemporalInterval] = []
    for interval in ordered:
        if merged and interval.start <= merged[-1].end:
            if interval.end > merged[-1].end:
                merged[-1] = TemporalInterval(merged[-1].start, interval.end)
        else:
            merged.append(interval)
    return tuple(merged)


def _evaluate_coverage(
    *,
    valid_intervals: Sequence[TemporalInterval],
    valid_certificate_count: int,
    scope_mismatch_count: int,
    fingerprint_mismatch_count: int,
    anchor_effective_at: datetime,
    as_of: datetime,
) -> CoverageDiagnostics:
    merged = _merge_intervals(valid_intervals)
    required = as_of > anchor_effective_at

    if not required:
        return CoverageDiagnostics(
            required=False,
            satisfied=True,
            required_start=anchor_effective_at,
            required_through=as_of,
            valid_certificate_count=valid_certificate_count,
            scope_mismatch_count=scope_mismatch_count,
            fingerprint_mismatch_count=fingerprint_mismatch_count,
            merged_intervals=merged,
            furthest_contiguous_end=None,
        )

    containing = next(
        (interval for interval in merged if interval.start <= anchor_effective_at < interval.end),
        None,
    )
    furthest = containing.end if containing is not None else None
    satisfied = furthest is not None and furthest > as_of

    return CoverageDiagnostics(
        required=True,
        satisfied=satisfied,
        required_start=anchor_effective_at,
        required_through=as_of,
        valid_certificate_count=valid_certificate_count,
        scope_mismatch_count=scope_mismatch_count,
        fingerprint_mismatch_count=fingerprint_mismatch_count,
        merged_intervals=merged,
        furthest_contiguous_end=furthest,
    )


def _coverage_finding_code(coverage: CoverageDiagnostics) -> IntegrityFindingCode | None:
    """The categorical reason a required, unsatisfied coverage failed --
    derived from CoverageDiagnostics, the structured source of truth.
    """

    if coverage.satisfied:
        return None
    if not coverage.merged_intervals:
        return IntegrityFindingCode.COVERAGE_NOT_CERTIFIED

    containing = next(
        (
            interval
            for interval in coverage.merged_intervals
            if interval.start <= coverage.required_start < interval.end
        ),
        None,
    )
    if containing is None:
        return IntegrityFindingCode.COVERAGE_GAP
    # A later, disconnected interval demonstrates an actual hole exists
    # between the containing interval and as_of, distinct from simply not
    # having certified far enough yet.
    if any(interval.start > containing.end for interval in coverage.merged_intervals):
        return IntegrityFindingCode.COVERAGE_GAP
    return IntegrityFindingCode.COVERAGE_BOUNDARY_NOT_REACHED


# --------------------------------------------------------------------------
# Membership resolution
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class UniverseMembershipResolution:
    status: UniverseIntegrityResolutionStatus
    universe_id: str
    as_of: datetime
    decision_time: datetime
    members: frozenset[str] | None
    selected_anchor: UniverseMembershipAnchor | None
    coverage: CoverageDiagnostics | None
    findings: tuple[IntegrityFinding, ...]

    def __post_init__(self) -> None:
        _require_enum("status", self.status, UniverseIntegrityResolutionStatus)
        object.__setattr__(self, "universe_id", _require_identity("universe_id", self.universe_id))
        object.__setattr__(self, "as_of", canonical_utc_datetime(self.as_of))
        object.__setattr__(self, "decision_time", canonical_utc_datetime(self.decision_time))
        for finding in self.findings:
            if not isinstance(finding, IntegrityFinding):
                raise ValueError(f"findings must contain only IntegrityFinding, got {finding!r}")
        object.__setattr__(self, "findings", tuple(sorted(self.findings, key=_finding_sort_key)))

        derived = _derive_status(self.findings)
        if self.status is not derived:
            raise ValueError(
                f"status {self.status.value!r} does not match finding-derived status "
                f"{derived.value!r}"
            )

        if self.status is UniverseIntegrityResolutionStatus.RESOLVED:
            if not isinstance(self.members, frozenset):
                raise ValueError("RESOLVED requires members to be a frozenset")
            if self.selected_anchor is None:
                raise ValueError("RESOLVED requires a selected_anchor")
            if self.findings:
                raise ValueError("RESOLVED must have no findings")
            if self.coverage is None or not self.coverage.satisfied:
                raise ValueError("RESOLVED requires satisfied coverage")
        else:
            if self.members is not None:
                raise ValueError("non-RESOLVED must have members=None")


def resolve_universe_membership(
    facts: UniverseMembershipFacts,
    *,
    as_of: datetime,
    decision_time: datetime,
    coverage_certificates: Sequence[UniverseMembershipCoverageCertificate] = (),
) -> UniverseMembershipResolution:
    if not isinstance(facts, UniverseMembershipFacts):
        raise ValueError(f"facts must be a UniverseMembershipFacts instance, got {facts!r}")
    canonical_as_of = canonical_utc_datetime(as_of)
    canonical_decision_time = canonical_utc_datetime(decision_time)

    findings: list[IntegrityFinding] = []

    eligible_anchors = [a for a in facts.anchors if a.effective_at <= canonical_as_of]
    by_effective: dict[datetime, list[UniverseMembershipAnchor]] = {}
    for anchor in eligible_anchors:
        by_effective.setdefault(anchor.effective_at, []).append(anchor)

    selected_effective_at: datetime | None = None
    selected_outcome: _RevisionOutcome | None = None
    for effective_at in sorted(by_effective, reverse=True):
        outcome = _resolve_latest_revision(
            by_effective[effective_at],
            available_at_of=lambda a: a.available_at,
            value_of=lambda a: a.members,
            decision_time=canonical_decision_time,
        )
        if outcome.latest_available_at is None:
            continue
        selected_effective_at = effective_at
        selected_outcome = outcome
        break

    if selected_outcome is None:
        findings.append(
            IntegrityFinding(
                code=IntegrityFindingCode.NO_VISIBLE_ANCHOR,
                subject_id=None,
                effective_at=None,
                available_at=None,
            )
        )
        return UniverseMembershipResolution(
            status=_derive_status(findings),
            universe_id=facts.universe_id,
            as_of=canonical_as_of,
            decision_time=canonical_decision_time,
            members=None,
            selected_anchor=None,
            coverage=None,
            findings=tuple(findings),
        )

    if selected_outcome.conflicted:
        findings.append(
            IntegrityFinding(
                code=IntegrityFindingCode.ANCHOR_CONFLICT,
                subject_id=None,
                effective_at=selected_effective_at,
                available_at=selected_outcome.latest_available_at,
            )
        )
        return UniverseMembershipResolution(
            status=_derive_status(findings),
            universe_id=facts.universe_id,
            as_of=canonical_as_of,
            decision_time=canonical_decision_time,
            members=None,
            selected_anchor=None,
            coverage=None,
            findings=tuple(findings),
        )

    selected_anchor = next(
        a
        for a in by_effective[selected_effective_at]
        if a.available_at == selected_outcome.latest_available_at
        and a.members == selected_outcome.value
    )
    anchor_members: set[str] = set(selected_anchor.members)

    # Anchor-boundary events: checked for consistency, never applied.
    boundary_events_by_subject: dict[str, list[UniverseMembershipEvent]] = {}
    for event in facts.events:
        if event.effective_at == selected_anchor.effective_at:
            boundary_events_by_subject.setdefault(event.instrument_id, []).append(event)

    for instrument_id in sorted(boundary_events_by_subject):
        outcome = _resolve_latest_revision(
            boundary_events_by_subject[instrument_id],
            available_at_of=lambda e: e.available_at,
            value_of=lambda e: e.state,
            decision_time=canonical_decision_time,
        )
        if outcome.latest_available_at is None:
            continue
        if outcome.conflicted:
            findings.append(
                IntegrityFinding(
                    code=IntegrityFindingCode.EVENT_CONFLICT,
                    subject_id=instrument_id,
                    effective_at=selected_anchor.effective_at,
                    available_at=outcome.latest_available_at,
                )
            )
            continue
        anchor_value = (
            MembershipState.MEMBER
            if instrument_id in selected_anchor.members
            else MembershipState.NON_MEMBER
        )
        if outcome.value is not anchor_value:
            findings.append(
                IntegrityFinding(
                    code=IntegrityFindingCode.ANCHOR_EVENT_CONFLICT,
                    subject_id=instrument_id,
                    effective_at=selected_anchor.effective_at,
                    available_at=max(selected_anchor.available_at, outcome.latest_available_at),
                )
            )

    # Normal event reconstruction: strictly after the anchor, up to as_of.
    # BLOCKER 1 fix: visibility is filtered before effective-group selection.
    normal_events_by_subject: dict[str, list[UniverseMembershipEvent]] = {}
    for event in facts.events:
        if selected_anchor.effective_at < event.effective_at <= canonical_as_of:
            normal_events_by_subject.setdefault(event.instrument_id, []).append(event)

    for instrument_id in sorted(normal_events_by_subject):
        group = _latest_visible_effective_group(
            normal_events_by_subject[instrument_id],
            effective_at_of=lambda e: e.effective_at,
            available_at_of=lambda e: e.available_at,
            decision_time=canonical_decision_time,
        )
        if not group:
            continue
        outcome = _resolve_latest_revision(
            group,
            available_at_of=lambda e: e.available_at,
            value_of=lambda e: e.state,
            decision_time=canonical_decision_time,
        )
        if outcome.latest_available_at is None:
            continue
        if outcome.conflicted:
            findings.append(
                IntegrityFinding(
                    code=IntegrityFindingCode.EVENT_CONFLICT,
                    subject_id=instrument_id,
                    effective_at=group[0].effective_at,
                    available_at=outcome.latest_available_at,
                )
            )
            continue
        if outcome.value is MembershipState.MEMBER:
            anchor_members.add(instrument_id)
        else:
            anchor_members.discard(instrument_id)

    coverage = _resolve_membership_coverage(
        facts=facts,
        certificates=coverage_certificates,
        anchor_effective_at=selected_anchor.effective_at,
        as_of=canonical_as_of,
    )
    coverage_code = _coverage_finding_code(coverage)
    if coverage_code is not None:
        findings.append(
            IntegrityFinding(
                code=coverage_code,
                subject_id=None,
                effective_at=None,
                available_at=None,
            )
        )

    status = _derive_status(findings)
    return UniverseMembershipResolution(
        status=status,
        universe_id=facts.universe_id,
        as_of=canonical_as_of,
        decision_time=canonical_decision_time,
        members=frozenset(anchor_members) if status is UniverseIntegrityResolutionStatus.RESOLVED else None,
        selected_anchor=selected_anchor,
        coverage=coverage,
        findings=tuple(findings),
    )


def _resolve_membership_coverage(
    *,
    facts: UniverseMembershipFacts,
    certificates: Sequence[UniverseMembershipCoverageCertificate],
    anchor_effective_at: datetime,
    as_of: datetime,
) -> CoverageDiagnostics:
    valid_intervals: list[TemporalInterval] = []
    valid_certificate_count = 0
    scope_mismatch_count = 0
    fingerprint_mismatch_count = 0

    for certificate in certificates:
        if certificate.universe_id != facts.universe_id:
            scope_mismatch_count += 1
            continue
        expected = compute_universe_membership_event_slice_fingerprint(
            universe_id=facts.universe_id,
            coverage_start=certificate.coverage_start,
            coverage_end=certificate.coverage_end,
            events=facts.events,
        )
        if expected != certificate.certified_event_slice_fingerprint:
            fingerprint_mismatch_count += 1
            continue
        valid_certificate_count += 1
        valid_intervals.append(TemporalInterval(certificate.coverage_start, certificate.coverage_end))

    return _evaluate_coverage(
        valid_intervals=valid_intervals,
        valid_certificate_count=valid_certificate_count,
        scope_mismatch_count=scope_mismatch_count,
        fingerprint_mismatch_count=fingerprint_mismatch_count,
        anchor_effective_at=anchor_effective_at,
        as_of=as_of,
    )


# --------------------------------------------------------------------------
# Lifecycle resolution
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class InstrumentLifecycleResolution:
    status: UniverseIntegrityResolutionStatus
    instrument_id: str
    as_of: datetime
    decision_time: datetime
    state: LifecycleState | None
    selected_anchor: InstrumentLifecycleAnchor | None
    coverage: CoverageDiagnostics | None
    findings: tuple[IntegrityFinding, ...]

    def __post_init__(self) -> None:
        _require_enum("status", self.status, UniverseIntegrityResolutionStatus)
        object.__setattr__(
            self, "instrument_id", _require_identity("instrument_id", self.instrument_id)
        )
        object.__setattr__(self, "as_of", canonical_utc_datetime(self.as_of))
        object.__setattr__(self, "decision_time", canonical_utc_datetime(self.decision_time))
        for finding in self.findings:
            if not isinstance(finding, IntegrityFinding):
                raise ValueError(f"findings must contain only IntegrityFinding, got {finding!r}")
        object.__setattr__(self, "findings", tuple(sorted(self.findings, key=_finding_sort_key)))

        derived = _derive_status(self.findings)
        if self.status is not derived:
            raise ValueError(
                f"status {self.status.value!r} does not match finding-derived status "
                f"{derived.value!r}"
            )

        if self.status is UniverseIntegrityResolutionStatus.RESOLVED:
            if not isinstance(self.state, LifecycleState):
                raise ValueError("RESOLVED requires a LifecycleState")
            if self.selected_anchor is None:
                raise ValueError("RESOLVED requires a selected_anchor")
            if self.findings:
                raise ValueError("RESOLVED must have no findings")
            if self.coverage is None or not self.coverage.satisfied:
                raise ValueError("RESOLVED requires satisfied coverage")
        else:
            if self.state is not None:
                raise ValueError("non-RESOLVED must have state=None")


def resolve_instrument_lifecycle(
    facts: InstrumentLifecycleFacts,
    *,
    as_of: datetime,
    decision_time: datetime,
    coverage_certificates: Sequence[InstrumentLifecycleCoverageCertificate] = (),
) -> InstrumentLifecycleResolution:
    if not isinstance(facts, InstrumentLifecycleFacts):
        raise ValueError(f"facts must be an InstrumentLifecycleFacts instance, got {facts!r}")
    canonical_as_of = canonical_utc_datetime(as_of)
    canonical_decision_time = canonical_utc_datetime(decision_time)

    findings: list[IntegrityFinding] = []

    eligible_anchors = [a for a in facts.anchors if a.effective_at <= canonical_as_of]
    by_effective: dict[datetime, list[InstrumentLifecycleAnchor]] = {}
    for anchor in eligible_anchors:
        by_effective.setdefault(anchor.effective_at, []).append(anchor)

    selected_effective_at: datetime | None = None
    selected_outcome: _RevisionOutcome | None = None
    for effective_at in sorted(by_effective, reverse=True):
        outcome = _resolve_latest_revision(
            by_effective[effective_at],
            available_at_of=lambda a: a.available_at,
            value_of=lambda a: a.state,
            decision_time=canonical_decision_time,
        )
        if outcome.latest_available_at is None:
            continue
        selected_effective_at = effective_at
        selected_outcome = outcome
        break

    if selected_outcome is None:
        findings.append(
            IntegrityFinding(
                code=IntegrityFindingCode.NO_VISIBLE_ANCHOR,
                subject_id=None,
                effective_at=None,
                available_at=None,
            )
        )
        return InstrumentLifecycleResolution(
            status=_derive_status(findings),
            instrument_id=facts.instrument_id,
            as_of=canonical_as_of,
            decision_time=canonical_decision_time,
            state=None,
            selected_anchor=None,
            coverage=None,
            findings=tuple(findings),
        )

    if selected_outcome.conflicted:
        findings.append(
            IntegrityFinding(
                code=IntegrityFindingCode.ANCHOR_CONFLICT,
                subject_id=None,
                effective_at=selected_effective_at,
                available_at=selected_outcome.latest_available_at,
            )
        )
        return InstrumentLifecycleResolution(
            status=_derive_status(findings),
            instrument_id=facts.instrument_id,
            as_of=canonical_as_of,
            decision_time=canonical_decision_time,
            state=None,
            selected_anchor=None,
            coverage=None,
            findings=tuple(findings),
        )

    selected_anchor = next(
        a
        for a in by_effective[selected_effective_at]
        if a.available_at == selected_outcome.latest_available_at and a.state == selected_outcome.value
    )
    resolved_state = selected_anchor.state

    boundary_events = [e for e in facts.events if e.effective_at == selected_anchor.effective_at]
    if boundary_events:
        outcome = _resolve_latest_revision(
            boundary_events,
            available_at_of=lambda e: e.available_at,
            value_of=lambda e: e.state,
            decision_time=canonical_decision_time,
        )
        if outcome.latest_available_at is not None:
            if outcome.conflicted:
                findings.append(
                    IntegrityFinding(
                        code=IntegrityFindingCode.EVENT_CONFLICT,
                        subject_id=facts.instrument_id,
                        effective_at=selected_anchor.effective_at,
                        available_at=outcome.latest_available_at,
                    )
                )
            elif outcome.value is not selected_anchor.state:
                findings.append(
                    IntegrityFinding(
                        code=IntegrityFindingCode.ANCHOR_EVENT_CONFLICT,
                        subject_id=facts.instrument_id,
                        effective_at=selected_anchor.effective_at,
                        available_at=max(selected_anchor.available_at, outcome.latest_available_at),
                    )
                )

    # BLOCKER 1 fix: visibility is filtered before effective-group selection.
    normal_events = [
        e for e in facts.events if selected_anchor.effective_at < e.effective_at <= canonical_as_of
    ]
    group = _latest_visible_effective_group(
        normal_events,
        effective_at_of=lambda e: e.effective_at,
        available_at_of=lambda e: e.available_at,
        decision_time=canonical_decision_time,
    )
    if group:
        outcome = _resolve_latest_revision(
            group,
            available_at_of=lambda e: e.available_at,
            value_of=lambda e: e.state,
            decision_time=canonical_decision_time,
        )
        if outcome.latest_available_at is not None:
            if outcome.conflicted:
                findings.append(
                    IntegrityFinding(
                        code=IntegrityFindingCode.EVENT_CONFLICT,
                        subject_id=facts.instrument_id,
                        effective_at=group[0].effective_at,
                        available_at=outcome.latest_available_at,
                    )
                )
            else:
                resolved_state = outcome.value

    coverage = _resolve_lifecycle_coverage(
        facts=facts,
        certificates=coverage_certificates,
        anchor_effective_at=selected_anchor.effective_at,
        as_of=canonical_as_of,
    )
    coverage_code = _coverage_finding_code(coverage)
    if coverage_code is not None:
        findings.append(
            IntegrityFinding(
                code=coverage_code,
                subject_id=None,
                effective_at=None,
                available_at=None,
            )
        )

    status = _derive_status(findings)
    return InstrumentLifecycleResolution(
        status=status,
        instrument_id=facts.instrument_id,
        as_of=canonical_as_of,
        decision_time=canonical_decision_time,
        state=resolved_state if status is UniverseIntegrityResolutionStatus.RESOLVED else None,
        selected_anchor=selected_anchor,
        coverage=coverage,
        findings=tuple(findings),
    )


def _resolve_lifecycle_coverage(
    *,
    facts: InstrumentLifecycleFacts,
    certificates: Sequence[InstrumentLifecycleCoverageCertificate],
    anchor_effective_at: datetime,
    as_of: datetime,
) -> CoverageDiagnostics:
    valid_intervals: list[TemporalInterval] = []
    valid_certificate_count = 0
    scope_mismatch_count = 0
    fingerprint_mismatch_count = 0

    for certificate in certificates:
        if certificate.instrument_id != facts.instrument_id:
            scope_mismatch_count += 1
            continue
        expected = compute_instrument_lifecycle_event_slice_fingerprint(
            instrument_id=facts.instrument_id,
            coverage_start=certificate.coverage_start,
            coverage_end=certificate.coverage_end,
            events=facts.events,
        )
        if expected != certificate.certified_event_slice_fingerprint:
            fingerprint_mismatch_count += 1
            continue
        valid_certificate_count += 1
        valid_intervals.append(TemporalInterval(certificate.coverage_start, certificate.coverage_end))

    return _evaluate_coverage(
        valid_intervals=valid_intervals,
        valid_certificate_count=valid_certificate_count,
        scope_mismatch_count=scope_mismatch_count,
        fingerprint_mismatch_count=fingerprint_mismatch_count,
        anchor_effective_at=anchor_effective_at,
        as_of=as_of,
    )


# --------------------------------------------------------------------------
# Classification resolution
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class ClassificationResolution:
    status: UniverseIntegrityResolutionStatus
    instrument_id: str
    taxonomy_id: str
    as_of: datetime
    decision_time: datetime
    value: ClassificationValue | None
    selected_anchor: ClassificationAnchor | None
    coverage: CoverageDiagnostics | None
    findings: tuple[IntegrityFinding, ...]

    def __post_init__(self) -> None:
        _require_enum("status", self.status, UniverseIntegrityResolutionStatus)
        object.__setattr__(
            self, "instrument_id", _require_identity("instrument_id", self.instrument_id)
        )
        object.__setattr__(self, "taxonomy_id", _require_identity("taxonomy_id", self.taxonomy_id))
        object.__setattr__(self, "as_of", canonical_utc_datetime(self.as_of))
        object.__setattr__(self, "decision_time", canonical_utc_datetime(self.decision_time))
        for finding in self.findings:
            if not isinstance(finding, IntegrityFinding):
                raise ValueError(f"findings must contain only IntegrityFinding, got {finding!r}")
        object.__setattr__(self, "findings", tuple(sorted(self.findings, key=_finding_sort_key)))

        derived = _derive_status(self.findings)
        if self.status is not derived:
            raise ValueError(
                f"status {self.status.value!r} does not match finding-derived status "
                f"{derived.value!r}"
            )

        if self.status is UniverseIntegrityResolutionStatus.RESOLVED:
            if not isinstance(self.value, ClassificationValue):
                raise ValueError("RESOLVED requires a ClassificationValue")
            if self.selected_anchor is None:
                raise ValueError("RESOLVED requires a selected_anchor")
            if self.findings:
                raise ValueError("RESOLVED must have no findings")
            if self.coverage is None or not self.coverage.satisfied:
                raise ValueError("RESOLVED requires satisfied coverage")
        else:
            if self.value is not None:
                raise ValueError("non-RESOLVED must have value=None")


def resolve_classification(
    facts: ClassificationFacts,
    *,
    as_of: datetime,
    decision_time: datetime,
    coverage_certificates: Sequence[ClassificationCoverageCertificate] = (),
) -> ClassificationResolution:
    if not isinstance(facts, ClassificationFacts):
        raise ValueError(f"facts must be a ClassificationFacts instance, got {facts!r}")
    canonical_as_of = canonical_utc_datetime(as_of)
    canonical_decision_time = canonical_utc_datetime(decision_time)

    findings: list[IntegrityFinding] = []

    eligible_anchors = [a for a in facts.anchors if a.effective_at <= canonical_as_of]
    by_effective: dict[datetime, list[ClassificationAnchor]] = {}
    for anchor in eligible_anchors:
        by_effective.setdefault(anchor.effective_at, []).append(anchor)

    selected_effective_at: datetime | None = None
    selected_outcome: _RevisionOutcome | None = None
    for effective_at in sorted(by_effective, reverse=True):
        outcome = _resolve_latest_revision(
            by_effective[effective_at],
            available_at_of=lambda a: a.available_at,
            value_of=lambda a: a.value,
            decision_time=canonical_decision_time,
        )
        if outcome.latest_available_at is None:
            continue
        selected_effective_at = effective_at
        selected_outcome = outcome
        break

    if selected_outcome is None:
        findings.append(
            IntegrityFinding(
                code=IntegrityFindingCode.NO_VISIBLE_ANCHOR,
                subject_id=None,
                effective_at=None,
                available_at=None,
            )
        )
        return ClassificationResolution(
            status=_derive_status(findings),
            instrument_id=facts.instrument_id,
            taxonomy_id=facts.taxonomy_id,
            as_of=canonical_as_of,
            decision_time=canonical_decision_time,
            value=None,
            selected_anchor=None,
            coverage=None,
            findings=tuple(findings),
        )

    if selected_outcome.conflicted:
        findings.append(
            IntegrityFinding(
                code=IntegrityFindingCode.ANCHOR_CONFLICT,
                subject_id=None,
                effective_at=selected_effective_at,
                available_at=selected_outcome.latest_available_at,
            )
        )
        return ClassificationResolution(
            status=_derive_status(findings),
            instrument_id=facts.instrument_id,
            taxonomy_id=facts.taxonomy_id,
            as_of=canonical_as_of,
            decision_time=canonical_decision_time,
            value=None,
            selected_anchor=None,
            coverage=None,
            findings=tuple(findings),
        )

    selected_anchor = next(
        a
        for a in by_effective[selected_effective_at]
        if a.available_at == selected_outcome.latest_available_at and a.value == selected_outcome.value
    )
    resolved_value = selected_anchor.value

    boundary_events = [e for e in facts.events if e.effective_at == selected_anchor.effective_at]
    if boundary_events:
        outcome = _resolve_latest_revision(
            boundary_events,
            available_at_of=lambda e: e.available_at,
            value_of=lambda e: e.value,
            decision_time=canonical_decision_time,
        )
        if outcome.latest_available_at is not None:
            if outcome.conflicted:
                findings.append(
                    IntegrityFinding(
                        code=IntegrityFindingCode.EVENT_CONFLICT,
                        subject_id=facts.instrument_id,
                        effective_at=selected_anchor.effective_at,
                        available_at=outcome.latest_available_at,
                    )
                )
            elif outcome.value != selected_anchor.value:
                findings.append(
                    IntegrityFinding(
                        code=IntegrityFindingCode.ANCHOR_EVENT_CONFLICT,
                        subject_id=facts.instrument_id,
                        effective_at=selected_anchor.effective_at,
                        available_at=max(selected_anchor.available_at, outcome.latest_available_at),
                    )
                )

    # BLOCKER 1 fix: visibility is filtered before effective-group selection.
    normal_events = [
        e for e in facts.events if selected_anchor.effective_at < e.effective_at <= canonical_as_of
    ]
    group = _latest_visible_effective_group(
        normal_events,
        effective_at_of=lambda e: e.effective_at,
        available_at_of=lambda e: e.available_at,
        decision_time=canonical_decision_time,
    )
    if group:
        outcome = _resolve_latest_revision(
            group,
            available_at_of=lambda e: e.available_at,
            value_of=lambda e: e.value,
            decision_time=canonical_decision_time,
        )
        if outcome.latest_available_at is not None:
            if outcome.conflicted:
                findings.append(
                    IntegrityFinding(
                        code=IntegrityFindingCode.EVENT_CONFLICT,
                        subject_id=facts.instrument_id,
                        effective_at=group[0].effective_at,
                        available_at=outcome.latest_available_at,
                    )
                )
            else:
                resolved_value = outcome.value

    coverage = _resolve_classification_coverage(
        facts=facts,
        certificates=coverage_certificates,
        anchor_effective_at=selected_anchor.effective_at,
        as_of=canonical_as_of,
    )
    coverage_code = _coverage_finding_code(coverage)
    if coverage_code is not None:
        findings.append(
            IntegrityFinding(
                code=coverage_code,
                subject_id=None,
                effective_at=None,
                available_at=None,
            )
        )

    status = _derive_status(findings)
    return ClassificationResolution(
        status=status,
        instrument_id=facts.instrument_id,
        taxonomy_id=facts.taxonomy_id,
        as_of=canonical_as_of,
        decision_time=canonical_decision_time,
        value=resolved_value if status is UniverseIntegrityResolutionStatus.RESOLVED else None,
        selected_anchor=selected_anchor,
        coverage=coverage,
        findings=tuple(findings),
    )


def _resolve_classification_coverage(
    *,
    facts: ClassificationFacts,
    certificates: Sequence[ClassificationCoverageCertificate],
    anchor_effective_at: datetime,
    as_of: datetime,
) -> CoverageDiagnostics:
    valid_intervals: list[TemporalInterval] = []
    valid_certificate_count = 0
    scope_mismatch_count = 0
    fingerprint_mismatch_count = 0

    for certificate in certificates:
        if certificate.instrument_id != facts.instrument_id or certificate.taxonomy_id != facts.taxonomy_id:
            scope_mismatch_count += 1
            continue
        expected = compute_classification_event_slice_fingerprint(
            instrument_id=facts.instrument_id,
            taxonomy_id=facts.taxonomy_id,
            coverage_start=certificate.coverage_start,
            coverage_end=certificate.coverage_end,
            events=facts.events,
        )
        if expected != certificate.certified_event_slice_fingerprint:
            fingerprint_mismatch_count += 1
            continue
        valid_certificate_count += 1
        valid_intervals.append(TemporalInterval(certificate.coverage_start, certificate.coverage_end))

    return _evaluate_coverage(
        valid_intervals=valid_intervals,
        valid_certificate_count=valid_certificate_count,
        scope_mismatch_count=scope_mismatch_count,
        fingerprint_mismatch_count=fingerprint_mismatch_count,
        anchor_effective_at=anchor_effective_at,
        as_of=as_of,
    )
