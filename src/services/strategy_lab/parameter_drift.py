"""Parameter Selection Identity Drift V0.1.

Measures cross-fold changes in selected parameter-set *identity*, using
opaque caller-supplied ``selected_parameter_hash`` evidence. It explicitly
does NOT measure parameter distance, numeric delta, directionality,
per-field drift, categorical distance, normalized movement, or any other
parameter-space magnitude.

Trust boundaries (V0.1 -- read this before relying on any drift metric):

1. ``selected_parameter_hash`` is opaque caller-supplied identity evidence.
2. The same hash means the caller declares the same selected parameter-set
   identity.
3. A different hash means the caller declares a different identity.
4. This module does NOT prove payload equality/difference.
5. This module cannot verify parameter-search-space consistency.
6. This module cannot verify hash canonicalization-policy consistency.
7. This module cannot prove that the separately supplied fold selection
   evidence is the exact evidence originally used to produce the
   ``WalkForwardValidationReport``. Evidence is bound only via the
   fold_id domain, fold eligibility (``FoldValidationStatus``) and the
   canonical fold order; a caller can swap hashes between folds without
   this module being able to detect it.

Mode semantics:

- ``FIXED``: there is no cross-fold selection process at all, so drift is
  ``NOT_APPLICABLE``. The fixed parameter hash is surfaced as context and
  every drift metric is ``None`` -- never a fake zero-drift measurement.
- ``TRAIN_ONLY`` / ``TRAIN_VALIDATION``: identical identity-drift logic.
  Only ``FoldValidationStatus.VALID`` folds contribute selection
  identities. A non-VALID fold does not break observable continuity but is
  counted on each generated transition as
  ``skipped_non_valid_fold_count``; a VALID fold whose selection evidence
  is missing DOES break continuity, and no transition is generated across
  the gap.

This module is a stdlib-only pure-compute leaf: it imports closed
Walk-Forward types directly, has no persistence/repository/SQLAlchemy
dependency, and has no algorithmic dependency on the Parameter Stability
Engine (scalar neighborhood robustness is a different question from
cross-fold selection-identity movement).
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any, Sequence

from .walk_forward import (
    FixedParameterEvidence,
    FoldParameterSelectionEvidence,
    FoldValidationResult,
    FoldValidationStatus,
    ParameterSelectionMode,
    WalkForwardValidationReport,
)

__all__ = [
    "ParameterDriftFinding",
    "ParameterDriftFindingCode",
    "ParameterDriftFoldObservation",
    "ParameterDriftReport",
    "ParameterDriftResolution",
    "ParameterDriftTransition",
    "evaluate_parameter_drift",
]


# --------------------------------------------------------------------------
# Frozen enums
# --------------------------------------------------------------------------


class ParameterDriftResolution(str, Enum):
    RESOLVED = "resolved"
    INSUFFICIENT_DATA = "insufficient_data"
    INCOMPLETE_EVIDENCE = "incomplete_evidence"
    NOT_APPLICABLE = "not_applicable"


class ParameterDriftFindingCode(str, Enum):
    FIXED_MODE_NOT_APPLICABLE = "fixed_mode_not_applicable"
    VALID_FOLD_SELECTION_EVIDENCE_MISSING = "valid_fold_selection_evidence_missing"
    INSUFFICIENT_OBSERVED_SELECTIONS = "insufficient_observed_selections"
    NON_VALID_SELECTION_EVIDENCE_IGNORED = "non_valid_selection_evidence_ignored"


# --------------------------------------------------------------------------
# Private validators (module-local, mirroring closed-module conventions)
# --------------------------------------------------------------------------


def _require_nonempty_str(label: str, value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty string, got {value!r}")
    return value


def _require_enum(label: str, value: Any, enum_type: type[Enum]) -> Enum:
    if not isinstance(value, enum_type):
        raise ValueError(f"{label} must be a {enum_type.__name__} instance, got {value!r}")
    return value


def _require_bool(label: str, value: Any) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{label} must be a bool, got {value!r}")
    return value


def _require_nonneg_int(label: str, value: Any) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(f"{label} must be a non-negative int, got {value!r}")
    return value


def _require_fold_id(label: str, value: Any) -> str:
    return _require_nonempty_str(label, value)


# --------------------------------------------------------------------------
# Frozen dataclasses
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class ParameterDriftFinding:
    code: ParameterDriftFindingCode
    fold_id: str | None
    message: str

    def __post_init__(self) -> None:
        _require_enum("code", self.code, ParameterDriftFindingCode)
        if self.fold_id is not None:
            object.__setattr__(self, "fold_id", _require_fold_id("fold_id", self.fold_id))
        object.__setattr__(self, "message", _require_nonempty_str("message", self.message))


@dataclass(frozen=True)
class ParameterDriftFoldObservation:
    fold_id: str
    fold_status: FoldValidationStatus
    selected_parameter_hash: str | None
    selection_evidence_supplied: bool

    def __post_init__(self) -> None:
        object.__setattr__(self, "fold_id", _require_fold_id("fold_id", self.fold_id))
        _require_enum("fold_status", self.fold_status, FoldValidationStatus)
        if self.selected_parameter_hash is not None:
            object.__setattr__(
                self,
                "selected_parameter_hash",
                _require_nonempty_str("selected_parameter_hash", self.selected_parameter_hash),
            )
        _require_bool("selection_evidence_supplied", self.selection_evidence_supplied)
        if self.selected_parameter_hash is not None and not self.selection_evidence_supplied:
            raise ValueError(
                "selected_parameter_hash is present but selection_evidence_supplied is False"
            )


@dataclass(frozen=True)
class ParameterDriftTransition:
    from_fold_id: str
    to_fold_id: str
    from_parameter_hash: str
    to_parameter_hash: str
    changed: bool
    skipped_non_valid_fold_count: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "from_fold_id", _require_fold_id("from_fold_id", self.from_fold_id))
        object.__setattr__(self, "to_fold_id", _require_fold_id("to_fold_id", self.to_fold_id))
        object.__setattr__(
            self, "from_parameter_hash", _require_nonempty_str("from_parameter_hash", self.from_parameter_hash)
        )
        object.__setattr__(
            self, "to_parameter_hash", _require_nonempty_str("to_parameter_hash", self.to_parameter_hash)
        )
        object.__setattr__(
            self,
            "skipped_non_valid_fold_count",
            _require_nonneg_int("skipped_non_valid_fold_count", self.skipped_non_valid_fold_count),
        )
        _require_bool("changed", self.changed)
        expected_changed = self.from_parameter_hash != self.to_parameter_hash
        if self.changed != expected_changed:
            raise ValueError(
                f"changed {self.changed!r} does not match from/to hash identity comparison"
            )


@dataclass(frozen=True)
class ParameterDriftReport:
    resolution: ParameterDriftResolution
    parameter_selection_mode: ParameterSelectionMode

    total_fold_count: int
    valid_fold_count: int
    non_valid_fold_count: int

    observed_selection_count: int
    missing_valid_selection_count: int
    ignored_non_valid_selection_evidence_count: int

    transition_opportunity_count: int | None
    transition_count: int | None
    transition_rate: float | None

    unique_parameter_hash_count: int | None
    longest_observed_stable_run: int | None

    fixed_parameter_hash: str | None

    fold_observations: tuple[ParameterDriftFoldObservation, ...]
    transitions: tuple[ParameterDriftTransition, ...]
    findings: tuple[ParameterDriftFinding, ...]

    def __post_init__(self) -> None:
        _require_enum("resolution", self.resolution, ParameterDriftResolution)
        _require_enum(
            "parameter_selection_mode", self.parameter_selection_mode, ParameterSelectionMode
        )
        for label in (
            "total_fold_count",
            "valid_fold_count",
            "non_valid_fold_count",
            "observed_selection_count",
            "missing_valid_selection_count",
            "ignored_non_valid_selection_evidence_count",
        ):
            _require_nonneg_int(label, getattr(self, label))
        object.__setattr__(
            self,
            "fold_observations",
            tuple(_require_tuple_entries("fold_observations", self.fold_observations, ParameterDriftFoldObservation)),
        )
        object.__setattr__(
            self,
            "transitions",
            tuple(_require_tuple_entries("transitions", self.transitions, ParameterDriftTransition)),
        )
        object.__setattr__(
            self,
            "findings",
            tuple(
                sorted(
                    _require_tuple_entries("findings", self.findings, ParameterDriftFinding),
                    key=lambda f: (f.code.value, f.fold_id or "", f.message),
                )
            ),
        )

        if self.total_fold_count != self.valid_fold_count + self.non_valid_fold_count:
            raise ValueError(
                "total_fold_count must equal valid_fold_count + non_valid_fold_count"
            )

        is_fixed = self.parameter_selection_mode is ParameterSelectionMode.FIXED
        if is_fixed:
            if self.resolution is not ParameterDriftResolution.NOT_APPLICABLE:
                raise ValueError("FIXED mode requires resolution NOT_APPLICABLE")
            if self.fixed_parameter_hash is None:
                raise ValueError("FIXED mode requires fixed_parameter_hash")
            object.__setattr__(
                self, "fixed_parameter_hash",
                _require_nonempty_str("fixed_parameter_hash", self.fixed_parameter_hash),
            )
            if (
                self.transition_opportunity_count is not None
                or self.transition_count is not None
                or self.transition_rate is not None
                or self.unique_parameter_hash_count is not None
                or self.longest_observed_stable_run is not None
            ):
                raise ValueError("FIXED mode requires all drift metrics to be None")
            if self.fold_observations or self.transitions:
                raise ValueError("FIXED mode requires empty fold_observations and transitions")
            if (
                self.observed_selection_count != 0
                or self.missing_valid_selection_count != 0
                or self.ignored_non_valid_selection_evidence_count != 0
            ):
                raise ValueError(
                    "FIXED mode has no per-fold selection process; observation counts must be 0"
                )
            return

        # TRAIN_ONLY / TRAIN_VALIDATION
        if self.fixed_parameter_hash is not None:
            raise ValueError("TRAIN modes require fixed_parameter_hash to be None")
        if self.observed_selection_count + self.missing_valid_selection_count != self.valid_fold_count:
            raise ValueError(
                "observed_selection_count + missing_valid_selection_count must equal valid_fold_count"
            )
        opportunity = self.transition_opportunity_count
        count = self.transition_count
        if opportunity is None or count is None:
            raise ValueError("TRAIN modes require transition counts to be ints, not None")
        _require_nonneg_int("transition_opportunity_count", opportunity)
        _require_nonneg_int("transition_count", count)
        if opportunity != len(self.transitions):
            raise ValueError("transition_opportunity_count must equal len(transitions)")
        if count != sum(1 for t in self.transitions if t.changed):
            raise ValueError("transition_count must equal the number of changed transitions")
        if opportunity == 0:
            if self.transition_rate is not None:
                raise ValueError("transition_rate must be None when no opportunity exists")
        else:
            expected_rate = count / opportunity
            if self.transition_rate != expected_rate:
                raise ValueError(
                    f"transition_rate {self.transition_rate!r} does not match "
                    f"{count} / {opportunity} = {expected_rate!r}"
                )
        unique = self.unique_parameter_hash_count
        if unique is None:
            raise ValueError("TRAIN modes require unique_parameter_hash_count to be an int")
        _require_nonneg_int("unique_parameter_hash_count", unique)
        if self.observed_selection_count == 0:
            if unique != 0:
                raise ValueError("unique_parameter_hash_count must be 0 with no observed selections")
            if self.longest_observed_stable_run is not None:
                raise ValueError(
                    "longest_observed_stable_run must be None with no observed selections"
                )
        else:
            longest = self.longest_observed_stable_run
            if longest is None:
                raise ValueError(
                    "longest_observed_stable_run must be an int when selections are observed"
                )
            _require_nonneg_int("longest_observed_stable_run", longest)
            if longest < 1:
                raise ValueError("longest_observed_stable_run must be at least 1 when observed")


def _require_tuple_entries(label: str, value: Any, entry_type: type[Any]) -> tuple[Any, ...]:
    if not isinstance(value, tuple):
        raise ValueError(f"{label} must be a tuple, got {value!r}")
    for entry in value:
        if not isinstance(entry, entry_type):
            raise ValueError(
                f"{label} must contain only {entry_type.__name__} entries, got {entry!r}"
            )
    return value


# --------------------------------------------------------------------------
# Canonical ordering helpers (geometry-first, defensive)
# --------------------------------------------------------------------------


def _canonical_fold_sort_key(result: FoldValidationResult) -> tuple[Any, Any, str]:
    return (result.fold.oos_interval.start, result.fold.train_interval.start, result.fold.fold_id)


def _finding_sort_key(finding: ParameterDriftFinding) -> tuple[str, str, str]:
    return (finding.code.value, finding.fold_id or "", finding.message)


# --------------------------------------------------------------------------
# Public entry point
# --------------------------------------------------------------------------


def evaluate_parameter_drift(
    *,
    walk_forward_report: WalkForwardValidationReport,
    fold_parameter_selection_evidence: Sequence[FoldParameterSelectionEvidence] = (),
    fixed_parameter_evidence: FixedParameterEvidence | None = None,
) -> ParameterDriftReport:
    """Evaluate cross-fold selected parameter-set identity drift.

    Structural misuse of the input contract (duplicate/unknown fold ids,
    mode-incompatible evidence) raises ``ValueError``; it is never folded
    into a drift resolution. See the module docstring for the trust
    boundaries -- in particular this module cannot prove the supplied
    evidence is the exact evidence used to produce the Walk-Forward report.
    """

    if not isinstance(walk_forward_report, WalkForwardValidationReport):
        raise ValueError(
            f"walk_forward_report must be a WalkForwardValidationReport instance, "
            f"got {walk_forward_report!r}"
        )

    # Defensive canonical ordering: never trust input order.
    results = sorted(walk_forward_report.fold_results, key=_canonical_fold_sort_key)

    fold_ids = [result.fold.fold_id for result in results]
    if len(set(fold_ids)) != len(fold_ids):
        raise ValueError("walk_forward_report contains duplicate fold_id entries")

    if fixed_parameter_evidence is not None and not isinstance(fixed_parameter_evidence, FixedParameterEvidence):
        raise ValueError(
            f"fixed_parameter_evidence must be a FixedParameterEvidence instance, "
            f"got {fixed_parameter_evidence!r}"
        )

    mode = walk_forward_report.parameter_selection_mode

    if mode is ParameterSelectionMode.FIXED:
        return _evaluate_fixed(
            results=results,
            fold_parameter_selection_evidence=fold_parameter_selection_evidence,
            fixed_parameter_evidence=fixed_parameter_evidence,
        )
    return _evaluate_train(
        mode=mode,
        results=results,
        fold_parameter_selection_evidence=fold_parameter_selection_evidence,
        fixed_parameter_evidence=fixed_parameter_evidence,
    )


def _evaluate_fixed(
    *,
    results: Sequence[FoldValidationResult],
    fold_parameter_selection_evidence: Sequence[FoldParameterSelectionEvidence],
    fixed_parameter_evidence: FixedParameterEvidence | None,
) -> ParameterDriftReport:
    if fold_parameter_selection_evidence:
        raise ValueError(
            "fold_parameter_selection_evidence must be empty for FIXED parameter selection"
        )
    if fixed_parameter_evidence is None:
        raise ValueError("fixed_parameter_evidence is required for FIXED parameter selection")

    total = len(results)
    valid = sum(1 for r in results if r.status is FoldValidationStatus.VALID)
    return ParameterDriftReport(
        resolution=ParameterDriftResolution.NOT_APPLICABLE,
        parameter_selection_mode=ParameterSelectionMode.FIXED,
        total_fold_count=total,
        valid_fold_count=valid,
        non_valid_fold_count=total - valid,
        observed_selection_count=0,
        missing_valid_selection_count=0,
        ignored_non_valid_selection_evidence_count=0,
        transition_opportunity_count=None,
        transition_count=None,
        transition_rate=None,
        unique_parameter_hash_count=None,
        longest_observed_stable_run=None,
        fixed_parameter_hash=fixed_parameter_evidence.selected_parameter_hash,
        fold_observations=(),
        transitions=(),
        findings=(
            ParameterDriftFinding(
                code=ParameterDriftFindingCode.FIXED_MODE_NOT_APPLICABLE,
                fold_id=None,
                message=(
                    "FIXED parameter selection performs no cross-fold selection process; "
                    "identity drift is not applicable and no drift metric is computed"
                ),
            ),
        ),
    )


def _evaluate_train(
    *,
    mode: ParameterSelectionMode,
    results: Sequence[FoldValidationResult],
    fold_parameter_selection_evidence: Sequence[FoldParameterSelectionEvidence],
    fixed_parameter_evidence: FixedParameterEvidence | None,
) -> ParameterDriftReport:
    if fixed_parameter_evidence is not None:
        raise ValueError("fixed_parameter_evidence must be None for TRAIN_ONLY/TRAIN_VALIDATION")

    evidence_by_fold: dict[str, FoldParameterSelectionEvidence] = {}
    for evidence in fold_parameter_selection_evidence:
        if not isinstance(evidence, FoldParameterSelectionEvidence):
            raise ValueError(
                f"fold_parameter_selection_evidence must contain only "
                f"FoldParameterSelectionEvidence entries, got {evidence!r}"
            )
        if evidence.fold_id in evidence_by_fold:
            raise ValueError(
                f"duplicate fold_parameter_selection_evidence fold_id {evidence.fold_id!r}"
            )
        evidence_by_fold[evidence.fold_id] = evidence

    known_fold_ids = {result.fold.fold_id for result in results}
    for fold_id in evidence_by_fold:
        if fold_id not in known_fold_ids:
            raise ValueError(
                f"fold_parameter_selection_evidence references unknown fold_id {fold_id!r}"
            )

    findings: list[ParameterDriftFinding] = []
    observations: list[ParameterDriftFoldObservation] = []
    observed = 0
    missing_valid = 0
    ignored_non_valid = 0

    for result in results:
        fold_id = result.fold.fold_id
        evidence = evidence_by_fold.get(fold_id)
        if result.status is FoldValidationStatus.VALID:
            if evidence is None:
                observations.append(
                    ParameterDriftFoldObservation(
                        fold_id=fold_id,
                        fold_status=FoldValidationStatus.VALID,
                        selected_parameter_hash=None,
                        selection_evidence_supplied=False,
                    )
                )
                missing_valid += 1
                findings.append(
                    ParameterDriftFinding(
                        code=ParameterDriftFindingCode.VALID_FOLD_SELECTION_EVIDENCE_MISSING,
                        fold_id=fold_id,
                        message=(
                            f"fold {fold_id!r} is VALID but no selection evidence was supplied"
                        ),
                    )
                )
            else:
                observations.append(
                    ParameterDriftFoldObservation(
                        fold_id=fold_id,
                        fold_status=FoldValidationStatus.VALID,
                        selected_parameter_hash=evidence.selected_parameter_hash,
                        selection_evidence_supplied=True,
                    )
                )
                observed += 1
        else:
            if evidence is not None:
                # Auditability only: the supplied hash is retained on the
                # observation but must never enter drift metrics.
                observations.append(
                    ParameterDriftFoldObservation(
                        fold_id=fold_id,
                        fold_status=result.status,
                        selected_parameter_hash=evidence.selected_parameter_hash,
                        selection_evidence_supplied=True,
                    )
                )
                ignored_non_valid += 1
                findings.append(
                    ParameterDriftFinding(
                        code=ParameterDriftFindingCode.NON_VALID_SELECTION_EVIDENCE_IGNORED,
                        fold_id=fold_id,
                        message=(
                            f"fold {fold_id!r} is not VALID; its supplied selection evidence "
                            f"is excluded from drift metrics"
                        ),
                    )
                )
            else:
                observations.append(
                    ParameterDriftFoldObservation(
                        fold_id=fold_id,
                        fold_status=result.status,
                        selected_parameter_hash=None,
                        selection_evidence_supplied=False,
                    )
                )

    # Transition generation over observable continuity.
    transitions: list[ParameterDriftTransition] = []
    current_fold_id: str | None = None
    current_hash: str | None = None
    skipped_since_current = 0
    current_run_hash: str | None = None
    current_run_length = 0
    longest_run = 0
    unique_hashes: set[str] = set()

    for result in results:
        fold_id = result.fold.fold_id
        evidence = evidence_by_fold.get(fold_id)
        if result.status is FoldValidationStatus.VALID and evidence is not None:
            unique_hashes.add(evidence.selected_parameter_hash)
            if current_fold_id is not None:
                transitions.append(
                    ParameterDriftTransition(
                        from_fold_id=current_fold_id,
                        to_fold_id=fold_id,
                        from_parameter_hash=current_hash,
                        to_parameter_hash=evidence.selected_parameter_hash,
                        changed=current_hash != evidence.selected_parameter_hash,
                        skipped_non_valid_fold_count=skipped_since_current,
                    )
                )
            current_fold_id = fold_id
            current_hash = evidence.selected_parameter_hash
            skipped_since_current = 0
            # Stable-run tracking: only VALID-missing breaks a run.
            if current_run_hash == evidence.selected_parameter_hash:
                current_run_length += 1
            else:
                current_run_hash = evidence.selected_parameter_hash
                current_run_length = 1
            longest_run = max(longest_run, current_run_length)
        elif result.status is FoldValidationStatus.VALID:
            # VALID + missing evidence: break observable continuity and runs.
            current_fold_id = None
            current_hash = None
            skipped_since_current = 0
            current_run_hash = None
            current_run_length = 0
        else:
            # Non-VALID: does not break continuity, does not break runs.
            skipped_since_current += 1

    opportunity = len(transitions)
    count = sum(1 for t in transitions if t.changed)
    rate = None if opportunity == 0 else count / opportunity

    if missing_valid > 0:
        resolution = ParameterDriftResolution.INCOMPLETE_EVIDENCE
    elif observed < 2:
        resolution = ParameterDriftResolution.INSUFFICIENT_DATA
        findings.append(
            ParameterDriftFinding(
                code=ParameterDriftFindingCode.INSUFFICIENT_OBSERVED_SELECTIONS,
                fold_id=None,
                message=(
                    "fewer than 2 observable selections; transition metrics cannot be computed"
                ),
            )
        )
    else:
        resolution = ParameterDriftResolution.RESOLVED

    total = len(results)
    valid = sum(1 for r in results if r.status is FoldValidationStatus.VALID)
    return ParameterDriftReport(
        resolution=resolution,
        parameter_selection_mode=mode,
        total_fold_count=total,
        valid_fold_count=valid,
        non_valid_fold_count=total - valid,
        observed_selection_count=observed,
        missing_valid_selection_count=missing_valid,
        ignored_non_valid_selection_evidence_count=ignored_non_valid,
        transition_opportunity_count=opportunity,
        transition_count=count,
        transition_rate=rate,
        unique_parameter_hash_count=len(unique_hashes),
        longest_observed_stable_run=None if observed == 0 else longest_run,
        fixed_parameter_hash=None,
        fold_observations=tuple(observations),
        transitions=tuple(transitions),
        findings=tuple(sorted(findings, key=_finding_sort_key)),
    )
