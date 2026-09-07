"""Strategy Lab V0.1 -- Walk-Forward Core Foundation.

Validates whether caller-declared fold geometry, parameter provenance,
causal-separation evidence, information-dependency obligations, lineage
evidence, and PIT-universe evidence are structurally self-consistent enough
to qualify as out-of-sample (OOS) evidence. It answers "is this walk-forward
setup structurally sound enough to trust its OOS folds", never "is this
strategy profitable".

This module does not calculate performance, Sharpe, or alpha; does not
optimize parameters; does not own persistence or an OOS Consumption Ledger;
does not generate folds; does not own a trading calendar or bar-grid
conversion; and does not own universe checkpoint/sampling policy. It
consumes already-computed evidence from ``experiment_governance``,
``information_dependency``, and ``universe_integrity`` and cross-checks it
against caller-declared fold geometry and provenance.

Non-goal: proving caller honesty
---------------------------------
``FoldParameterSelectionEvidence`` is caller-declared provenance. V0.1
detects contradictions between declared provenance and frozen
windows/governance (a declared selection timestamp that falls inside the
fold's own train window, or after its own declared completion time, or at or
after the fold's OOS start), but it does not prove that undeclared inputs
were never read. A caller that lies about these timestamps while keeping
them internally consistent is not detected here. Likewise,
``ExperimentLineageAudit`` does not audit the referenced origin experiment
itself when ``ParameterOriginType.PRIOR_EXPERIMENT`` is declared -- only
self-reference against the *current* manifest is checked.

Cross-fold OOS feedback is a reserved, unreachable-in-V0.1 code
------------------------------------------------------------------
Past raw OOS market facts legitimately become historical training data for a
later fold; past OOS *strategy outcomes* (rankings, Sharpe, hit rate)
influencing later parameter selection would require a new experiment
lineage, and are otherwise leakage. Distinguishing these two cases from
declared timestamps alone is not decidable, so
``WalkForwardFindingCode.CROSS_FOLD_OOS_FEEDBACK`` is a reserved vocabulary
member for a normative/integration hook: V0.1 never emits it itself. This
mirrors ``EMBARGO_INSUFFICIENT``, which is unreachable under the current
strict-sequential ``required_embargo_bars == 0`` capability boundary.

Warmup grid: evaluation grid, or state grid when there is no feature grid
------------------------------------------------------------------------
Warmup is normally checked against
``declaration.feature_set.payload.evaluation_bar_grid_id``. But a positive,
*resolved* ``required_warmup_bars`` can also arise with the feature set
``NOT_APPLICABLE`` (contributing exactly zero) when a ``DECLARED``
``COLD_START`` state supplies the entire warmup on its own -- the only
constructible way for that combination to exist, since an ``UNDECLARED``
feature set leaves ``required_warmup_bars`` unresolved and this whole check
is skipped. In that state-only case there is no declared evaluation grid to
compare against, so the check falls back to
``declaration.state.payload.bar_grid_id`` -- a field the closed
``StateDependency`` contract already requires whenever
``convergence_warmup_bars`` is positive, never invented here.

Manifest binding and the fingerprint chicken-and-egg
-------------------------------------------------------
``validate_walk_forward`` requires ``manifest.governed_components`` to
already carry matching fingerprints for ``information_dependency``,
``universe_policy``, ``window_configuration``, ``contamination_policy``, and
``evaluation_protocol`` -- but ``ExperimentManifest`` is immutable and must
be constructed *before* this function runs. ``window_configuration`` and
``contamination_policy`` depend on the same ``mode``/``folds``/
``parameter_selection_mode`` this function receives, and
``evaluation_protocol`` is a fixed version-pin; so a caller must be able to
compute all three independently, ahead of time, in order to embed them in
the manifest before calling this function. ``compute_window_configuration_fingerprint``,
``compute_contamination_policy_fingerprint``, and
``compute_evaluation_protocol_fingerprint`` are therefore public functions,
not private helpers -- this is the whole of the integration seam, mirroring
how ``UniverseIntegrityRequirement.fingerprint`` lets a caller pre-commit to
``universe_policy`` and ``InformationDependencyReport.contract_fingerprint``
already exists for the caller to pre-commit to ``information_dependency``.

``"information_dependency"`` is not in
``experiment_governance.RECOGNIZED_GOVERNED_COMPONENTS`` -- that set is
advisory-only there, so this is not a defect; it is simply not yet listed.
This module does not modify ``experiment_governance`` to add it and treats
the key as a de-facto reserved Walk-Forward integration key.

Experiment-wide findings are broadcast onto every fold
----------------------------------------------------------
Some findings are about the whole experiment rather than one fold's own
data: a manifest-binding failure, a lineage-audit verdict, an
information-dependency completeness gap, or a FIXED-parameter provenance
violation. Because ``FoldValidationResult.status`` must be the status
*derived from that result's own findings* (never inherited from the
report), each such experiment-wide problem is recorded twice: once as a
single canonical ``fold_id=None`` entry in ``report_findings``, and once
more, verbatim, attached with each fold's own ``fold_id`` into every
``FoldValidationResult.findings`` -- so every fold's own status correctly
reflects a problem that structurally affects all of them, and the
structural denominator (exactly one result per input fold) is never
disturbed by report-level findings creating phantom fold entries.

Evidence coverage is order-invariant
----------------------------------------
Per-fold evidence collections (parameter-selection, separation, data,
universe-integrity) are grouped by ``fold_id`` before anything is inspected,
never by first-arrival order: an id absent from the input folds is one
``EVIDENCE_FOLD_ID_UNKNOWN`` per *distinct* unknown id -- never one per
duplicate entry sharing that id -- (report-level, since there is no fold
result to attach it to), more than one entry sharing one *known* fold's id is
``DUPLICATE_EVIDENCE_FOLD_ID`` (attached to that fold, and that fold's
evidence is then treated as absent for every check that would otherwise have
used it -- picking one of the ambiguous entries would make the result depend
on input order), and a fold with no matching entry at all is
``FOLD_EVIDENCE_MISSING``.

Auditable failures return a report; only malformed inputs raise
--------------------------------------------------------------------
``ValueError`` is reserved for genuine caller/programmer mistakes a report
cannot meaningfully describe: a wrong Python type, a negative bar count, a
bool where an int is required, a naive datetime, a malformed identity string,
or an otherwise-impossible dataclass invariant. Everything else this module
can detect about an otherwise well-formed experiment -- including a
``manifest.experiment_id``/``lineage_audit.experiment_id`` mismatch
(``EXPERIMENT_IDENTITY_MISMATCH``) and a ``FIXED`` call missing
``parameter_origin`` (``PARAMETER_ORIGIN_REQUIRED``), missing
``fixed_parameter_evidence`` (``FIXED_EVIDENCE_REQUIRED``), or carrying
non-empty ``fold_parameter_selection_evidence``
(``FORBIDDEN_FOLD_SELECTION_EVIDENCE_UNDER_FIXED``) -- is an ``INVALID``
finding broadcast to every fold rather than an abort, so the caller always
gets back a report with exactly one ``FoldValidationResult`` per input fold.
With zero folds, the ``FIXED`` parameter-hash and ``PRIOR_EXPERIMENT``
self-reference checks still run (they need no fold data), but the
``information_horizon_end``/``declared_at`` boundary checks -- which need
``min(fold.train_interval.start)`` -- are skipped rather than inventing a
fake boundary; ``total_fold_count`` is simply ``0``.

Evidence must not contradict a fold's own declared geometry
----------------------------------------------------------------
A fold with no ``validation_interval`` has no train-to-validation boundary,
so its separation evidence must not carry a non-``None``
``applied_train_to_validation_purge_bars`` and its data evidence must not
carry a non-``None`` ``usable_validation_bars`` -- either is a genuine
contradiction between the evidence and the fold's own declared shape, not a
missing-evidence or insufficiency question, and is reported as
``INVALID_FOLD_GEOMETRY``.

Canonical ordering
---------------------
Folds are ordered by ``(oos_interval.start, train_interval.start,
fold_id)`` wherever fold order matters: pairwise geometry/mode checks, OOS
overlap attribution (attached to the *later* canonical fold), the
``window_configuration`` fingerprint payload, ``fold_results`` storage
order, and ``performance_eligible_fold_ids``. Findings are ordered by
``(severity_rank, code.value, fold_id_or_empty, message)``. Both orderings
are applied at construction time, so permuting any input sequence produces
byte-identical output.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Mapping, Sequence, TypeVar

from .experiment_governance import (
    ExperimentLineageAudit,
    ExperimentManifest,
    LineageAuditVerdict,
    ParameterOrigin,
    ParameterOriginType,
)
from .information_dependency import (
    CompletenessLevel,
    DeclarationStatus,
    InformationDependencyReport,
    StateCarryMode,
)
from .temporal_contract import TemporalInterval, canonical_utc_datetime, canonical_utc_text
from .universe_integrity import (
    ClassificationResolution,
    InstrumentLifecycleResolution,
    UniverseIntegrityResolutionStatus,
    UniverseMembershipResolution,
)

_WINDOW_CONFIGURATION_SCHEMA = "walk-forward-window-configuration-v0.1"
_CONTAMINATION_POLICY_SCHEMA = "walk-forward-contamination-policy-v0.1"
_EVALUATION_PROTOCOL_SCHEMA = "walk-forward-evaluation-protocol-v0.1"
_UNIVERSE_POLICY_SCHEMA = "walk-forward-universe-policy-v0.1"

_PROTOCOL_VERSION = "walk-forward-core-v0.1"
_STATUS_PRECEDENCE_VERSION = "wf-status-precedence-v0.1"
_FINDING_MAPPING_VERSION = "wf-finding-map-v0.1"
_DENOMINATOR_RULE_VERSION = "wf-structural-denominator-v0.1"

T = TypeVar("T")


class WalkForwardMode(str, Enum):
    EXPANDING = "expanding"
    ROLLING = "rolling"


class ParameterSelectionMode(str, Enum):
    FIXED = "fixed"
    TRAIN_ONLY = "train_only"
    TRAIN_VALIDATION = "train_validation"


class FoldValidationStatus(str, Enum):
    VALID = "valid"
    INSUFFICIENT_DATA = "insufficient_data"
    LEAKAGE_RISK = "leakage_risk"
    INVALID = "invalid"


class WalkForwardFindingCode(str, Enum):
    DUPLICATE_FOLD_ID = "duplicate_fold_id"
    INVALID_FOLD_GEOMETRY = "invalid_fold_geometry"
    INVALID_MODE_GEOMETRY = "invalid_mode_geometry"
    OOS_OVERLAP = "oos_overlap"
    VALIDATION_REQUIRED = "validation_required"

    EXPERIMENT_IDENTITY_MISMATCH = "experiment_identity_mismatch"
    PARAMETER_ORIGIN_REQUIRED = "parameter_origin_required"
    FIXED_EVIDENCE_REQUIRED = "fixed_evidence_required"
    FORBIDDEN_FOLD_SELECTION_EVIDENCE_UNDER_FIXED = "forbidden_fold_selection_evidence_under_fixed"

    LINEAGE_VIOLATION = "lineage_violation"
    LINEAGE_INDETERMINATE = "lineage_indeterminate"

    INFORMATION_DEPENDENCY_UNBOUND = "information_dependency_unbound"
    UNIVERSE_POLICY_UNBOUND = "universe_policy_unbound"
    WINDOW_CONFIGURATION_UNBOUND = "window_configuration_unbound"
    CONTAMINATION_POLICY_UNBOUND = "contamination_policy_unbound"
    EVALUATION_PROTOCOL_UNBOUND = "evaluation_protocol_unbound"

    UNIVERSE_INTEGRITY_CONFLICT = "universe_integrity_conflict"
    UNIVERSE_INTEGRITY_INDETERMINATE = "universe_integrity_indeterminate"
    UNIVERSE_INTEGRITY_EVIDENCE_MISSING = "universe_integrity_evidence_missing"

    PARAMETER_HASH_MISMATCH = "parameter_hash_mismatch"
    PARAMETER_ORIGIN_SELF_REFERENCE = "parameter_origin_self_reference"
    PARAMETER_ORIGIN_INFORMATION_HORIZON_VIOLATION = "parameter_origin_information_horizon_violation"
    PARAMETER_ORIGIN_DECLARED_AT_VIOLATION = "parameter_origin_declared_at_violation"
    PARAMETER_SELECTION_OUTSIDE_ALLOWED_WINDOW = "parameter_selection_outside_allowed_window"
    OOS_PARAMETER_PEEK = "oos_parameter_peek"
    CROSS_FOLD_OOS_FEEDBACK = "cross_fold_oos_feedback"

    EVIDENCE_FOLD_ID_UNKNOWN = "evidence_fold_id_unknown"
    DUPLICATE_EVIDENCE_FOLD_ID = "duplicate_evidence_fold_id"
    FOLD_EVIDENCE_MISSING = "fold_evidence_missing"

    BAR_GRID_MISMATCH = "bar_grid_mismatch"

    INFORMATION_DEPENDENCY_INCOMPLETE = "information_dependency_incomplete"
    INFORMATION_DEPENDENCY_LIMITED = "information_dependency_limited"
    PURGE_REQUIREMENT_UNRESOLVED = "purge_requirement_unresolved"
    PURGE_APPLICATION_UNRESOLVED = "purge_application_unresolved"
    PURGE_INSUFFICIENT = "purge_insufficient"
    EMBARGO_APPLICATION_UNRESOLVED = "embargo_application_unresolved"
    EMBARGO_INSUFFICIENT = "embargo_insufficient"

    WARMUP_REQUIREMENT_UNRESOLVED = "warmup_requirement_unresolved"
    TRAIN_WARMUP_INSUFFICIENT = "train_warmup_insufficient"
    VALIDATION_DATA_EMPTY = "validation_data_empty"
    OOS_DATA_EMPTY = "oos_data_empty"


_CODE_TO_STATUS: dict[WalkForwardFindingCode, FoldValidationStatus] = {}
for _code in (
    WalkForwardFindingCode.DUPLICATE_FOLD_ID,
    WalkForwardFindingCode.INVALID_FOLD_GEOMETRY,
    WalkForwardFindingCode.INVALID_MODE_GEOMETRY,
    WalkForwardFindingCode.OOS_OVERLAP,
    WalkForwardFindingCode.VALIDATION_REQUIRED,
    WalkForwardFindingCode.EXPERIMENT_IDENTITY_MISMATCH,
    WalkForwardFindingCode.PARAMETER_ORIGIN_REQUIRED,
    WalkForwardFindingCode.FIXED_EVIDENCE_REQUIRED,
    WalkForwardFindingCode.FORBIDDEN_FOLD_SELECTION_EVIDENCE_UNDER_FIXED,
    WalkForwardFindingCode.LINEAGE_VIOLATION,
    WalkForwardFindingCode.INFORMATION_DEPENDENCY_UNBOUND,
    WalkForwardFindingCode.UNIVERSE_POLICY_UNBOUND,
    WalkForwardFindingCode.WINDOW_CONFIGURATION_UNBOUND,
    WalkForwardFindingCode.CONTAMINATION_POLICY_UNBOUND,
    WalkForwardFindingCode.EVALUATION_PROTOCOL_UNBOUND,
    WalkForwardFindingCode.UNIVERSE_INTEGRITY_CONFLICT,
    WalkForwardFindingCode.PARAMETER_HASH_MISMATCH,
    WalkForwardFindingCode.PARAMETER_ORIGIN_SELF_REFERENCE,
    WalkForwardFindingCode.EVIDENCE_FOLD_ID_UNKNOWN,
    WalkForwardFindingCode.DUPLICATE_EVIDENCE_FOLD_ID,
    WalkForwardFindingCode.BAR_GRID_MISMATCH,
):
    _CODE_TO_STATUS[_code] = FoldValidationStatus.INVALID
for _code in (
    WalkForwardFindingCode.LINEAGE_INDETERMINATE,
    WalkForwardFindingCode.PARAMETER_SELECTION_OUTSIDE_ALLOWED_WINDOW,
    WalkForwardFindingCode.OOS_PARAMETER_PEEK,
    WalkForwardFindingCode.CROSS_FOLD_OOS_FEEDBACK,
    WalkForwardFindingCode.PARAMETER_ORIGIN_INFORMATION_HORIZON_VIOLATION,
    WalkForwardFindingCode.PARAMETER_ORIGIN_DECLARED_AT_VIOLATION,
    WalkForwardFindingCode.INFORMATION_DEPENDENCY_INCOMPLETE,
    WalkForwardFindingCode.INFORMATION_DEPENDENCY_LIMITED,
    WalkForwardFindingCode.PURGE_REQUIREMENT_UNRESOLVED,
    WalkForwardFindingCode.PURGE_APPLICATION_UNRESOLVED,
    WalkForwardFindingCode.PURGE_INSUFFICIENT,
    WalkForwardFindingCode.EMBARGO_APPLICATION_UNRESOLVED,
    WalkForwardFindingCode.EMBARGO_INSUFFICIENT,
    WalkForwardFindingCode.UNIVERSE_INTEGRITY_INDETERMINATE,
    WalkForwardFindingCode.UNIVERSE_INTEGRITY_EVIDENCE_MISSING,
    WalkForwardFindingCode.WARMUP_REQUIREMENT_UNRESOLVED,
    WalkForwardFindingCode.FOLD_EVIDENCE_MISSING,
):
    _CODE_TO_STATUS[_code] = FoldValidationStatus.LEAKAGE_RISK
for _code in (
    WalkForwardFindingCode.TRAIN_WARMUP_INSUFFICIENT,
    WalkForwardFindingCode.VALIDATION_DATA_EMPTY,
    WalkForwardFindingCode.OOS_DATA_EMPTY,
):
    _CODE_TO_STATUS[_code] = FoldValidationStatus.INSUFFICIENT_DATA
assert set(_CODE_TO_STATUS) == set(WalkForwardFindingCode)

_STATUS_SEVERITY_RANK = {
    FoldValidationStatus.INVALID: 0,
    FoldValidationStatus.LEAKAGE_RISK: 1,
    FoldValidationStatus.INSUFFICIENT_DATA: 2,
}
_STATUS_PRECEDENCE = (
    FoldValidationStatus.INVALID,
    FoldValidationStatus.LEAKAGE_RISK,
    FoldValidationStatus.INSUFFICIENT_DATA,
)


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


def _require_nonempty_str(label: str, value: Any) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be a string, got {value!r}")
    if not value.strip():
        raise ValueError(f"{label} must not be empty")
    return value


def _require_enum(label: str, value: Any, enum_type: type[Enum]) -> Any:
    if not isinstance(value, enum_type):
        raise ValueError(f"{label} must be a {enum_type.__name__} instance, got {value!r}")
    return value


def _require_bool(label: str, value: Any) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{label} must be a bool, got {value!r}")
    return value


def _require_bar_count(label: str, value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{label} must be an int or None, got {value!r}")
    if value < 0:
        raise ValueError(f"{label} must be non-negative, got {value}")
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


def _canonical_encode(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if value is None or isinstance(value, (str, bool, int)):
        return value
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


def _fold_sort_key(fold: "WalkForwardFold") -> tuple[datetime, datetime, str]:
    return (fold.oos_interval.start, fold.train_interval.start, fold.fold_id)


def _finding_severity_rank(code: WalkForwardFindingCode) -> int:
    return _STATUS_SEVERITY_RANK[_CODE_TO_STATUS[code]]


def _finding_sort_key(finding: "WalkForwardFinding") -> tuple[int, str, str, str]:
    return (
        _finding_severity_rank(finding.code),
        finding.code.value,
        finding.fold_id or "",
        finding.message,
    )


def _derive_fold_status(findings: Sequence["WalkForwardFinding"]) -> FoldValidationStatus:
    statuses = {_CODE_TO_STATUS[f.code] for f in findings}
    for status in _STATUS_PRECEDENCE:
        if status in statuses:
            return status
    return FoldValidationStatus.VALID


# --------------------------------------------------------------------------
# Frozen dataclasses
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class WalkForwardFold:
    fold_id: str
    train_interval: TemporalInterval
    validation_interval: TemporalInterval | None
    oos_interval: TemporalInterval

    def __post_init__(self) -> None:
        object.__setattr__(self, "fold_id", _require_identity("fold_id", self.fold_id))
        if not isinstance(self.train_interval, TemporalInterval):
            raise ValueError(
                f"train_interval must be a TemporalInterval instance, got {self.train_interval!r}"
            )
        if self.validation_interval is not None and not isinstance(
            self.validation_interval, TemporalInterval
        ):
            raise ValueError(
                f"validation_interval must be a TemporalInterval instance or None, "
                f"got {self.validation_interval!r}"
            )
        if not isinstance(self.oos_interval, TemporalInterval):
            raise ValueError(
                f"oos_interval must be a TemporalInterval instance, got {self.oos_interval!r}"
            )


@dataclass(frozen=True)
class FixedParameterEvidence:
    selected_parameter_hash: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "selected_parameter_hash", _require_identity(
                "selected_parameter_hash", self.selected_parameter_hash
            )
        )


@dataclass(frozen=True)
class FoldParameterSelectionEvidence:
    fold_id: str
    selected_parameter_hash: str
    latest_selection_information_at: datetime
    selection_completed_at: datetime

    def __post_init__(self) -> None:
        object.__setattr__(self, "fold_id", _require_identity("fold_id", self.fold_id))
        object.__setattr__(
            self, "selected_parameter_hash", _require_identity(
                "selected_parameter_hash", self.selected_parameter_hash
            )
        )
        object.__setattr__(
            self,
            "latest_selection_information_at",
            canonical_utc_datetime(self.latest_selection_information_at),
        )
        object.__setattr__(
            self, "selection_completed_at", canonical_utc_datetime(self.selection_completed_at)
        )


@dataclass(frozen=True)
class FoldSeparationEvidence:
    fold_id: str
    purge_bar_grid_id: str
    applied_train_to_validation_purge_bars: int | None
    applied_pre_oos_purge_bars: int | None
    applied_embargo_bars: int | None

    def __post_init__(self) -> None:
        object.__setattr__(self, "fold_id", _require_identity("fold_id", self.fold_id))
        object.__setattr__(
            self, "purge_bar_grid_id", _require_identity("purge_bar_grid_id", self.purge_bar_grid_id)
        )
        object.__setattr__(
            self,
            "applied_train_to_validation_purge_bars",
            _require_bar_count(
                "applied_train_to_validation_purge_bars", self.applied_train_to_validation_purge_bars
            ),
        )
        object.__setattr__(
            self,
            "applied_pre_oos_purge_bars",
            _require_bar_count("applied_pre_oos_purge_bars", self.applied_pre_oos_purge_bars),
        )
        object.__setattr__(
            self,
            "applied_embargo_bars",
            _require_bar_count("applied_embargo_bars", self.applied_embargo_bars),
        )


@dataclass(frozen=True)
class FoldDataEvidence:
    fold_id: str
    bar_grid_id: str
    usable_train_bars: int | None
    usable_validation_bars: int | None
    usable_oos_bars: int | None

    def __post_init__(self) -> None:
        object.__setattr__(self, "fold_id", _require_identity("fold_id", self.fold_id))
        object.__setattr__(self, "bar_grid_id", _require_identity("bar_grid_id", self.bar_grid_id))
        object.__setattr__(
            self, "usable_train_bars", _require_bar_count("usable_train_bars", self.usable_train_bars)
        )
        object.__setattr__(
            self,
            "usable_validation_bars",
            _require_bar_count("usable_validation_bars", self.usable_validation_bars),
        )
        object.__setattr__(
            self, "usable_oos_bars", _require_bar_count("usable_oos_bars", self.usable_oos_bars)
        )


@dataclass(frozen=True)
class UniverseIntegrityRequirement:
    require_membership: bool
    require_lifecycle: bool
    require_classification: bool

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "require_membership", _require_bool("require_membership", self.require_membership)
        )
        object.__setattr__(
            self, "require_lifecycle", _require_bool("require_lifecycle", self.require_lifecycle)
        )
        object.__setattr__(
            self,
            "require_classification",
            _require_bool("require_classification", self.require_classification),
        )

    @property
    def fingerprint(self) -> str:
        payload = {
            "schema": _UNIVERSE_POLICY_SCHEMA,
            "require_membership": self.require_membership,
            "require_lifecycle": self.require_lifecycle,
            "require_classification": self.require_classification,
        }
        return _sha256(_canonical_json(payload))


@dataclass(frozen=True)
class FoldUniverseIntegrityEvidence:
    fold_id: str
    membership_resolutions: tuple[UniverseMembershipResolution, ...]
    lifecycle_resolutions: tuple[InstrumentLifecycleResolution, ...]
    classification_resolutions: tuple[ClassificationResolution, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "fold_id", _require_identity("fold_id", self.fold_id))
        object.__setattr__(
            self,
            "membership_resolutions",
            _require_tuple("membership_resolutions", self.membership_resolutions, UniverseMembershipResolution),
        )
        object.__setattr__(
            self,
            "lifecycle_resolutions",
            _require_tuple(
                "lifecycle_resolutions", self.lifecycle_resolutions, InstrumentLifecycleResolution
            ),
        )
        object.__setattr__(
            self,
            "classification_resolutions",
            _require_tuple(
                "classification_resolutions", self.classification_resolutions, ClassificationResolution
            ),
        )


@dataclass(frozen=True)
class WalkForwardFinding:
    code: WalkForwardFindingCode
    fold_id: str | None
    message: str

    def __post_init__(self) -> None:
        _require_enum("code", self.code, WalkForwardFindingCode)
        if self.fold_id is not None:
            object.__setattr__(self, "fold_id", _require_identity("fold_id", self.fold_id))
        object.__setattr__(self, "message", _require_nonempty_str("message", self.message))


@dataclass(frozen=True)
class FoldValidationResult:
    fold: WalkForwardFold
    status: FoldValidationStatus
    findings: tuple[WalkForwardFinding, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.fold, WalkForwardFold):
            raise ValueError(f"fold must be a WalkForwardFold instance, got {self.fold!r}")
        _require_enum("status", self.status, FoldValidationStatus)
        findings = _require_tuple("findings", self.findings, WalkForwardFinding)
        for finding in findings:
            if finding.fold_id != self.fold.fold_id:
                raise ValueError(
                    f"finding fold_id {finding.fold_id!r} does not match this result's fold_id "
                    f"{self.fold.fold_id!r}"
                )
        object.__setattr__(self, "findings", tuple(sorted(findings, key=_finding_sort_key)))

        derived = _derive_fold_status(self.findings)
        if self.status is not derived:
            raise ValueError(
                f"status {self.status.value!r} does not match the finding-derived status "
                f"{derived.value!r}"
            )


@dataclass(frozen=True)
class WalkForwardValidationReport:
    mode: WalkForwardMode
    parameter_selection_mode: ParameterSelectionMode
    fold_results: tuple[FoldValidationResult, ...]
    report_findings: tuple[WalkForwardFinding, ...]

    def __post_init__(self) -> None:
        _require_enum("mode", self.mode, WalkForwardMode)
        _require_enum("parameter_selection_mode", self.parameter_selection_mode, ParameterSelectionMode)
        fold_results = _require_tuple("fold_results", self.fold_results, FoldValidationResult)
        report_findings = _require_tuple("report_findings", self.report_findings, WalkForwardFinding)
        for finding in report_findings:
            if finding.fold_id is not None:
                raise ValueError(
                    f"report_findings must all have fold_id=None, got {finding.fold_id!r}"
                )
        object.__setattr__(
            self, "fold_results", tuple(sorted(fold_results, key=lambda r: _fold_sort_key(r.fold)))
        )
        object.__setattr__(
            self, "report_findings", tuple(sorted(report_findings, key=_finding_sort_key))
        )

    @property
    def total_fold_count(self) -> int:
        return len(self.fold_results)

    @property
    def valid_fold_count(self) -> int:
        return sum(1 for r in self.fold_results if r.status is FoldValidationStatus.VALID)

    @property
    def insufficient_data_fold_count(self) -> int:
        return sum(1 for r in self.fold_results if r.status is FoldValidationStatus.INSUFFICIENT_DATA)

    @property
    def leakage_risk_fold_count(self) -> int:
        return sum(1 for r in self.fold_results if r.status is FoldValidationStatus.LEAKAGE_RISK)

    @property
    def invalid_fold_count(self) -> int:
        return sum(1 for r in self.fold_results if r.status is FoldValidationStatus.INVALID)

    @property
    def performance_eligible_fold_ids(self) -> tuple[str, ...]:
        return tuple(
            r.fold.fold_id for r in self.fold_results if r.status is FoldValidationStatus.VALID
        )


# --------------------------------------------------------------------------
# Governed-component fingerprints -- see module docstring's binding section.
# --------------------------------------------------------------------------


def compute_window_configuration_fingerprint(
    *, mode: WalkForwardMode, folds: Sequence[WalkForwardFold]
) -> str:
    ordered = sorted(folds, key=_fold_sort_key)
    fold_rows = []
    for fold in ordered:
        fold_rows.append(
            {
                "fold_id": fold.fold_id,
                "train_start": canonical_utc_text(fold.train_interval.start),
                "train_end": canonical_utc_text(fold.train_interval.end),
                "validation_start": (
                    None
                    if fold.validation_interval is None
                    else canonical_utc_text(fold.validation_interval.start)
                ),
                "validation_end": (
                    None
                    if fold.validation_interval is None
                    else canonical_utc_text(fold.validation_interval.end)
                ),
                "oos_start": canonical_utc_text(fold.oos_interval.start),
                "oos_end": canonical_utc_text(fold.oos_interval.end),
            }
        )
    payload = {
        "schema": _WINDOW_CONFIGURATION_SCHEMA,
        "mode": mode.value,
        "folds": fold_rows,
    }
    return _sha256(_canonical_json(payload))


def compute_contamination_policy_fingerprint(
    *, parameter_selection_mode: ParameterSelectionMode
) -> str:
    payload = {
        "schema": _CONTAMINATION_POLICY_SCHEMA,
        "parameter_selection_mode": parameter_selection_mode.value,
        "cross_fold_oos_feedback": "forbidden",
    }
    return _sha256(_canonical_json(payload))


def compute_evaluation_protocol_fingerprint() -> str:
    payload = {
        "schema": _EVALUATION_PROTOCOL_SCHEMA,
        "protocol_version": _PROTOCOL_VERSION,
        "status_precedence_version": _STATUS_PRECEDENCE_VERSION,
        "finding_mapping_version": _FINDING_MAPPING_VERSION,
        "denominator_rule_version": _DENOMINATOR_RULE_VERSION,
    }
    return _sha256(_canonical_json(payload))


# --------------------------------------------------------------------------
# Evidence coverage -- order-invariant grouping by fold_id.
# --------------------------------------------------------------------------


def _resolve_evidence_coverage(
    items: Sequence[T],
    *,
    known_fold_ids: set[str],
    collection_name: str,
    id_of: Callable[[T], str],
) -> tuple[dict[str, T], list[WalkForwardFinding], dict[str, WalkForwardFinding]]:
    grouped: dict[str, list[T]] = {}
    for item in items:
        grouped.setdefault(id_of(item), []).append(item)

    resolved: dict[str, T] = {}
    unknown_findings: list[WalkForwardFinding] = []
    duplicate_findings: dict[str, WalkForwardFinding] = {}

    for fold_id, group in grouped.items():
        if fold_id not in known_fold_ids:
            unknown_findings.append(
                WalkForwardFinding(
                    code=WalkForwardFindingCode.EVIDENCE_FOLD_ID_UNKNOWN,
                    fold_id=None,
                    message=(
                        f"{collection_name} references unknown fold_id {fold_id!r} "
                        f"({len(group)} entries), which does not match any input fold"
                    ),
                )
            )
            continue
        if len(group) > 1:
            duplicate_findings[fold_id] = WalkForwardFinding(
                code=WalkForwardFindingCode.DUPLICATE_EVIDENCE_FOLD_ID,
                fold_id=fold_id,
                message=(
                    f"{collection_name} contains {len(group)} entries for fold_id {fold_id!r}, "
                    f"so no single entry can be treated as authoritative"
                ),
            )
            continue
        resolved[fold_id] = group[0]

    return resolved, unknown_findings, duplicate_findings


# --------------------------------------------------------------------------
# Fold-set-level geometry
# --------------------------------------------------------------------------


def _validate_geometry(
    mode: WalkForwardMode, folds: Sequence[WalkForwardFold]
) -> dict[int, list[WalkForwardFinding]]:
    findings_by_index: dict[int, list[WalkForwardFinding]] = {i: [] for i in range(len(folds))}

    id_positions: dict[str, list[int]] = {}
    for i, fold in enumerate(folds):
        id_positions.setdefault(fold.fold_id, []).append(i)
    for fold_id, positions in id_positions.items():
        if len(positions) > 1:
            for i in positions:
                findings_by_index[i].append(
                    WalkForwardFinding(
                        code=WalkForwardFindingCode.DUPLICATE_FOLD_ID,
                        fold_id=fold_id,
                        message=f"fold_id {fold_id!r} is used by {len(positions)} input folds",
                    )
                )

    for i, fold in enumerate(folds):
        if fold.validation_interval is None:
            if not (fold.train_interval.end <= fold.oos_interval.start):
                findings_by_index[i].append(
                    WalkForwardFinding(
                        code=WalkForwardFindingCode.INVALID_FOLD_GEOMETRY,
                        fold_id=fold.fold_id,
                        message="train_interval.end must be <= oos_interval.start when there is no validation interval",
                    )
                )
        else:
            ok = (
                fold.train_interval.end <= fold.validation_interval.start
                and fold.validation_interval.end <= fold.oos_interval.start
            )
            if not ok:
                findings_by_index[i].append(
                    WalkForwardFinding(
                        code=WalkForwardFindingCode.INVALID_FOLD_GEOMETRY,
                        fold_id=fold.fold_id,
                        message=(
                            "train_interval.end must be <= validation_interval.start and "
                            "validation_interval.end must be <= oos_interval.start"
                        ),
                    )
                )

    order = sorted(range(len(folds)), key=lambda i: _fold_sort_key(folds[i]))
    for pos in range(1, len(order)):
        prev_i, cur_i = order[pos - 1], order[pos]
        prev, cur = folds[prev_i], folds[cur_i]

        if mode is WalkForwardMode.EXPANDING:
            if cur.train_interval.start != prev.train_interval.start:
                findings_by_index[cur_i].append(
                    WalkForwardFinding(
                        code=WalkForwardFindingCode.INVALID_MODE_GEOMETRY,
                        fold_id=cur.fold_id,
                        message="EXPANDING requires an identical train_interval.start across all folds",
                    )
                )
            if not (cur.train_interval.end > prev.train_interval.end):
                findings_by_index[cur_i].append(
                    WalkForwardFinding(
                        code=WalkForwardFindingCode.INVALID_MODE_GEOMETRY,
                        fold_id=cur.fold_id,
                        message="EXPANDING requires strictly increasing train_interval.end in canonical order",
                    )
                )
        else:
            if not (cur.train_interval.start > prev.train_interval.start):
                findings_by_index[cur_i].append(
                    WalkForwardFinding(
                        code=WalkForwardFindingCode.INVALID_MODE_GEOMETRY,
                        fold_id=cur.fold_id,
                        message="ROLLING requires strictly increasing train_interval.start in canonical order",
                    )
                )
            if not (cur.train_interval.end > prev.train_interval.end):
                findings_by_index[cur_i].append(
                    WalkForwardFinding(
                        code=WalkForwardFindingCode.INVALID_MODE_GEOMETRY,
                        fold_id=cur.fold_id,
                        message="ROLLING requires strictly increasing train_interval.end in canonical order",
                    )
                )

        if not (cur.oos_interval.start > prev.oos_interval.start):
            findings_by_index[cur_i].append(
                WalkForwardFinding(
                    code=WalkForwardFindingCode.INVALID_MODE_GEOMETRY,
                    fold_id=cur.fold_id,
                    message="oos_interval.start must be strictly increasing in canonical order",
                )
            )

        if not (prev.oos_interval.end <= cur.oos_interval.start):
            findings_by_index[cur_i].append(
                WalkForwardFinding(
                    code=WalkForwardFindingCode.OOS_OVERLAP,
                    fold_id=cur.fold_id,
                    message="oos_interval overlaps the previous canonical fold's oos_interval",
                )
            )

    return findings_by_index


# --------------------------------------------------------------------------
# Per-fold evaluators
# --------------------------------------------------------------------------


def _evaluate_purge_and_embargo(
    fold: WalkForwardFold,
    information_dependency: InformationDependencyReport,
    separation: FoldSeparationEvidence | None,
) -> list[WalkForwardFinding]:
    findings: list[WalkForwardFinding] = []
    fold_id = fold.fold_id

    if (
        separation is not None
        and fold.validation_interval is None
        and separation.applied_train_to_validation_purge_bars is not None
    ):
        findings.append(
            WalkForwardFinding(
                code=WalkForwardFindingCode.INVALID_FOLD_GEOMETRY,
                fold_id=fold_id,
                message=(
                    "separation.applied_train_to_validation_purge_bars must be None when the "
                    "fold has no validation_interval"
                ),
            )
        )

    required_purge = information_dependency.required_purge_bars

    if required_purge is None:
        findings.append(
            WalkForwardFinding(
                code=WalkForwardFindingCode.PURGE_REQUIREMENT_UNRESOLVED,
                fold_id=fold_id,
                message="information_dependency.required_purge_bars is unresolved",
            )
        )

    if separation is None:
        findings.append(
            WalkForwardFinding(
                code=WalkForwardFindingCode.FOLD_EVIDENCE_MISSING,
                fold_id=fold_id,
                message="fold separation evidence is missing",
            )
        )
        return findings

    if required_purge is not None:
        label_grid = information_dependency.declaration.label.payload.bar_grid_id
        if separation.purge_bar_grid_id != label_grid:
            findings.append(
                WalkForwardFinding(
                    code=WalkForwardFindingCode.BAR_GRID_MISMATCH,
                    fold_id=fold_id,
                    message=(
                        f"separation.purge_bar_grid_id {separation.purge_bar_grid_id!r} does not "
                        f"match the declared label bar_grid_id {label_grid!r}"
                    ),
                )
            )
        else:
            fields = (
                [
                    (
                        "applied_train_to_validation_purge_bars",
                        separation.applied_train_to_validation_purge_bars,
                    ),
                    ("applied_pre_oos_purge_bars", separation.applied_pre_oos_purge_bars),
                ]
                if fold.validation_interval is not None
                else [("applied_pre_oos_purge_bars", separation.applied_pre_oos_purge_bars)]
            )
            for name, value in fields:
                if value is None:
                    findings.append(
                        WalkForwardFinding(
                            code=WalkForwardFindingCode.PURGE_APPLICATION_UNRESOLVED,
                            fold_id=fold_id,
                            message=f"separation.{name} is unresolved",
                        )
                    )
                elif value < required_purge:
                    findings.append(
                        WalkForwardFinding(
                            code=WalkForwardFindingCode.PURGE_INSUFFICIENT,
                            fold_id=fold_id,
                            message=(
                                f"separation.{name}={value} is less than the required "
                                f"{required_purge} purge bars"
                            ),
                        )
                    )

    if separation.applied_embargo_bars is None:
        findings.append(
            WalkForwardFinding(
                code=WalkForwardFindingCode.EMBARGO_APPLICATION_UNRESOLVED,
                fold_id=fold_id,
                message="separation.applied_embargo_bars is unresolved",
            )
        )

    return findings


def _evaluate_warmup(
    fold: WalkForwardFold,
    information_dependency: InformationDependencyReport,
    data: FoldDataEvidence | None,
) -> list[WalkForwardFinding]:
    findings: list[WalkForwardFinding] = []
    fold_id = fold.fold_id
    required_warmup = information_dependency.required_warmup_bars

    if required_warmup is None:
        findings.append(
            WalkForwardFinding(
                code=WalkForwardFindingCode.WARMUP_REQUIREMENT_UNRESOLVED,
                fold_id=fold_id,
                message="information_dependency.required_warmup_bars is unresolved",
            )
        )

    if data is None:
        findings.append(
            WalkForwardFinding(
                code=WalkForwardFindingCode.FOLD_EVIDENCE_MISSING,
                fold_id=fold_id,
                message="fold data evidence is missing",
            )
        )
        return findings

    if required_warmup is not None and required_warmup > 0:
        feature_set = information_dependency.declaration.feature_set
        if feature_set.status is DeclarationStatus.DECLARED:
            required_grid = feature_set.payload.evaluation_bar_grid_id
            grid_label = "evaluation"
        else:
            # feature_set cannot be UNDECLARED here: an undeclared feature set
            # leaves required_warmup_bars unresolved (None), which the guard
            # above already excludes. So feature_set is NOT_APPLICABLE and the
            # positive warmup is driven entirely by state -- the only
            # constructible source for a positive, resolved warmup with no
            # declared feature grid is a DECLARED COLD_START state, which the
            # closed StateDependency contract requires to carry its own
            # bar_grid_id whenever convergence_warmup_bars is positive.
            state = information_dependency.declaration.state
            required_grid = state.payload.bar_grid_id
            grid_label = "state"
        if data.bar_grid_id != required_grid:
            findings.append(
                WalkForwardFinding(
                    code=WalkForwardFindingCode.BAR_GRID_MISMATCH,
                    fold_id=fold_id,
                    message=(
                        f"data.bar_grid_id {data.bar_grid_id!r} does not match the declared "
                        f"{grid_label} bar_grid_id {required_grid!r}"
                    ),
                )
            )

    if data.usable_train_bars is None:
        findings.append(
            WalkForwardFinding(
                code=WalkForwardFindingCode.FOLD_EVIDENCE_MISSING,
                fold_id=fold_id,
                message="data.usable_train_bars is missing",
            )
        )
    elif required_warmup is not None and data.usable_train_bars < required_warmup:
        findings.append(
            WalkForwardFinding(
                code=WalkForwardFindingCode.TRAIN_WARMUP_INSUFFICIENT,
                fold_id=fold_id,
                message=(
                    f"data.usable_train_bars={data.usable_train_bars} is less than the required "
                    f"{required_warmup} warmup bars"
                ),
            )
        )

    return findings


def _evaluate_data_completeness(
    fold: WalkForwardFold, data: FoldDataEvidence | None
) -> list[WalkForwardFinding]:
    findings: list[WalkForwardFinding] = []
    if data is None:
        return findings
    fold_id = fold.fold_id

    if fold.validation_interval is None and data.usable_validation_bars is not None:
        findings.append(
            WalkForwardFinding(
                code=WalkForwardFindingCode.INVALID_FOLD_GEOMETRY,
                fold_id=fold_id,
                message="data.usable_validation_bars must be None when the fold has no validation_interval",
            )
        )

    if data.usable_validation_bars is None:
        if fold.validation_interval is not None:
            findings.append(
                WalkForwardFinding(
                    code=WalkForwardFindingCode.FOLD_EVIDENCE_MISSING,
                    fold_id=fold_id,
                    message="data.usable_validation_bars is missing for a fold with a validation interval",
                )
            )
    elif fold.validation_interval is not None and data.usable_validation_bars == 0:
        findings.append(
            WalkForwardFinding(
                code=WalkForwardFindingCode.VALIDATION_DATA_EMPTY,
                fold_id=fold_id,
                message="data.usable_validation_bars is 0",
            )
        )

    if data.usable_oos_bars is None:
        findings.append(
            WalkForwardFinding(
                code=WalkForwardFindingCode.FOLD_EVIDENCE_MISSING,
                fold_id=fold_id,
                message="data.usable_oos_bars is missing",
            )
        )
    elif data.usable_oos_bars == 0:
        findings.append(
            WalkForwardFinding(
                code=WalkForwardFindingCode.OOS_DATA_EMPTY,
                fold_id=fold_id,
                message="data.usable_oos_bars is 0",
            )
        )

    return findings


def _evaluate_universe_integrity(
    fold: WalkForwardFold,
    requirement: UniverseIntegrityRequirement,
    evidence: FoldUniverseIntegrityEvidence | None,
) -> list[WalkForwardFinding]:
    findings: list[WalkForwardFinding] = []
    fold_id = fold.fold_id

    domains = (
        (
            "membership",
            requirement.require_membership,
            () if evidence is None else evidence.membership_resolutions,
        ),
        (
            "lifecycle",
            requirement.require_lifecycle,
            () if evidence is None else evidence.lifecycle_resolutions,
        ),
        (
            "classification",
            requirement.require_classification,
            () if evidence is None else evidence.classification_resolutions,
        ),
    )
    for name, required, resolutions in domains:
        if not resolutions:
            if required:
                findings.append(
                    WalkForwardFinding(
                        code=WalkForwardFindingCode.UNIVERSE_INTEGRITY_EVIDENCE_MISSING,
                        fold_id=fold_id,
                        message=f"{name} universe integrity evidence is required but empty",
                    )
                )
            continue
        statuses = {r.status for r in resolutions}
        if UniverseIntegrityResolutionStatus.CONFLICT in statuses:
            findings.append(
                WalkForwardFinding(
                    code=WalkForwardFindingCode.UNIVERSE_INTEGRITY_CONFLICT,
                    fold_id=fold_id,
                    message=f"{name} universe integrity evidence contains a CONFLICT resolution",
                )
            )
        elif UniverseIntegrityResolutionStatus.INDETERMINATE in statuses:
            findings.append(
                WalkForwardFinding(
                    code=WalkForwardFindingCode.UNIVERSE_INTEGRITY_INDETERMINATE,
                    fold_id=fold_id,
                    message=f"{name} universe integrity evidence contains an INDETERMINATE resolution",
                )
            )

    return findings


def _manifest_binding_problems(
    manifest: ExperimentManifest,
    *,
    information_dependency_fp: str,
    universe_policy_fp: str,
    window_configuration_fp: str,
    contamination_policy_fp: str,
    evaluation_protocol_fp: str,
) -> list[tuple[WalkForwardFindingCode, str]]:
    checks = (
        ("information_dependency", information_dependency_fp, WalkForwardFindingCode.INFORMATION_DEPENDENCY_UNBOUND),
        ("universe_policy", universe_policy_fp, WalkForwardFindingCode.UNIVERSE_POLICY_UNBOUND),
        ("window_configuration", window_configuration_fp, WalkForwardFindingCode.WINDOW_CONFIGURATION_UNBOUND),
        ("contamination_policy", contamination_policy_fp, WalkForwardFindingCode.CONTAMINATION_POLICY_UNBOUND),
        ("evaluation_protocol", evaluation_protocol_fp, WalkForwardFindingCode.EVALUATION_PROTOCOL_UNBOUND),
    )
    problems: list[tuple[WalkForwardFindingCode, str]] = []
    for key, expected, code in checks:
        actual = manifest.governed_components.get(key)
        if actual is None or actual != expected:
            problems.append(
                (
                    code,
                    f"manifest.governed_components[{key!r}] is missing or does not match the "
                    f"expected fingerprint",
                )
            )
    return problems


# --------------------------------------------------------------------------
# Public entry point
# --------------------------------------------------------------------------


def validate_walk_forward(
    *,
    manifest: ExperimentManifest,
    mode: WalkForwardMode,
    parameter_selection_mode: ParameterSelectionMode,
    folds: Sequence[WalkForwardFold],
    information_dependency: InformationDependencyReport,
    lineage_audit: ExperimentLineageAudit,
    parameter_origin: ParameterOrigin | None = None,
    fixed_parameter_evidence: FixedParameterEvidence | None = None,
    fold_parameter_selection_evidence: Sequence[FoldParameterSelectionEvidence] = (),
    separation_evidence: Sequence[FoldSeparationEvidence] = (),
    data_evidence: Sequence[FoldDataEvidence] = (),
    universe_requirement: UniverseIntegrityRequirement,
    universe_integrity_evidence: Sequence[FoldUniverseIntegrityEvidence] = (),
) -> WalkForwardValidationReport:
    if not isinstance(manifest, ExperimentManifest):
        raise ValueError(f"manifest must be an ExperimentManifest instance, got {manifest!r}")
    _require_enum("mode", mode, WalkForwardMode)
    _require_enum("parameter_selection_mode", parameter_selection_mode, ParameterSelectionMode)
    if not isinstance(information_dependency, InformationDependencyReport):
        raise ValueError(
            f"information_dependency must be an InformationDependencyReport instance, "
            f"got {information_dependency!r}"
        )
    if not isinstance(lineage_audit, ExperimentLineageAudit):
        raise ValueError(
            f"lineage_audit must be an ExperimentLineageAudit instance, got {lineage_audit!r}"
        )
    if not isinstance(universe_requirement, UniverseIntegrityRequirement):
        raise ValueError(
            f"universe_requirement must be a UniverseIntegrityRequirement instance, "
            f"got {universe_requirement!r}"
        )

    folds = _require_tuple("folds", tuple(folds), WalkForwardFold)
    fold_parameter_selection_evidence = _require_tuple(
        "fold_parameter_selection_evidence",
        tuple(fold_parameter_selection_evidence),
        FoldParameterSelectionEvidence,
    )
    separation_evidence = _require_tuple(
        "separation_evidence", tuple(separation_evidence), FoldSeparationEvidence
    )
    data_evidence = _require_tuple("data_evidence", tuple(data_evidence), FoldDataEvidence)
    universe_integrity_evidence = _require_tuple(
        "universe_integrity_evidence",
        tuple(universe_integrity_evidence),
        FoldUniverseIntegrityEvidence,
    )

    n = len(folds)
    fold_ids = [fold.fold_id for fold in folds]
    known_fold_ids = set(fold_ids)

    findings_by_index: list[list[WalkForwardFinding]] = [[] for _ in range(n)]
    report_findings: list[WalkForwardFinding] = []

    def _broadcast(code: WalkForwardFindingCode, message: str) -> None:
        report_findings.append(WalkForwardFinding(code=code, fold_id=None, message=message))
        for i in range(n):
            findings_by_index[i].append(
                WalkForwardFinding(code=code, fold_id=fold_ids[i], message=message)
            )

    def _attach_to_id(fold_id: str, finding: WalkForwardFinding) -> None:
        for i in range(n):
            if fold_ids[i] == fold_id:
                findings_by_index[i].append(finding)

    # ---- experiment identity ----
    if manifest.experiment_id != lineage_audit.experiment_id:
        _broadcast(
            WalkForwardFindingCode.EXPERIMENT_IDENTITY_MISMATCH,
            f"manifest.experiment_id {manifest.experiment_id!r} does not match "
            f"lineage_audit.experiment_id {lineage_audit.experiment_id!r}",
        )

    # ---- fold-set geometry ----
    geometry_findings = _validate_geometry(mode, folds)
    for i, items in geometry_findings.items():
        findings_by_index[i].extend(items)

    if parameter_selection_mode is ParameterSelectionMode.TRAIN_VALIDATION:
        for i, fold in enumerate(folds):
            if fold.validation_interval is None:
                findings_by_index[i].append(
                    WalkForwardFinding(
                        code=WalkForwardFindingCode.VALIDATION_REQUIRED,
                        fold_id=fold.fold_id,
                        message="TRAIN_VALIDATION requires a validation_interval",
                    )
                )

    # ---- manifest governed-component binding ----
    window_fp = compute_window_configuration_fingerprint(mode=mode, folds=folds)
    contamination_fp = compute_contamination_policy_fingerprint(
        parameter_selection_mode=parameter_selection_mode
    )
    evaluation_fp = compute_evaluation_protocol_fingerprint()
    for code, message in _manifest_binding_problems(
        manifest,
        information_dependency_fp=information_dependency.contract_fingerprint,
        universe_policy_fp=universe_requirement.fingerprint,
        window_configuration_fp=window_fp,
        contamination_policy_fp=contamination_fp,
        evaluation_protocol_fp=evaluation_fp,
    ):
        _broadcast(code, message)

    # ---- lineage ----
    if lineage_audit.verdict is LineageAuditVerdict.VIOLATION:
        _broadcast(
            WalkForwardFindingCode.LINEAGE_VIOLATION, "experiment lineage audit verdict is VIOLATION"
        )
    elif lineage_audit.verdict is LineageAuditVerdict.INDETERMINATE:
        _broadcast(
            WalkForwardFindingCode.LINEAGE_INDETERMINATE,
            "experiment lineage audit verdict is INDETERMINATE",
        )

    # ---- information dependency completeness ----
    if information_dependency.completeness is CompletenessLevel.INCOMPLETE:
        _broadcast(
            WalkForwardFindingCode.INFORMATION_DEPENDENCY_INCOMPLETE,
            "information_dependency.completeness is INCOMPLETE",
        )
    elif information_dependency.completeness is CompletenessLevel.LIMITED_EXPRESSION:
        _broadcast(
            WalkForwardFindingCode.INFORMATION_DEPENDENCY_LIMITED,
            "information_dependency.completeness is LIMITED_EXPRESSION",
        )

    # ---- parameter provenance ----
    if parameter_selection_mode is ParameterSelectionMode.FIXED:
        if parameter_origin is None:
            _broadcast(
                WalkForwardFindingCode.PARAMETER_ORIGIN_REQUIRED,
                "parameter_origin is required for FIXED parameter selection",
            )
        if fixed_parameter_evidence is None:
            _broadcast(
                WalkForwardFindingCode.FIXED_EVIDENCE_REQUIRED,
                "fixed_parameter_evidence is required for FIXED parameter selection",
            )
        if fold_parameter_selection_evidence:
            _broadcast(
                WalkForwardFindingCode.FORBIDDEN_FOLD_SELECTION_EVIDENCE_UNDER_FIXED,
                "fold_parameter_selection_evidence must be empty for FIXED parameter selection",
            )

        if parameter_origin is not None and fixed_parameter_evidence is not None:
            if parameter_origin.parameter_hash != fixed_parameter_evidence.selected_parameter_hash:
                _broadcast(
                    WalkForwardFindingCode.PARAMETER_HASH_MISMATCH,
                    "parameter_origin.parameter_hash does not match "
                    "fixed_parameter_evidence.selected_parameter_hash",
                )
            if (
                parameter_origin.origin_type is ParameterOriginType.PRIOR_EXPERIMENT
                and parameter_origin.origin_experiment_id == manifest.experiment_id
            ):
                _broadcast(
                    WalkForwardFindingCode.PARAMETER_ORIGIN_SELF_REFERENCE,
                    "parameter_origin.origin_experiment_id references the current experiment",
                )
            # These two checks need an experiment-wide time boundary derived
            # from the fold set; with zero folds there is no boundary to
            # derive, and inventing one would be worse than not checking.
            if folds:
                experiment_data_boundary = min(fold.train_interval.start for fold in folds)
                if not (parameter_origin.information_horizon_end < experiment_data_boundary):
                    _broadcast(
                        WalkForwardFindingCode.PARAMETER_ORIGIN_INFORMATION_HORIZON_VIOLATION,
                        "parameter_origin.information_horizon_end is not strictly before the "
                        "experiment data boundary",
                    )
                if not (parameter_origin.declared_at < experiment_data_boundary):
                    _broadcast(
                        WalkForwardFindingCode.PARAMETER_ORIGIN_DECLARED_AT_VIOLATION,
                        "parameter_origin.declared_at is not strictly before the experiment "
                        "data boundary",
                    )
    else:
        resolved_selection, unknown, duplicates = _resolve_evidence_coverage(
            fold_parameter_selection_evidence,
            known_fold_ids=known_fold_ids,
            collection_name="fold_parameter_selection_evidence",
            id_of=lambda e: e.fold_id,
        )
        report_findings.extend(unknown)
        for fold_id, finding in duplicates.items():
            _attach_to_id(fold_id, finding)

        for i, fold in enumerate(folds):
            selection = None if fold.fold_id in duplicates else resolved_selection.get(fold.fold_id)
            if selection is None:
                findings_by_index[i].append(
                    WalkForwardFinding(
                        code=WalkForwardFindingCode.FOLD_EVIDENCE_MISSING,
                        fold_id=fold.fold_id,
                        message="fold parameter selection evidence is missing",
                    )
                )
                continue

            if parameter_selection_mode is ParameterSelectionMode.TRAIN_ONLY:
                boundary = fold.train_interval.end
                boundary_label = "train_interval.end"
            elif fold.validation_interval is not None:
                boundary = fold.validation_interval.end
                boundary_label = "validation_interval.end"
            else:
                boundary = None
                boundary_label = ""

            if boundary is not None:
                if not (selection.latest_selection_information_at < boundary):
                    findings_by_index[i].append(
                        WalkForwardFinding(
                            code=WalkForwardFindingCode.PARAMETER_SELECTION_OUTSIDE_ALLOWED_WINDOW,
                            fold_id=fold.fold_id,
                            message=(
                                f"latest_selection_information_at is not strictly before "
                                f"{boundary_label}"
                            ),
                        )
                    )
                if not (selection.latest_selection_information_at < selection.selection_completed_at):
                    findings_by_index[i].append(
                        WalkForwardFinding(
                            code=WalkForwardFindingCode.PARAMETER_SELECTION_OUTSIDE_ALLOWED_WINDOW,
                            fold_id=fold.fold_id,
                            message="latest_selection_information_at is not strictly before selection_completed_at",
                        )
                    )
                if not (selection.selection_completed_at < fold.oos_interval.start):
                    findings_by_index[i].append(
                        WalkForwardFinding(
                            code=WalkForwardFindingCode.OOS_PARAMETER_PEEK,
                            fold_id=fold.fold_id,
                            message="selection_completed_at is not strictly before oos_interval.start",
                        )
                    )

    # ---- separation / purge / embargo ----
    resolved_separation, unknown_sep, dup_sep = _resolve_evidence_coverage(
        separation_evidence,
        known_fold_ids=known_fold_ids,
        collection_name="separation_evidence",
        id_of=lambda e: e.fold_id,
    )
    report_findings.extend(unknown_sep)
    for fold_id, finding in dup_sep.items():
        _attach_to_id(fold_id, finding)
    for i, fold in enumerate(folds):
        separation = None if fold.fold_id in dup_sep else resolved_separation.get(fold.fold_id)
        findings_by_index[i].extend(_evaluate_purge_and_embargo(fold, information_dependency, separation))

    # ---- data / warmup ----
    resolved_data, unknown_data, dup_data = _resolve_evidence_coverage(
        data_evidence, known_fold_ids=known_fold_ids, collection_name="data_evidence", id_of=lambda e: e.fold_id
    )
    report_findings.extend(unknown_data)
    for fold_id, finding in dup_data.items():
        _attach_to_id(fold_id, finding)
    for i, fold in enumerate(folds):
        data = None if fold.fold_id in dup_data else resolved_data.get(fold.fold_id)
        findings_by_index[i].extend(_evaluate_warmup(fold, information_dependency, data))
        findings_by_index[i].extend(_evaluate_data_completeness(fold, data))

    # ---- universe integrity ----
    resolved_ui, unknown_ui, dup_ui = _resolve_evidence_coverage(
        universe_integrity_evidence,
        known_fold_ids=known_fold_ids,
        collection_name="universe_integrity_evidence",
        id_of=lambda e: e.fold_id,
    )
    report_findings.extend(unknown_ui)
    for fold_id, finding in dup_ui.items():
        _attach_to_id(fold_id, finding)
    for i, fold in enumerate(folds):
        ui_evidence = None if fold.fold_id in dup_ui else resolved_ui.get(fold.fold_id)
        findings_by_index[i].extend(_evaluate_universe_integrity(fold, universe_requirement, ui_evidence))

    # ---- assemble ----
    fold_results = tuple(
        FoldValidationResult(
            fold=fold,
            status=_derive_fold_status(findings_by_index[i]),
            findings=tuple(findings_by_index[i]),
        )
        for i, fold in enumerate(folds)
    )

    return WalkForwardValidationReport(
        mode=mode,
        parameter_selection_mode=parameter_selection_mode,
        fold_results=fold_results,
        report_findings=tuple(report_findings),
    )
