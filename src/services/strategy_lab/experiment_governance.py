"""Strategy Lab V0.1 -- Experiment Governance Foundation.

Provides the experiment identity, parameter provenance, and lineage-audit
contracts that later Strategy Lab work (OOS / Walk-Forward, benchmark,
regime, component attribution) needs in order to reason about *which*
experiment produced a piece of evidence and *where its parameters came
from*.

This module is pure compute: no persistence, no repository, no I/O beyond
reading its own inputs. It deliberately does **not** implement an OOS
consumption ledger, Walk-Forward folds, PIT universe handling, or any
`PerformanceReport` integration, and it does not touch the Hard or Soft
validation pipelines.

Trust boundary (V0.1 -- read this before relying on ``manifest_hash``)
---------------------------------------------------------------------
Component fingerprints inside ``governed_components`` are **caller-supplied
trusted inputs**. ``manifest_hash`` proves that a manifest is a consistent,
canonical function of the fingerprints it was handed; it does **not** prove
that those fingerprints faithfully represent the external component
contents they claim to describe. A caller that computes a component
fingerprint incorrectly, or that stamps a stale fingerprint, produces a
manifest that hashes perfectly and still misrepresents the experiment.
Verifying fingerprint faithfulness against real component contents is out
of scope for V0.1 and belongs to whichever layer owns those components.

Immutability by identity
------------------------
An ``experiment_id`` names exactly one manifest definition, permanently.
The same ``experiment_id`` observed with a different manifest definition
(a different ``manifest_hash``, parent, or root) is always a lineage
violation, regardless of any downstream OOS-consumption state. This
Foundation takes no OOS-consumption input at all; OOS burn consequences
remain the responsibility of the future persistent ledger.

``governed_components`` is exposed as a read-only mapping: because it *is*
definition identity rather than diagnostics, neither the caller's original
mapping nor the stored attribute may change ``manifest_hash`` after
construction. ``manifest_hash`` itself is a derived read-only property --
there is no hash field to inject or assign, so a caller can neither forge it
nor mutate what it computes to.

A conflicting ``experiment_id`` is ambiguous, not merely duplicated
-------------------------------------------------------------------
When one ``experiment_id`` carries more than one distinct definition, the
audit reports ``DUPLICATE_EXPERIMENT_IDENTITY`` **and** stops treating that
id as a usable lineage node. Choosing one of the conflicting definitions
would make parent/root comparison, ancestor traversal, and cycle detection
depend on the order the history happened to arrive in. Instead the id is
excluded from the resolvable index, and any walk that reaches it yields an
``AMBIGUOUS_ANCESTOR`` claim at ``INDETERMINATE`` severity: the audit
declines to conclude rather than guessing. Membership of the resolvable and
ambiguous sets is computed from the *set* of distinct definition descriptors
per id, so it cannot depend on input order.

``ExperimentLineageAudit.unverifiable_claims`` exposes exactly the
``INDETERMINATE`` violations, derived from the canonically sorted
``violations`` rather than maintained as a second list, so calibrated
abstention has one source of truth and inherits the report's order
invariance.

Governed components are an open mapping
---------------------------------------
``governed_components`` is intentionally open-ended: unknown keys are
accepted and hashed like any other. ``RECOGNIZED_GOVERNED_COMPONENTS`` is
**advisory only** -- it exists so a typo such as ``"feature"`` instead of
``"features"`` is visible via ``ExperimentManifest.unrecognized_component_keys``,
never so that an unrecognized key is rejected. There is deliberately no
anti-shrink test over this key set: governance coverage is expected to grow,
and a frozen whitelist would be exactly the fragile mechanism this design
avoids.

Canonicalization is narrow on purpose
-------------------------------------
The canonical manifest input is only ``schema_version`` plus
``governed_components``. This is not, and must not become, a general JSON
canonicalization framework: non-string component keys or fingerprints are
rejected outright rather than coerced, so no ``default=str``-style silent
stringification can produce a stable-looking but meaningless digest.

    manifest_hash = SHA256(canonical(schema_version + governed_components))

``experiment_id``, ``parent_experiment_id``, ``root_experiment_id``, and
``created_at`` are excluded **structurally** -- the hash function only ever
receives the governed subset, rather than receiving a whole manifest and
removing named fields. A denylist would silently sweep any future identity
field into the hash; this construction cannot.

Temporal contract
-----------------
Every governance datetime must be timezone-aware and is canonicalized to
UTC at construction; a naive datetime raises ``ValueError``. This is
deliberately stricter than the existing Strategy Lab engines
(``TradeObservation`` / ``ExecutionObservation`` accept naive datetimes),
and those engines are **not** retrofitted here. Governance timestamps are
provenance facts that must be globally comparable; engine timestamps are
caller-supplied observation data.

Structural well-formedness vs. lineage semantics
------------------------------------------------
``ExperimentManifest.__post_init__`` validates only *well-formedness*
(non-empty identifiers, string components, aware datetimes). Lineage
*semantics* -- self-parent, root invariants, child/root mismatch, cycles,
missing parents, conflicting duplicate identity -- are evaluated by
``audit_experiment_lineage`` and reported as structured
``LineageViolation`` records. A malformed lineage must remain constructible,
otherwise it could never be audited.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from types import MappingProxyType
from typing import Any, Mapping, Sequence


class ParameterOriginType(str, Enum):
    PRIOR_EXPERIMENT = "prior_experiment"
    LITERATURE = "literature"
    MANUAL_PRIOR = "manual_prior"


class LineageAuditVerdict(str, Enum):
    PASS = "pass"
    VIOLATION = "violation"
    INDETERMINATE = "indeterminate"


class LineageViolationSeverity(str, Enum):
    VIOLATION = "violation"
    INDETERMINATE = "indeterminate"


class LineageViolationCode(str, Enum):
    ROOT_INVARIANT = "root_invariant"
    CHILD_ROOT_MISMATCH = "child_root_mismatch"
    MISSING_PARENT = "missing_parent"
    SELF_PARENT = "self_parent"
    LINEAGE_CYCLE = "lineage_cycle"
    DUPLICATE_EXPERIMENT_IDENTITY = "duplicate_experiment_identity"
    AMBIGUOUS_ANCESTOR = "ambiguous_ancestor"


# Layout of each descriptor tuple reported in DUPLICATE_EXPERIMENT_IDENTITY
# evidence. A same-hash conflict is still distinguishable because parent and
# root identity travel with the hash.
DEFINITION_DESCRIPTOR_FIELDS = ("manifest_hash", "parent_experiment_id", "root_experiment_id")


# Advisory only -- see module docstring. Unknown keys stay valid.
RECOGNIZED_GOVERNED_COMPONENTS = frozenset(
    {
        "strategy_config",
        "parameter_search_space",
        "parameter_origin",
        "features",
        "labels",
        "universe_policy",
        "window_configuration",
        "contamination_policy",
        "evaluation_protocol",
    }
)

# Highest precedence first: any VIOLATION dominates; otherwise any
# INDETERMINATE dominates; otherwise PASS.
_VERDICT_PRECEDENCE = (
    LineageAuditVerdict.VIOLATION,
    LineageAuditVerdict.INDETERMINATE,
)

_SEVERITY_TO_VERDICT = {
    LineageViolationSeverity.VIOLATION: LineageAuditVerdict.VIOLATION,
    LineageViolationSeverity.INDETERMINATE: LineageAuditVerdict.INDETERMINATE,
}


def _require_nonempty_str(label: str, value: Any) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be a string, got {value!r}")
    if not value.strip():
        raise ValueError(f"{label} must not be empty")
    return value


def _require_utc_datetime(label: str, value: Any) -> datetime:
    """Reject naive datetimes; canonicalize aware datetimes to UTC."""

    if not isinstance(value, datetime):
        raise ValueError(f"{label} must be a datetime, got {value!r}")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{label} must be timezone-aware, got naive {value!r}")
    return value.astimezone(timezone.utc)


def _canonical_component_payload(
    schema_version: str,
    governed_components: Mapping[str, str],
) -> str:
    """Canonical V0.1 manifest input: schema_version + governed_components only.

    No ``default=`` fallback is passed to ``json.dumps`` on purpose -- every
    value is validated as a string beforehand, so an unsupported type raises
    instead of being silently stringified into a meaningless digest.
    """

    return json.dumps(
        {
            "schema_version": schema_version,
            "governed_components": dict(sorted(governed_components.items())),
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


@dataclass(frozen=True)
class ParameterOrigin:
    """Provenance of a FIXED parameter set declared outside this experiment."""

    origin_type: ParameterOriginType
    source_ref: str
    parameter_hash: str
    declared_at: datetime
    information_horizon_end: datetime
    origin_experiment_id: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.origin_type, ParameterOriginType):
            raise ValueError(
                f"origin_type must be a ParameterOriginType instance, got {self.origin_type!r}"
            )
        _require_nonempty_str("source_ref", self.source_ref)
        _require_nonempty_str("parameter_hash", self.parameter_hash)

        object.__setattr__(
            self, "declared_at", _require_utc_datetime("declared_at", self.declared_at)
        )
        object.__setattr__(
            self,
            "information_horizon_end",
            _require_utc_datetime("information_horizon_end", self.information_horizon_end),
        )

        if self.origin_type is ParameterOriginType.PRIOR_EXPERIMENT:
            if self.origin_experiment_id is None:
                raise ValueError(
                    "origin_experiment_id is required when origin_type is PRIOR_EXPERIMENT"
                )
            _require_nonempty_str("origin_experiment_id", self.origin_experiment_id)
        elif self.origin_experiment_id is not None:
            raise ValueError(
                f"origin_experiment_id is not allowed when origin_type is "
                f"{self.origin_type.value}"
            )

        if self.information_horizon_end > self.declared_at:
            raise ValueError(
                "information_horizon_end must not be later than declared_at "
                f"({self.information_horizon_end.isoformat()} > {self.declared_at.isoformat()})"
            )

    @property
    def fingerprint(self) -> str:
        """Canonical fingerprint covering every provenance field."""

        payload = json.dumps(
            {
                "origin_type": self.origin_type.value,
                "source_ref": self.source_ref,
                "parameter_hash": self.parameter_hash,
                "declared_at": self.declared_at.isoformat(),
                "information_horizon_end": self.information_horizon_end.isoformat(),
                "origin_experiment_id": self.origin_experiment_id,
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ExperimentManifest:
    experiment_id: str
    schema_version: str
    governed_components: Mapping[str, str]
    created_at: datetime
    root_experiment_id: str
    parent_experiment_id: str | None = None

    def __post_init__(self) -> None:
        _require_nonempty_str("experiment_id", self.experiment_id)
        _require_nonempty_str("schema_version", self.schema_version)
        _require_nonempty_str("root_experiment_id", self.root_experiment_id)
        if self.parent_experiment_id is not None:
            _require_nonempty_str("parent_experiment_id", self.parent_experiment_id)

        object.__setattr__(
            self, "created_at", _require_utc_datetime("created_at", self.created_at)
        )

        if not isinstance(self.governed_components, Mapping):
            raise ValueError(
                f"governed_components must be a mapping, got {self.governed_components!r}"
            )
        if not self.governed_components:
            raise ValueError("governed_components must not be empty")
        for key, value in self.governed_components.items():
            _require_nonempty_str("governed_components key", key)
            _require_nonempty_str(f"governed_components[{key!r}] fingerprint", value)

        # Read-only by construction: governed components are definition
        # identity, not diagnostics, so neither the caller's original mapping
        # nor the stored attribute may mutate the hash after construction.
        # Keys and values are already strict strings, so a shallow proxy over
        # a private copy is sufficient -- no deep-freeze machinery needed.
        object.__setattr__(
            self, "governed_components", MappingProxyType(dict(self.governed_components))
        )

    @property
    def manifest_hash(self) -> str:
        """SHA256(canonical(schema_version + governed_components)).

        Identity and timestamp fields are excluded structurally -- they are
        never passed to the canonicalizer in the first place.
        """

        payload = _canonical_component_payload(self.schema_version, self.governed_components)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    @property
    def unrecognized_component_keys(self) -> tuple[str, ...]:
        """Advisory diagnostic for typo visibility. Never a rejection."""

        return tuple(
            sorted(key for key in self.governed_components if key not in RECOGNIZED_GOVERNED_COMPONENTS)
        )

    def defines_same_experiment_as(self, other: "ExperimentManifest") -> bool:
        """Whether two manifests for one experiment_id agree on its definition."""

        return (
            self.manifest_hash == other.manifest_hash
            and self.parent_experiment_id == other.parent_experiment_id
            and self.root_experiment_id == other.root_experiment_id
        )


@dataclass(frozen=True)
class LineageAuditContext:
    """Caller-declared completeness of the supplied lineage history.

    The auditor never infers completeness from ``prior_manifests``: an empty
    or partial history is indistinguishable from a complete one by
    inspection, so the caller must state it. This is what separates "the
    parent genuinely does not exist" (``VIOLATION``) from "the parent was
    not supplied to this audit" (``INDETERMINATE``).
    """

    history_complete: bool

    def __post_init__(self) -> None:
        if not isinstance(self.history_complete, bool):
            raise ValueError(
                f"history_complete must be a bool, got {self.history_complete!r}"
            )


@dataclass(frozen=True)
class LineageViolation:
    code: LineageViolationCode
    severity: LineageViolationSeverity
    message: str
    evidence: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.code, LineageViolationCode):
            raise ValueError(f"code must be a LineageViolationCode instance, got {self.code!r}")
        if not isinstance(self.severity, LineageViolationSeverity):
            raise ValueError(
                f"severity must be a LineageViolationSeverity instance, got {self.severity!r}"
            )
        _require_nonempty_str("message", self.message)


@dataclass(frozen=True)
class ExperimentLineageAudit:
    experiment_id: str
    verdict: LineageAuditVerdict
    violations: tuple[LineageViolation, ...]
    history_complete: bool

    def __post_init__(self) -> None:
        _require_nonempty_str("experiment_id", self.experiment_id)
        if not isinstance(self.verdict, LineageAuditVerdict):
            raise ValueError(
                f"verdict must be a LineageAuditVerdict instance, got {self.verdict!r}"
            )
        if not isinstance(self.history_complete, bool):
            raise ValueError(
                f"history_complete must be a bool, got {self.history_complete!r}"
            )
        for violation in self.violations:
            if not isinstance(violation, LineageViolation):
                raise ValueError(
                    f"violations must contain only LineageViolation instances, got {violation!r}"
                )

        object.__setattr__(
            self, "violations", tuple(sorted(self.violations, key=_violation_sort_key))
        )

        derived = _derive_verdict(self.violations)
        if self.verdict is not derived:
            raise ValueError(
                f"verdict {self.verdict.value!r} does not match the severity-derived "
                f"verdict {derived.value!r} for the given violations"
            )

    @property
    def unverifiable_claims(self) -> tuple[LineageViolation, ...]:
        """Claims the audit could not decide, for calibrated abstention.

        Derived from the canonically sorted ``violations`` rather than
        maintained separately, so there is exactly one source of truth and
        the view inherits the report's order invariance.
        """

        return tuple(
            violation
            for violation in self.violations
            if violation.severity is LineageViolationSeverity.INDETERMINATE
        )


def _violation_sort_key(violation: LineageViolation) -> tuple[str, str, tuple[tuple[str, str], ...]]:
    return (
        violation.code.value,
        violation.message,
        tuple(sorted((str(key), str(value)) for key, value in violation.evidence.items())),
    )


def _derive_verdict(violations: Sequence[LineageViolation]) -> LineageAuditVerdict:
    present = {_SEVERITY_TO_VERDICT[violation.severity] for violation in violations}
    for verdict in _VERDICT_PRECEDENCE:
        if verdict in present:
            return verdict
    return LineageAuditVerdict.PASS


def audit_experiment_lineage(
    *,
    manifest: ExperimentManifest,
    prior_manifests: Sequence[ExperimentManifest] = (),
    context: LineageAuditContext,
) -> ExperimentLineageAudit:
    """Audit one manifest's lineage against a caller-supplied history.

    Deterministic and order-invariant: ``prior_manifests`` is consumed as a
    set of facts, and the resulting violations are canonically sorted, so
    permuting the history cannot change the verdict or the report.
    """

    violations: list[LineageViolation] = []

    # A conflicting experiment_id is not a usable lineage node: picking one of
    # its definitions would make every downstream conclusion depend on input
    # order. Such ids are therefore excluded from the resolvable index and
    # treated as ambiguous wherever the walk reaches them.
    by_id, ambiguous = _resolve_definitions((*prior_manifests, manifest))

    for experiment_id in sorted(ambiguous):
        violations.append(
            LineageViolation(
                code=LineageViolationCode.DUPLICATE_EXPERIMENT_IDENTITY,
                severity=LineageViolationSeverity.VIOLATION,
                message=(
                    f"experiment_id {experiment_id!r} appears with conflicting manifest "
                    f"definitions"
                ),
                evidence={
                    "experiment_id": experiment_id,
                    "definition_fields": DEFINITION_DESCRIPTOR_FIELDS,
                    "definitions": ambiguous[experiment_id],
                },
            )
        )

    self_parent = manifest.parent_experiment_id == manifest.experiment_id
    if self_parent:
        violations.append(
            LineageViolation(
                code=LineageViolationCode.SELF_PARENT,
                severity=LineageViolationSeverity.VIOLATION,
                message=f"experiment {manifest.experiment_id!r} declares itself as its parent",
                evidence={"experiment_id": manifest.experiment_id},
            )
        )

    if manifest.parent_experiment_id is None:
        if manifest.root_experiment_id != manifest.experiment_id:
            violations.append(
                LineageViolation(
                    code=LineageViolationCode.ROOT_INVARIANT,
                    severity=LineageViolationSeverity.VIOLATION,
                    message=(
                        f"root experiment {manifest.experiment_id!r} must declare itself as "
                        f"its own root"
                    ),
                    evidence={
                        "experiment_id": manifest.experiment_id,
                        "root_experiment_id": manifest.root_experiment_id,
                    },
                )
            )
    elif manifest.root_experiment_id == manifest.experiment_id:
        violations.append(
            LineageViolation(
                code=LineageViolationCode.ROOT_INVARIANT,
                severity=LineageViolationSeverity.VIOLATION,
                message=(
                    f"child experiment {manifest.experiment_id!r} must not declare itself as "
                    f"its own root"
                ),
                evidence={
                    "experiment_id": manifest.experiment_id,
                    "parent_experiment_id": manifest.parent_experiment_id,
                },
            )
        )

    ambiguous_ancestors: set[str] = set()

    if manifest.parent_experiment_id is not None and not self_parent:
        parent_id = manifest.parent_experiment_id
        if parent_id in ambiguous:
            # The parent exists but has no single definition, so its root
            # cannot be compared without arbitrarily choosing one.
            ambiguous_ancestors.add(parent_id)
        else:
            parent = by_id.get(parent_id)
            if parent is None:
                violations.append(
                    LineageViolation(
                        code=LineageViolationCode.MISSING_PARENT,
                        severity=(
                            LineageViolationSeverity.VIOLATION
                            if context.history_complete
                            else LineageViolationSeverity.INDETERMINATE
                        ),
                        message=(
                            f"parent {parent_id!r} of experiment "
                            f"{manifest.experiment_id!r} was not found in the supplied history"
                        ),
                        evidence={
                            "experiment_id": manifest.experiment_id,
                            "parent_experiment_id": parent_id,
                            "history_complete": context.history_complete,
                        },
                    )
                )
            elif parent.root_experiment_id != manifest.root_experiment_id:
                violations.append(
                    LineageViolation(
                        code=LineageViolationCode.CHILD_ROOT_MISMATCH,
                        severity=LineageViolationSeverity.VIOLATION,
                        message=(
                            f"experiment {manifest.experiment_id!r} declares root "
                            f"{manifest.root_experiment_id!r} but its parent declares "
                            f"{parent.root_experiment_id!r}"
                        ),
                        evidence={
                            "experiment_id": manifest.experiment_id,
                            "root_experiment_id": manifest.root_experiment_id,
                            "parent_experiment_id": parent.experiment_id,
                            "parent_root_experiment_id": parent.root_experiment_id,
                        },
                    )
                )

    if not self_parent:
        cycle_ids, blocked_by = _walk_ancestors(manifest, by_id, ambiguous)
        if blocked_by is not None:
            ambiguous_ancestors.add(blocked_by)
        if cycle_ids is not None:
            violations.append(
                LineageViolation(
                    code=LineageViolationCode.LINEAGE_CYCLE,
                    severity=LineageViolationSeverity.VIOLATION,
                    message=(
                        f"experiment {manifest.experiment_id!r} sits on a cyclic parent chain"
                    ),
                    evidence={
                        "experiment_id": manifest.experiment_id,
                        "cycle": tuple(cycle_ids),
                    },
                )
            )

    for ancestor_id in sorted(ambiguous_ancestors):
        violations.append(
            LineageViolation(
                code=LineageViolationCode.AMBIGUOUS_ANCESTOR,
                severity=LineageViolationSeverity.INDETERMINATE,
                message=(
                    f"ancestor {ancestor_id!r} of experiment {manifest.experiment_id!r} has "
                    f"conflicting definitions, so lineage beyond it cannot be decided"
                ),
                evidence={
                    "experiment_id": manifest.experiment_id,
                    "ambiguous_ancestor_id": ancestor_id,
                },
            )
        )

    return ExperimentLineageAudit(
        experiment_id=manifest.experiment_id,
        verdict=_derive_verdict(violations),
        violations=tuple(violations),
        history_complete=context.history_complete,
    )


def _definition_descriptor(manifest: ExperimentManifest) -> tuple[str, str, str]:
    """Canonical, sortable descriptor -- see DEFINITION_DESCRIPTOR_FIELDS."""

    return (
        manifest.manifest_hash,
        manifest.parent_experiment_id or "",
        manifest.root_experiment_id,
    )


def _resolve_definitions(
    manifests: Sequence[ExperimentManifest],
) -> tuple[dict[str, ExperimentManifest], dict[str, tuple[tuple[str, str, str], ...]]]:
    """Split ids into singly-defined (resolvable) and conflicting (ambiguous).

    Order-independent by construction: membership is decided by the *set* of
    distinct definition descriptors for an id, never by which definition
    happened to arrive first.
    """

    grouped: dict[str, list[ExperimentManifest]] = {}
    for candidate in manifests:
        grouped.setdefault(candidate.experiment_id, []).append(candidate)

    resolvable: dict[str, ExperimentManifest] = {}
    ambiguous: dict[str, tuple[tuple[str, str, str], ...]] = {}
    for experiment_id, items in grouped.items():
        descriptors = {_definition_descriptor(item) for item in items}
        if len(descriptors) == 1:
            resolvable[experiment_id] = items[0]
        else:
            ambiguous[experiment_id] = tuple(sorted(descriptors))
    return resolvable, ambiguous


def _walk_ancestors(
    manifest: ExperimentManifest,
    by_id: Mapping[str, ExperimentManifest],
    ambiguous: Mapping[str, Any],
) -> tuple[tuple[str, ...] | None, str | None]:
    """Walk the parent chain over resolvable nodes only.

    Returns ``(cycle_path, blocking_ambiguous_id)``. The walk stops -- and
    concludes nothing -- at an ambiguous ancestor or an absent one, so a
    cycle is only ever reported when it is fully established over
    unambiguously defined nodes.
    """

    visited: list[str] = [manifest.experiment_id]
    seen = {manifest.experiment_id}
    current = manifest.parent_experiment_id
    while current is not None:
        if current in seen:
            visited.append(current)
            return tuple(visited), None
        if current in ambiguous:
            return None, current
        visited.append(current)
        seen.add(current)
        ancestor = by_id.get(current)
        if ancestor is None:
            return None, None
        current = ancestor.parent_experiment_id
    return None, None
