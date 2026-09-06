"""Strategy Lab V0.1 -- Information Dependency Contract Foundation.

Declares what information a strategy's features, labels, and state actually
depend on, and derives the warmup, purge, embargo, and overlap obligations
that follow. It answers "what would have to be true for this evidence to be
causally clean", never "is this strategy profitable".

Pure compute, stdlib only, and a leaf within the package: no Data Layer, no
trading calendar, no repositories or persistence, no other Strategy Lab
engine, and nothing from ``experiment_governance`` -- in particular none of
its private canonicalization helpers, which are deliberately narrow to their
own contract and must not be generalized. The canonicalizer below is a
separate, equally narrow local implementation.

Declaration state is a wrapper, not a payload field
---------------------------------------------------
``DependencyDeclaration[T]`` is the generic declaration-state wrapper --
``status`` plus an optional ``payload`` and ``reason``. The payload
dataclasses describe the dependency *itself* and never repeat declaration
status, so "is this declared" and "what does it say" cannot drift apart.
``InformationDependencyDeclaration`` is the aggregate contract holding one
wrapper per slot.

``FeatureDependencyDeclaration`` mirrors that wrapper shape --
``status`` / ``payload`` / ``reason`` -- but additionally carries
``feature_id``, because a feature's identity must survive being undeclared.
An undeclared feature is therefore a named, stated fact rather than an absence
inferred from a missing value, and a ``reason`` may accompany either status:
explaining a declared dependency is as legitimate as explaining a gap.

Frozen NOT_APPLICABLE matrix
----------------------------
    Label        invalid   -- supervised evidence always reaches forward
    FeatureSet   valid, non-empty reason required
    State        invalid   -- declare STATELESS, a positive claim
    Overlap      valid, non-empty reason required
    Feature item invalid   -- only the set as a whole may be N/A

``bar_grid_id`` is opaque, and the evaluation grid is declared
--------------------------------------------------------------
A ``bar_grid_id`` is an exact-match identifier and nothing more: a strict
non-empty string, never normalized, never alias-resolved, never interpreted.
This module assigns no meaning to ``"1m"``, ``"15m"``, ``"1d"``, ``"daily"``,
``"D"``, or any provider spelling, and does not treat any two distinct
strings as equivalent.

``FeatureSetDependency.evaluation_bar_grid_id`` states the grid the strategy
is actually evaluated on. Cross-grid detection compares each declared
feature's own ``bar_grid_id`` against that declared evaluation grid -- it does
**not** infer "same grid" merely because every feature happens to agree with
every other feature. A single feature stated on grid A while evaluation
happens on grid B is cross-grid, even though the feature set is internally
uniform.

A lookback stated on a different bar grid lives in a different index space, so
it is **never numerically compared** -- not maxed, not summed, not ranked.
Converting between grids needs a calendar this module deliberately does not
own, so cross-grid warmup is ``EXTERNAL_RESOLUTION_REQUIRED``: it leaves
``feature_warmup_bars`` and ``required_warmup_bars`` at ``None``, sets
``warmup_source=UNRESOLVED`` and ``calendar_resolution_required=True``, and --
on its own -- does **not** reduce completeness. The dependency was stated
exactly; only the conversion is out of scope here.

``LIMITED_EXPRESSION`` is reserved for a genuine schema capability gap, namely
``AvailabilityLagKind.UNSUPPORTED``: something the declaration vocabulary
cannot express at all, as opposed to something it expressed precisely that
simply needs an external resolver.

``None`` is not ``0``
---------------------
An *undeclared* quantity is unknown and poisons anything derived from it; a
quantity declared *not applicable* is exactly zero and fully resolved. These
are never collapsed. An ``UNDECLARED`` wrapper may not carry payload, and a
``NOT_APPLICABLE`` wrapper must state a non-empty reason.

Lookback and availability are orthogonal
----------------------------------------
A feature's ``lookback_bars`` and a label's ``information_horizon_bars`` are
always plain non-negative bar counts -- they are how far the dependency
reaches through the bar grid, and that is always expressible. Separately,
each carries an ``availability_lag`` describing *when the value can actually
be known*, and only that lag may be ``BAR_COUNT``, ``DURATION``, or
``UNSUPPORTED``. A lookback is never itself a duration or unsupported, and an
availability lag never poisons warmup.

``feature_availability_requirements`` are obligations, not a census: only
``DECLARED`` features appear there, each with a concrete ``bar_grid_id`` and
complete ``AvailabilityLag`` -- kind, bars, duration, and note, not merely the
kind. An undeclared feature is represented solely by its structured
unresolved finding, so an obligation list never contains an entry whose
obligation is unknown.

Unresolved category is authoritative
------------------------------------
Every unresolved finding carries an ``UnresolvedCategory``, and that category
alone drives completeness. There is no separate presentation-severity axis:

    any UNDECLARED               -> INCOMPLETE
    else any LIMITED_EXPRESSION  -> LIMITED_EXPRESSION
    else                         -> COMPLETE

``EXTERNAL_RESOLUTION_REQUIRED`` -- a ``DURATION`` availability lag, a
cross-grid warmup, or an unresolved overlap -- stays in the findings and never
reduces completeness.

There is deliberately no aggregate "warmup unresolved" finding. Warmup can be
unresolved because a side is undeclared *or* because grids need external
resolution, and those carry different categories; inventing one aggregate
category for both would misreport whichever case it did not match. Instead an
unresolved warmup is expressed structurally --
``required_warmup_bars=None`` with ``warmup_source=UNRESOLVED`` -- while only
the specific underlying findings are reported.

Derivation semantics (frozen)
-----------------------------
- Feature set ``UNDECLARED`` -> feature warmup unknown; ``NOT_APPLICABLE`` ->
  exactly 0; ``DECLARED`` -> the maximum lookback among features stated on the
  declared evaluation grid. A single ``UNDECLARED`` feature poisons the
  aggregate while keeping its identity; any off-evaluation-grid feature makes
  it externally unresolvable. Every feature tied at the binding maximum is
  preserved.
- State ``UNDECLARED`` -> unknown; ``STATELESS`` / ``WARM_START`` -> 0;
  ``COLD_START`` -> the declared convergence warmup, which must itself sit on
  the evaluation grid to be comparable.
- ``warmup_source`` is a single scalar: ``FEATURE`` when the feature side is
  strictly larger, ``STATE`` when the state side is, ``BOTH`` when they are
  equal and positive, ``NONE`` when both are zero, and ``UNRESOLVED`` when
  either side is unknown. Feature-level ties are preserved separately in
  ``binding_feature_ids``.
- Purge is driven by the label information horizon plus its availability lag,
  never by feature lookback: a feature looks *backwards* from a decision,
  whereas a label reaches *forwards* past it. A zero horizon with a zero lag
  derives a purge of exactly zero -- a resolved answer, not a missing one.
  ``PurgeDerivation`` is a structured diagnostic record of the facts that
  produced (or failed to produce) that number, never a verdict or driver
  label: when the label is undeclared its fields explicitly represent
  unavailable declaration facts.

Embargo
-------
V0.1 is strictly sequential as a *capability boundary*, not as a
caller-declared option: there is no topology field on the declaration, none
in the canonical payload, and none in either fingerprint. Under that single
supported capability the derivation is constant --
``required_embargo_bars = 0`` with ``embargo_reason =
NO_APPLICABLE_DEPENDENCY``. This derivation is valid only for V0.1's
strict-sequential capability; non-sequential and combinatorial-purged
cross-validation topologies are not implemented, and when one is introduced
this constant must be revisited rather than reused.

Fingerprints
------------
``declaration_fingerprint`` covers the canonical declarations only.
``contract_fingerprint`` covers the contract version plus those same
declarations. ``contract_fingerprint`` -- not ``declaration_fingerprint`` --
is the value intended for a future
``governed_components["information_dependency"]`` entry. This module neither
imports nor instantiates any Experiment Governance object; producing that
string is the whole of the integration seam. Both fingerprints are derived
read-only properties: they are provenance facts, so a report cannot be
constructed carrying supplied fingerprint strings.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import timedelta
from enum import Enum
from typing import Any, Generic, Mapping, Sequence, TypeVar


class DeclarationStatus(str, Enum):
    DECLARED = "declared"
    UNDECLARED = "undeclared"
    NOT_APPLICABLE = "not_applicable"


class AvailabilityLagKind(str, Enum):
    BAR_COUNT = "bar_count"
    DURATION = "duration"
    UNSUPPORTED = "unsupported"


class StateCarryMode(str, Enum):
    STATELESS = "stateless"
    WARM_START = "warm_start"
    COLD_START = "cold_start"


class EmbargoReason(str, Enum):
    NO_APPLICABLE_DEPENDENCY = "no_applicable_dependency"


class WarmupSource(str, Enum):
    """Which side binds the required warmup. Scalar, never a collection."""

    NONE = "none"
    FEATURE = "feature"
    STATE = "state"
    BOTH = "both"
    UNRESOLVED = "unresolved"


class ResolutionStatus(str, Enum):
    RESOLVED = "resolved"
    UNRESOLVED = "unresolved"


class CompletenessLevel(str, Enum):
    COMPLETE = "complete"
    LIMITED_EXPRESSION = "limited_expression"
    INCOMPLETE = "incomplete"


class UnresolvedCategory(str, Enum):
    """Authoritative model: category alone drives completeness."""

    UNDECLARED = "undeclared"
    LIMITED_EXPRESSION = "limited_expression"
    EXTERNAL_RESOLUTION_REQUIRED = "external_resolution_required"


class UnresolvedCode(str, Enum):
    FEATURE_SET_UNDECLARED = "feature_set_undeclared"
    FEATURE_UNDECLARED = "feature_undeclared"
    CROSS_GRID_WARMUP_NOT_COMPARABLE = "cross_grid_warmup_not_comparable"
    STATE_UNDECLARED = "state_undeclared"
    LABEL_UNDECLARED = "label_undeclared"
    PURGE_UNRESOLVED = "purge_unresolved"
    CALENDAR_RESOLUTION_REQUIRED = "calendar_resolution_required"
    UNSUPPORTED_AVAILABILITY = "unsupported_availability"
    OVERLAP_UNDECLARED = "overlap_undeclared"
    OVERLAP_UNRESOLVED = "overlap_unresolved"


# Highest precedence first.
_COMPLETENESS_PRECEDENCE = (
    (UnresolvedCategory.UNDECLARED, CompletenessLevel.INCOMPLETE),
    (UnresolvedCategory.LIMITED_EXPRESSION, CompletenessLevel.LIMITED_EXPRESSION),
)

# Findings whose resolution needs an external calendar / grid mapping. Not
# every EXTERNAL_RESOLUTION_REQUIRED finding qualifies: an unresolved overlap
# awaits sample intervals, not a calendar.
_CALENDAR_RESOLUTION_CODES = frozenset(
    {
        UnresolvedCode.CALENDAR_RESOLUTION_REQUIRED,
        UnresolvedCode.CROSS_GRID_WARMUP_NOT_COMPARABLE,
    }
)

# V0.1 capability boundary -- see the module docstring's Embargo section.
_STRICT_SEQUENTIAL_EMBARGO_BARS = 0

T = TypeVar("T")


def _require_nonempty_str(label: str, value: Any) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be a string, got {value!r}")
    if not value.strip():
        raise ValueError(f"{label} must not be empty")
    return value


def _require_non_negative_int(label: str, value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{label} must be an int, got {value!r}")
    if value < 0:
        raise ValueError(f"{label} must not be negative, got {value}")
    return value


def _require_positive_int(label: str, value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{label} must be an int, got {value!r}")
    if value <= 0:
        raise ValueError(f"{label} must be positive, got {value}")
    return value


def _require_enum(label: str, value: Any, enum_type: type[Enum]) -> Any:
    if not isinstance(value, enum_type):
        raise ValueError(f"{label} must be a {enum_type.__name__} instance, got {value!r}")
    return value


def _timedelta_microseconds(value: timedelta) -> int:
    return (value.days * 86_400 + value.seconds) * 1_000_000 + value.microseconds


def _canonical_encode(value: Any) -> Any:
    """Narrow canonical encoder over a closed value space.

    Deliberately not a generic JSON framework: enums become their ``.value``,
    ``timedelta`` becomes exact integer microseconds, ``None`` is preserved
    explicitly, and any other type raises rather than being coerced. There is
    no ``default=`` fallback anywhere in this module.
    """

    if isinstance(value, Enum):
        return _canonical_encode(value.value)
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, timedelta):
        return {"__timedelta_microseconds__": _timedelta_microseconds(value)}
    if isinstance(value, Mapping):
        return {
            _require_nonempty_str("canonical mapping key", key): _canonical_encode(item)
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


@dataclass(frozen=True)
class AvailabilityLag:
    """When a declared value can actually be known.

    Orthogonal to how far the dependency reaches: only the *lag* may be a
    duration or unsupported, never the lookback or horizon itself.
    """

    kind: AvailabilityLagKind
    bars: int | None = None
    duration: timedelta | None = None
    note: str | None = None

    def __post_init__(self) -> None:
        _require_enum("kind", self.kind, AvailabilityLagKind)

        if self.kind is AvailabilityLagKind.BAR_COUNT:
            if self.bars is None:
                raise ValueError("BAR_COUNT availability lag requires bars")
            _require_non_negative_int("bars", self.bars)
            if self.duration is not None:
                raise ValueError("BAR_COUNT availability lag must not carry a duration")
        elif self.kind is AvailabilityLagKind.DURATION:
            if not isinstance(self.duration, timedelta):
                raise ValueError("DURATION availability lag requires a timedelta duration")
            if self.duration < timedelta(0):
                raise ValueError("duration must not be negative")
            if self.bars is not None:
                raise ValueError("DURATION availability lag must not carry a bar count")
        else:
            if self.bars is not None or self.duration is not None:
                raise ValueError("UNSUPPORTED availability lag must not carry a value")
            _require_nonempty_str("note", self.note)

    def _payload(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "bars": self.bars,
            "duration": self.duration,
            "note": self.note,
        }


@dataclass(frozen=True)
class PurgeDerivation:
    """Structured record of the facts behind the purge result.

    A diagnostic, never a verdict or driver label. When the label is
    undeclared, its fields explicitly represent unavailable declaration facts
    rather than being omitted.
    """

    label_horizon_bars: int | None
    label_lag_kind: AvailabilityLagKind | None
    label_lag_bars: int | None
    resolvable_in_bars: bool

    def __post_init__(self) -> None:
        if self.label_horizon_bars is not None:
            _require_non_negative_int("label_horizon_bars", self.label_horizon_bars)
        if self.label_lag_kind is not None:
            _require_enum("label_lag_kind", self.label_lag_kind, AvailabilityLagKind)
        if not isinstance(self.resolvable_in_bars, bool):
            raise ValueError(
                f"resolvable_in_bars must be a bool, got {self.resolvable_in_bars!r}"
            )

        # horizon and lag_kind are declared together or not at all: a label
        # that was declared always states its horizon, and the undeclared
        # state (both None) is the only legal way to have neither.
        if (self.label_horizon_bars is None) != (self.label_lag_kind is None):
            raise ValueError(
                "label_horizon_bars and label_lag_kind must be present or absent together"
            )

        if self.label_lag_kind is None:
            if self.label_lag_bars is not None:
                raise ValueError("label_lag_bars must be None when label_lag_kind is None")
            if self.resolvable_in_bars:
                raise ValueError("resolvable_in_bars requires a BAR_COUNT label_lag_kind")
        elif self.label_lag_kind is AvailabilityLagKind.BAR_COUNT:
            if self.label_lag_bars is None:
                raise ValueError("a BAR_COUNT label_lag_kind requires label_lag_bars")
            _require_non_negative_int("label_lag_bars", self.label_lag_bars)
            if not self.resolvable_in_bars:
                raise ValueError("a BAR_COUNT label_lag_kind must be resolvable_in_bars=True")
        else:
            # DURATION / UNSUPPORTED: the lag is known but not expressible in
            # bars, so no lag_bars value exists and the derivation cannot be
            # resolvable.
            if self.label_lag_bars is not None:
                raise ValueError(
                    f"a {self.label_lag_kind.value} label_lag_kind must not carry label_lag_bars"
                )
            if self.resolvable_in_bars:
                raise ValueError(
                    f"a {self.label_lag_kind.value} label_lag_kind must not be "
                    f"resolvable_in_bars=True"
                )


@dataclass(frozen=True)
class FeatureDependency:
    """What a declared feature depends on. Carries no declaration status."""

    bar_grid_id: str
    lookback_bars: int
    availability_lag: AvailabilityLag

    def __post_init__(self) -> None:
        _require_nonempty_str("bar_grid_id", self.bar_grid_id)
        _require_non_negative_int("lookback_bars", self.lookback_bars)
        if not isinstance(self.availability_lag, AvailabilityLag):
            raise ValueError(
                f"availability_lag must be an AvailabilityLag instance, "
                f"got {self.availability_lag!r}"
            )

    def _payload(self) -> dict[str, Any]:
        return {
            "bar_grid_id": self.bar_grid_id,
            "lookback_bars": self.lookback_bars,
            "availability_lag": self.availability_lag._payload(),
        }


@dataclass(frozen=True)
class FeatureDependencyDeclaration:
    """A known feature id plus its own declaration state.

    Mirrors ``DependencyDeclaration``'s status/payload/reason shape, with
    ``feature_id`` added so a feature's identity survives being undeclared.
    """

    feature_id: str
    status: DeclarationStatus
    payload: FeatureDependency | None = None
    reason: str | None = None

    def __post_init__(self) -> None:
        _require_nonempty_str("feature_id", self.feature_id)
        _require_enum("status", self.status, DeclarationStatus)

        if self.status is DeclarationStatus.NOT_APPLICABLE:
            raise ValueError(
                "a single feature cannot be NOT_APPLICABLE: only the feature set as a "
                "whole may be, and only with a reason"
            )
        if self.status is DeclarationStatus.DECLARED:
            if not isinstance(self.payload, FeatureDependency):
                raise ValueError("a DECLARED feature requires a FeatureDependency payload")
        elif self.payload is not None:
            raise ValueError("an UNDECLARED feature must not carry placeholder payload")

        # A reason is optional under either status: explaining a declared
        # dependency is as legitimate as explaining a gap.
        if self.reason is not None:
            _require_nonempty_str("reason", self.reason)

    def _payload_dict(self) -> dict[str, Any]:
        return {
            "feature_id": self.feature_id,
            "status": self.status,
            "payload": None if self.payload is None else self.payload._payload(),
            "reason": self.reason,
        }


@dataclass(frozen=True)
class FeatureSetDependency:
    """The declared feature set and the grid the strategy is evaluated on."""

    evaluation_bar_grid_id: str
    features: tuple[FeatureDependencyDeclaration, ...]

    def __post_init__(self) -> None:
        _require_nonempty_str("evaluation_bar_grid_id", self.evaluation_bar_grid_id)
        for feature in self.features:
            if not isinstance(feature, FeatureDependencyDeclaration):
                raise ValueError(
                    "features must contain only FeatureDependencyDeclaration instances, "
                    f"got {feature!r}"
                )
        if not self.features:
            raise ValueError("a declared feature set must not be empty")
        ids = [feature.feature_id for feature in self.features]
        if len(ids) != len(set(ids)):
            raise ValueError("feature ids must be unique within a feature set")
        object.__setattr__(
            self,
            "features",
            tuple(sorted(self.features, key=lambda feature: feature.feature_id)),
        )

    def _payload(self) -> dict[str, Any]:
        return {
            "evaluation_bar_grid_id": self.evaluation_bar_grid_id,
            "features": [feature._payload_dict() for feature in self.features],
        }


@dataclass(frozen=True)
class LabelDependency:
    """What a declared label depends on. Carries no declaration status."""

    bar_grid_id: str
    information_horizon_bars: int
    availability_lag: AvailabilityLag

    def __post_init__(self) -> None:
        _require_nonempty_str("bar_grid_id", self.bar_grid_id)
        _require_non_negative_int("information_horizon_bars", self.information_horizon_bars)
        if not isinstance(self.availability_lag, AvailabilityLag):
            raise ValueError("a label requires an AvailabilityLag")

    def _payload(self) -> dict[str, Any]:
        return {
            "bar_grid_id": self.bar_grid_id,
            "information_horizon_bars": self.information_horizon_bars,
            "availability_lag": self.availability_lag._payload(),
        }


@dataclass(frozen=True)
class StateDependency:
    """How declared state carries across evaluation. No declaration status."""

    carry_mode: StateCarryMode
    convergence_warmup_bars: int | None = None
    bar_grid_id: str | None = None

    def __post_init__(self) -> None:
        _require_enum("carry_mode", self.carry_mode, StateCarryMode)
        if self.carry_mode is StateCarryMode.COLD_START:
            _require_non_negative_int("convergence_warmup_bars", self.convergence_warmup_bars)
            _require_nonempty_str("bar_grid_id", self.bar_grid_id)
        else:
            if self.convergence_warmup_bars is not None:
                raise ValueError(
                    f"{self.carry_mode.value} state must not declare a convergence warmup"
                )
            if self.bar_grid_id is not None:
                raise ValueError(f"{self.carry_mode.value} state must not declare a bar grid")

    def _payload(self) -> dict[str, Any]:
        return {
            "carry_mode": self.carry_mode,
            "convergence_warmup_bars": self.convergence_warmup_bars,
            "bar_grid_id": self.bar_grid_id,
        }


@dataclass(frozen=True)
class SampleInformationInterval:
    """Half-open ``[start_bar_index, end_bar_index)`` in one caller-provided
    bar-index domain.

    V0.1 interprets all resolved intervals for one overlap declaration within
    a single such domain; it carries no grid identifier of its own.
    Cross-domain interval identity validation is outside this contract and is
    deliberately not simulated by attaching per-interval grid metadata here.
    """

    start_bar_index: int
    end_bar_index: int

    def __post_init__(self) -> None:
        _require_non_negative_int("start_bar_index", self.start_bar_index)
        _require_non_negative_int("end_bar_index", self.end_bar_index)
        if self.end_bar_index <= self.start_bar_index:
            raise ValueError(
                "end_bar_index must be strictly greater than start_bar_index "
                f"({self.end_bar_index} <= {self.start_bar_index})"
            )

    def _payload(self) -> dict[str, Any]:
        return {
            "start_bar_index": self.start_bar_index,
            "end_bar_index": self.end_bar_index,
        }


@dataclass(frozen=True)
class SampleOverlapDependency:
    """How samples are drawn and, when known, their exact spans."""

    sampling_step_bars: int
    resolved_intervals: tuple[SampleInformationInterval, ...] | None = None

    def __post_init__(self) -> None:
        _require_positive_int("sampling_step_bars", self.sampling_step_bars)
        if self.resolved_intervals is None:
            return

        intervals = tuple(self.resolved_intervals)
        if not intervals:
            raise ValueError("resolved_intervals must be None when unresolved, never empty")
        for interval in intervals:
            if not isinstance(interval, SampleInformationInterval):
                raise ValueError(
                    "resolved_intervals must contain only SampleInformationInterval "
                    f"instances, got {interval!r}"
                )
        object.__setattr__(
            self,
            "resolved_intervals",
            tuple(
                sorted(intervals, key=lambda item: (item.start_bar_index, item.end_bar_index))
            ),
        )

    def _payload(self) -> dict[str, Any]:
        return {
            "sampling_step_bars": self.sampling_step_bars,
            "resolved_intervals": (
                None
                if self.resolved_intervals is None
                else [interval._payload() for interval in self.resolved_intervals]
            ),
        }


@dataclass(frozen=True)
class DependencyDeclaration(Generic[T]):
    """Generic declaration-state wrapper around a dependency payload.

    Structural rules only. Which slots may be ``NOT_APPLICABLE`` is a property
    of the aggregate contract, not of this wrapper, and is enforced by
    ``InformationDependencyDeclaration``.
    """

    status: DeclarationStatus
    payload: T | None = None
    reason: str | None = None

    def __post_init__(self) -> None:
        _require_enum("status", self.status, DeclarationStatus)

        if self.status is DeclarationStatus.DECLARED:
            if self.payload is None:
                raise ValueError("a DECLARED dependency requires a payload")
            if self.reason is not None:
                raise ValueError("a DECLARED dependency must not carry a reason")
        elif self.status is DeclarationStatus.UNDECLARED:
            if self.payload is not None or self.reason is not None:
                raise ValueError("an UNDECLARED dependency must not carry placeholder payload")
        else:
            if self.payload is not None:
                raise ValueError("a NOT_APPLICABLE dependency must not carry a payload")
            _require_nonempty_str("reason", self.reason)

    def _payload_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "payload": None if self.payload is None else self.payload._payload(),
            "reason": self.reason,
        }


@dataclass(frozen=True)
class InformationDependencyDeclaration:
    """The aggregate contract: one declaration wrapper per dependency slot."""

    contract_version: str
    feature_set: DependencyDeclaration[FeatureSetDependency]
    label: DependencyDeclaration[LabelDependency]
    state: DependencyDeclaration[StateDependency]
    overlap: DependencyDeclaration[SampleOverlapDependency]

    def __post_init__(self) -> None:
        _require_nonempty_str("contract_version", self.contract_version)

        for name, payload_type, not_applicable_allowed, refusal in (
            ("feature_set", FeatureSetDependency, True, ""),
            (
                "label",
                LabelDependency,
                False,
                "supervised evidence always reaches forward from the decision point",
            ),
            (
                "state",
                StateDependency,
                False,
                "declare STATELESS instead, which is a positive claim rather than an "
                "absent one",
            ),
            ("overlap", SampleOverlapDependency, True, ""),
        ):
            slot = getattr(self, name)
            if not isinstance(slot, DependencyDeclaration):
                raise ValueError(
                    f"{name} must be a DependencyDeclaration wrapper, got {slot!r}"
                )
            if slot.status is DeclarationStatus.DECLARED and not isinstance(
                slot.payload, payload_type
            ):
                raise ValueError(
                    f"{name} payload must be a {payload_type.__name__} instance, "
                    f"got {slot.payload!r}"
                )
            if slot.status is DeclarationStatus.NOT_APPLICABLE and not not_applicable_allowed:
                raise ValueError(f"a {name} dependency cannot be NOT_APPLICABLE: {refusal}")

    def _declaration_payload(self) -> dict[str, Any]:
        """Canonical declarations only -- contract_version is excluded.

        No topology key participates: strict-sequential is a V0.1 capability
        boundary, not a declared, fingerprint-bearing option.
        """

        return {
            "feature_set": self.feature_set._payload_dict(),
            "label": self.label._payload_dict(),
            "state": self.state._payload_dict(),
            "overlap": self.overlap._payload_dict(),
        }

    @property
    def declaration_fingerprint(self) -> str:
        return _sha256(_canonical_json(self._declaration_payload()))

    @property
    def contract_fingerprint(self) -> str:
        return _sha256(
            _canonical_json(
                {
                    "contract_version": self.contract_version,
                    "declarations": self._declaration_payload(),
                }
            )
        )


@dataclass(frozen=True)
class UnresolvedFinding:
    code: UnresolvedCode
    category: UnresolvedCategory
    message: str
    evidence: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require_enum("code", self.code, UnresolvedCode)
        _require_enum("category", self.category, UnresolvedCategory)
        _require_nonempty_str("message", self.message)


@dataclass(frozen=True)
class FeatureAvailabilityRequirement:
    """An obligation carried by a DECLARED feature.

    Undeclared features never appear here -- an unknown obligation is not an
    obligation. They are represented solely by their unresolved finding.
    """

    feature_id: str
    bar_grid_id: str
    availability_lag: AvailabilityLag


@dataclass(frozen=True)
class OverlapDiagnostics:
    resolution_status: ResolutionStatus
    sampling_step_bars: int | None = None
    sample_count: int | None = None
    max_concurrent_samples: int | None = None
    max_non_overlapping_samples: int | None = None

    def __post_init__(self) -> None:
        _require_enum("resolution_status", self.resolution_status, ResolutionStatus)
        if self.resolution_status is ResolutionStatus.UNRESOLVED and any(
            value is not None
            for value in (
                self.sample_count,
                self.max_concurrent_samples,
                self.max_non_overlapping_samples,
            )
        ):
            raise ValueError("an UNRESOLVED overlap must not expose exact metrics")


@dataclass(frozen=True)
class GridFeatureWarmup:
    """Supplementary per-grid diagnostic, not part of the frozen contract."""

    bar_grid_id: str
    warmup_bars: int | None
    binding_feature_ids: tuple[str, ...]


@dataclass(frozen=True)
class InformationDependencyReport:
    """Derived obligations. Fingerprints are provenance, never caller-supplied.

    ``declaration`` is the sole constructor route to the fingerprints, which
    are exposed as read-only derived properties -- there is no fingerprint
    field to pass or assign. ``per_grid_feature_warmup`` and
    ``unresolved_feature_ids`` are supplementary diagnostics rather than frozen
    contract fields.
    """

    declaration: InformationDependencyDeclaration
    completeness: CompletenessLevel
    required_purge_bars: int | None
    purge_derivation: PurgeDerivation
    required_warmup_bars: int | None
    feature_warmup_bars: int | None
    state_warmup_bars: int | None
    warmup_source: WarmupSource
    binding_feature_ids: tuple[str, ...]
    state_carry_mode: StateCarryMode | None
    feature_availability_requirements: tuple[FeatureAvailabilityRequirement, ...]
    required_embargo_bars: int
    embargo_reason: EmbargoReason
    overlap: OverlapDiagnostics | None
    unresolved: tuple[UnresolvedFinding, ...]
    calendar_resolution_required: bool
    per_grid_feature_warmup: tuple[GridFeatureWarmup, ...] = ()
    unresolved_feature_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.declaration, InformationDependencyDeclaration):
            raise ValueError(
                f"declaration must be an InformationDependencyDeclaration instance, "
                f"got {self.declaration!r}"
            )
        _require_enum("completeness", self.completeness, CompletenessLevel)
        _require_enum("warmup_source", self.warmup_source, WarmupSource)
        if not isinstance(self.purge_derivation, PurgeDerivation):
            raise ValueError(
                f"purge_derivation must be a PurgeDerivation instance, "
                f"got {self.purge_derivation!r}"
            )
        for finding in self.unresolved:
            if not isinstance(finding, UnresolvedFinding):
                raise ValueError(
                    f"unresolved must contain only UnresolvedFinding instances, got {finding!r}"
                )
        object.__setattr__(
            self, "unresolved", tuple(sorted(self.unresolved, key=_finding_sort_key))
        )

        unresolved_warmup = self.required_warmup_bars is None
        if unresolved_warmup and self.warmup_source is not WarmupSource.UNRESOLVED:
            raise ValueError("an unresolved warmup must report warmup_source UNRESOLVED")
        if not unresolved_warmup and self.warmup_source is WarmupSource.UNRESOLVED:
            raise ValueError("a resolved warmup must not report warmup_source UNRESOLVED")
        if unresolved_warmup and self.binding_feature_ids:
            raise ValueError("an unresolved warmup must not name binding features")

        if (self.required_purge_bars is None) is self.purge_derivation.resolvable_in_bars:
            raise ValueError(
                "required_purge_bars and purge_derivation.resolvable_in_bars must agree"
            )

        # purge_derivation must be a faithful reflection of the actual label
        # declaration -- a locally self-consistent PurgeDerivation is not
        # enough if it silently contradicts what was declared.
        label = self.declaration.label
        if label.status is DeclarationStatus.UNDECLARED:
            if self.purge_derivation != PurgeDerivation(
                label_horizon_bars=None,
                label_lag_kind=None,
                label_lag_bars=None,
                resolvable_in_bars=False,
            ):
                raise ValueError(
                    "purge_derivation must reflect the undeclared label, but carries "
                    "non-empty derivation facts"
                )
        else:
            label_payload = label.payload
            lag = label_payload.availability_lag
            if self.purge_derivation.label_horizon_bars != label_payload.information_horizon_bars:
                raise ValueError(
                    "purge_derivation.label_horizon_bars does not match the declared label's "
                    "information_horizon_bars"
                )
            if self.purge_derivation.label_lag_kind is not lag.kind:
                raise ValueError(
                    "purge_derivation.label_lag_kind does not match the declared label's "
                    "availability_lag.kind"
                )
            if (
                lag.kind is AvailabilityLagKind.BAR_COUNT
                and self.purge_derivation.label_lag_bars != lag.bars
            ):
                raise ValueError(
                    "purge_derivation.label_lag_bars does not match the declared label's "
                    "BAR_COUNT availability_lag.bars"
                )

        derived = _derive_completeness(self.unresolved)
        if self.completeness is not derived:
            raise ValueError(
                f"completeness {self.completeness.value!r} does not match the "
                f"category-derived level {derived.value!r}"
            )

    @property
    def contract_version(self) -> str:
        return self.declaration.contract_version

    @property
    def declaration_fingerprint(self) -> str:
        return self.declaration.declaration_fingerprint

    @property
    def contract_fingerprint(self) -> str:
        return self.declaration.contract_fingerprint


def _finding_sort_key(
    finding: UnresolvedFinding,
) -> tuple[str, str, str, tuple[tuple[str, str], ...]]:
    return (
        finding.code.value,
        finding.category.value,
        finding.message,
        tuple(sorted((str(key), str(value)) for key, value in finding.evidence.items())),
    )


def _derive_completeness(findings: Sequence[UnresolvedFinding]) -> CompletenessLevel:
    present = {finding.category for finding in findings}
    for category, level in _COMPLETENESS_PRECEDENCE:
        if category in present:
            return level
    return CompletenessLevel.COMPLETE


def _derive_warmup_source(feature_bars: int | None, state_bars: int | None) -> WarmupSource:
    if feature_bars is None or state_bars is None:
        return WarmupSource.UNRESOLVED
    if feature_bars > state_bars:
        return WarmupSource.FEATURE
    if state_bars > feature_bars:
        return WarmupSource.STATE
    return WarmupSource.BOTH if feature_bars > 0 else WarmupSource.NONE


def _availability_findings(
    lag: AvailabilityLag,
    *,
    origin: str,
    extra_evidence: Mapping[str, Any] | None = None,
) -> list[UnresolvedFinding]:
    evidence: dict[str, Any] = {"origin": origin}
    if extra_evidence:
        evidence.update(extra_evidence)

    if lag.kind is AvailabilityLagKind.DURATION:
        return [
            UnresolvedFinding(
                code=UnresolvedCode.CALENDAR_RESOLUTION_REQUIRED,
                category=UnresolvedCategory.EXTERNAL_RESOLUTION_REQUIRED,
                message=(
                    f"{origin} is expressed as a duration and requires external calendar "
                    f"resolution before it can be stated in bars"
                ),
                evidence={
                    **evidence,
                    "duration_microseconds": _timedelta_microseconds(lag.duration),
                },
            )
        ]
    if lag.kind is AvailabilityLagKind.UNSUPPORTED:
        return [
            UnresolvedFinding(
                code=UnresolvedCode.UNSUPPORTED_AVAILABILITY,
                category=UnresolvedCategory.LIMITED_EXPRESSION,
                message=f"{origin} cannot be expressed in the supported vocabulary",
                evidence={**evidence, "note": lag.note},
            )
        ]
    return []


def _resolve_features(
    feature_set: DependencyDeclaration[FeatureSetDependency],
    findings: list[UnresolvedFinding],
) -> tuple[
    int | None,
    str | None,
    tuple[GridFeatureWarmup, ...],
    tuple[str, ...],
    tuple[str, ...],
    tuple[FeatureAvailabilityRequirement, ...],
]:
    """Return (feature_bars, evaluation_grid, per_grid, binding_ids,
    unresolved_ids, requirements)."""

    if feature_set.status is DeclarationStatus.UNDECLARED:
        findings.append(
            UnresolvedFinding(
                code=UnresolvedCode.FEATURE_SET_UNDECLARED,
                category=UnresolvedCategory.UNDECLARED,
                message="the feature set is undeclared, so feature warmup is unknown",
                evidence={},
            )
        )
        return None, None, (), (), (), ()

    if feature_set.status is DeclarationStatus.NOT_APPLICABLE:
        # Explicitly zero and fully resolved -- never conflated with unknown.
        return 0, None, (), (), (), ()

    payload = feature_set.payload
    evaluation_grid = payload.evaluation_bar_grid_id

    unresolved_ids: list[str] = []
    requirements: list[FeatureAvailabilityRequirement] = []
    off_grid: list[tuple[str, str]] = []
    per_grid_bars: dict[str, int] = {}
    per_grid_binding: dict[str, list[str]] = {}

    for feature in payload.features:
        if feature.status is DeclarationStatus.UNDECLARED:
            unresolved_ids.append(feature.feature_id)
            findings.append(
                UnresolvedFinding(
                    code=UnresolvedCode.FEATURE_UNDECLARED,
                    category=UnresolvedCategory.UNDECLARED,
                    message=(
                        f"feature {feature.feature_id!r} is undeclared, so aggregate feature "
                        f"warmup is unknown"
                    ),
                    evidence={"feature_id": feature.feature_id, "reason": feature.reason},
                )
            )
            continue

        dependency = feature.payload
        requirements.append(
            FeatureAvailabilityRequirement(
                feature_id=feature.feature_id,
                bar_grid_id=dependency.bar_grid_id,
                availability_lag=dependency.availability_lag,
            )
        )

        # Availability lag is a separate obligation: it never poisons warmup,
        # because lookback_bars is always a plain, resolvable bar count.
        findings.extend(
            _availability_findings(
                dependency.availability_lag,
                origin=f"feature {feature.feature_id!r} availability lag",
                extra_evidence={
                    "feature_id": feature.feature_id,
                    "bar_grid_id": dependency.bar_grid_id,
                },
            )
        )

        if dependency.bar_grid_id != evaluation_grid:
            # Compared against the *declared* evaluation grid, never inferred
            # from the features agreeing with one another.
            off_grid.append((feature.feature_id, dependency.bar_grid_id))

        bars = dependency.lookback_bars
        current = per_grid_bars.get(dependency.bar_grid_id)
        if current is None or bars > current:
            per_grid_bars[dependency.bar_grid_id] = bars
            per_grid_binding[dependency.bar_grid_id] = [feature.feature_id]
        elif bars == current:
            # Every tie is preserved -- never collapsed to the first winner.
            per_grid_binding[dependency.bar_grid_id].append(feature.feature_id)

    per_grid = tuple(
        GridFeatureWarmup(
            bar_grid_id=grid,
            warmup_bars=per_grid_bars[grid],
            binding_feature_ids=tuple(sorted(per_grid_binding[grid])),
        )
        for grid in sorted(per_grid_bars)
    )
    requirements_tuple = tuple(requirements)

    if off_grid:
        findings.append(
            UnresolvedFinding(
                code=UnresolvedCode.CROSS_GRID_WARMUP_NOT_COMPARABLE,
                # Stated exactly; only the grid conversion needs an external
                # resolver, so this is not a schema capability gap.
                category=UnresolvedCategory.EXTERNAL_RESOLUTION_REQUIRED,
                message=(
                    "feature lookbacks are stated on bar grids other than the declared "
                    "evaluation grid and are never numerically compared without external "
                    "grid resolution"
                ),
                evidence={
                    "evaluation_bar_grid_id": evaluation_grid,
                    "off_grid_features": tuple(sorted(off_grid)),
                },
            )
        )

    if unresolved_ids or off_grid:
        return (
            None,
            evaluation_grid,
            per_grid,
            (),
            tuple(sorted(unresolved_ids)),
            requirements_tuple,
        )

    evaluation = next(entry for entry in per_grid if entry.bar_grid_id == evaluation_grid)
    return (
        evaluation.warmup_bars,
        evaluation_grid,
        per_grid,
        evaluation.binding_feature_ids,
        (),
        requirements_tuple,
    )


def _resolve_state(
    state: DependencyDeclaration[StateDependency],
    findings: list[UnresolvedFinding],
) -> tuple[int | None, str | None, StateCarryMode | None]:
    if state.status is DeclarationStatus.UNDECLARED:
        findings.append(
            UnresolvedFinding(
                code=UnresolvedCode.STATE_UNDECLARED,
                category=UnresolvedCategory.UNDECLARED,
                message="state carry behaviour is undeclared, so state warmup is unknown",
                evidence={},
            )
        )
        return None, None, None

    payload = state.payload
    if payload.carry_mode is StateCarryMode.COLD_START:
        grid = payload.bar_grid_id if payload.convergence_warmup_bars else None
        return payload.convergence_warmup_bars, grid, payload.carry_mode
    return 0, None, payload.carry_mode


def _resolve_purge(
    label: DependencyDeclaration[LabelDependency],
    findings: list[UnresolvedFinding],
) -> tuple[int | None, PurgeDerivation]:
    if label.status is DeclarationStatus.UNDECLARED:
        findings.append(
            UnresolvedFinding(
                code=UnresolvedCode.LABEL_UNDECLARED,
                category=UnresolvedCategory.UNDECLARED,
                message="the label dependency is undeclared, so required purge is unknown",
                evidence={},
            )
        )
        # Fields explicitly represent unavailable declaration facts.
        return None, PurgeDerivation(
            label_horizon_bars=None,
            label_lag_kind=None,
            label_lag_bars=None,
            resolvable_in_bars=False,
        )

    payload = label.payload
    lag = payload.availability_lag
    findings.extend(
        _availability_findings(
            lag,
            origin="label availability lag",
            extra_evidence={"bar_grid_id": payload.bar_grid_id},
        )
    )

    if lag.kind is not AvailabilityLagKind.BAR_COUNT:
        findings.append(
            UnresolvedFinding(
                code=UnresolvedCode.PURGE_UNRESOLVED,
                category=(
                    UnresolvedCategory.EXTERNAL_RESOLUTION_REQUIRED
                    if lag.kind is AvailabilityLagKind.DURATION
                    else UnresolvedCategory.LIMITED_EXPRESSION
                ),
                message="required purge cannot be stated in bars from the declared label",
                evidence={"availability_lag_kind": lag.kind.value},
            )
        )
        return None, PurgeDerivation(
            label_horizon_bars=payload.information_horizon_bars,
            label_lag_kind=lag.kind,
            label_lag_bars=None,
            resolvable_in_bars=False,
        )

    # Purge follows the label's forward reach, never a feature's backward one.
    return payload.information_horizon_bars + lag.bars, PurgeDerivation(
        label_horizon_bars=payload.information_horizon_bars,
        label_lag_kind=lag.kind,
        label_lag_bars=lag.bars,
        resolvable_in_bars=True,
    )


def _resolve_overlap(
    overlap: DependencyDeclaration[SampleOverlapDependency],
    findings: list[UnresolvedFinding],
) -> OverlapDiagnostics | None:
    if overlap.status is DeclarationStatus.NOT_APPLICABLE:
        return None

    if overlap.status is DeclarationStatus.UNDECLARED:
        findings.append(
            UnresolvedFinding(
                code=UnresolvedCode.OVERLAP_UNDECLARED,
                category=UnresolvedCategory.UNDECLARED,
                message="sample overlap is undeclared, so concurrency cannot be assessed",
                evidence={},
            )
        )
        return None

    payload = overlap.payload
    if payload.resolved_intervals is None:
        findings.append(
            UnresolvedFinding(
                code=UnresolvedCode.OVERLAP_UNRESOLVED,
                category=UnresolvedCategory.EXTERNAL_RESOLUTION_REQUIRED,
                message=(
                    "sample overlap is declared but its intervals are not resolved yet; the "
                    "obligation is retained"
                ),
                evidence={"sampling_step_bars": payload.sampling_step_bars},
            )
        )
        return OverlapDiagnostics(
            resolution_status=ResolutionStatus.UNRESOLVED,
            sampling_step_bars=payload.sampling_step_bars,
        )

    intervals = payload.resolved_intervals
    return OverlapDiagnostics(
        resolution_status=ResolutionStatus.RESOLVED,
        sampling_step_bars=payload.sampling_step_bars,
        sample_count=len(intervals),
        max_concurrent_samples=_max_concurrency(intervals),
        max_non_overlapping_samples=_max_non_overlapping(intervals),
    )


def _max_concurrency(intervals: Sequence[SampleInformationInterval]) -> int:
    """Sweep line over half-open intervals: an end never collides with a start."""

    events: list[tuple[int, int]] = []
    for interval in intervals:
        events.append((interval.start_bar_index, 1))
        events.append((interval.end_bar_index, -1))
    # -1 sorts before +1 at equal index, so [a, b) and [b, c) never overlap.
    events.sort(key=lambda event: (event[0], event[1]))

    current = 0
    peak = 0
    for _, delta in events:
        current += delta
        peak = max(peak, current)
    return peak


def _max_non_overlapping(intervals: Sequence[SampleInformationInterval]) -> int:
    """Greedy earliest-end selection over half-open intervals."""

    ordered = sorted(intervals, key=lambda item: (item.end_bar_index, item.start_bar_index))
    selected = 0
    frontier: int | None = None
    for interval in ordered:
        if frontier is None or interval.start_bar_index >= frontier:
            selected += 1
            frontier = interval.end_bar_index
    return selected


def evaluate_information_dependency(
    declaration: InformationDependencyDeclaration,
) -> InformationDependencyReport:
    """Derive warmup / purge / embargo obligations from a frozen declaration."""

    if not isinstance(declaration, InformationDependencyDeclaration):
        raise ValueError(
            f"declaration must be an InformationDependencyDeclaration instance, "
            f"got {declaration!r}"
        )

    findings: list[UnresolvedFinding] = []

    (
        feature_bars,
        evaluation_grid,
        per_grid,
        binding_feature_ids,
        unresolved_feature_ids,
        availability_requirements,
    ) = _resolve_features(declaration.feature_set, findings)
    state_bars, state_grid, state_carry_mode = _resolve_state(declaration.state, findings)

    required_bars: int | None = None
    resolved_binding_features: tuple[str, ...] = ()

    if feature_bars is not None and state_bars is not None:
        if state_grid is not None and evaluation_grid is not None and state_grid != evaluation_grid:
            findings.append(
                UnresolvedFinding(
                    code=UnresolvedCode.CROSS_GRID_WARMUP_NOT_COMPARABLE,
                    category=UnresolvedCategory.EXTERNAL_RESOLUTION_REQUIRED,
                    message=(
                        "state warmup is stated on a bar grid other than the declared "
                        "evaluation grid and is never numerically compared without external "
                        "grid resolution"
                    ),
                    evidence={
                        "evaluation_bar_grid_id": evaluation_grid,
                        "state_bar_grid_id": state_grid,
                    },
                )
            )
        else:
            required_bars = max(feature_bars, state_bars)

    # No aggregate "warmup unresolved" finding is emitted: an unresolved warmup
    # is expressed structurally, and only the specific underlying causes are
    # reported, each with its own category.
    warmup_source = (
        _derive_warmup_source(feature_bars, state_bars)
        if required_bars is not None
        else WarmupSource.UNRESOLVED
    )
    if warmup_source in (WarmupSource.FEATURE, WarmupSource.BOTH):
        resolved_binding_features = binding_feature_ids

    required_purge_bars, purge_derivation = _resolve_purge(declaration.label, findings)
    overlap = _resolve_overlap(declaration.overlap, findings)

    calendar_resolution_required = any(
        finding.code in _CALENDAR_RESOLUTION_CODES for finding in findings
    )

    return InformationDependencyReport(
        declaration=declaration,
        completeness=_derive_completeness(findings),
        required_purge_bars=required_purge_bars,
        purge_derivation=purge_derivation,
        required_warmup_bars=required_bars,
        feature_warmup_bars=feature_bars,
        state_warmup_bars=state_bars,
        warmup_source=warmup_source,
        binding_feature_ids=resolved_binding_features,
        state_carry_mode=state_carry_mode,
        feature_availability_requirements=availability_requirements,
        required_embargo_bars=_STRICT_SEQUENTIAL_EMBARGO_BARS,
        embargo_reason=EmbargoReason.NO_APPLICABLE_DEPENDENCY,
        overlap=overlap,
        unresolved=tuple(findings),
        calendar_resolution_required=calendar_resolution_required,
        per_grid_feature_warmup=per_grid,
        unresolved_feature_ids=unresolved_feature_ids,
    )
