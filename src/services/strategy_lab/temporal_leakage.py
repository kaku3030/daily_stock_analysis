"""Implementation-level temporal leakage audits for Strategy Lab V0.1.

This module complements the declarative temporal contracts already present in
Strategy Lab.  A caller can declare honest-looking timestamps while an
indicator or signal implementation still reads future rows (for example via a
negative shift, an unbounded whole-series aggregate, or a future fill).  The
prefix-invariance audit detects that class of defect behaviorally:

1. evaluate the implementation once with the full history;
2. re-evaluate it with an exact prefix ending at an audited cutoff; and
3. compare the output at that cutoff.

If data after the cutoff changes an output that should already be fixed at the
cutoff, the implementation is future-dependent.

A separate startup-history sensitivity audit reruns the same endpoint with
multiple history lengths.  That detects recursive/warmup instability but does
*not* call it look-ahead by itself.  Keeping the two diagnoses separate avoids
turning an insufficient-warmup problem into a false accusation of future data
access.

The harness is framework-neutral and stdlib-only.  Evaluators return one
snapshot per input row.  Snapshot values are deliberately restricted to
simple finite scalar values and compared exactly.  Callers that need a numeric
tolerance must canonicalize/round inside their evaluator so the comparison
policy is explicit rather than a hidden Strategy Lab threshold.

A PASS certifies only the requested cutoffs/history lengths exercised by this
audit.  It is never proof that no other path, signal, market regime, or cutoff
can leak.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from math import isfinite
from typing import Any, Callable, Iterable, Mapping, Sequence, TypeAlias, TypeVar

from .validation_models import GateResult


Scalar: TypeAlias = str | int | float | bool | None
Snapshot: TypeAlias = Mapping[str, Scalar]
NormalizedSnapshot: TypeAlias = tuple[tuple[str, Scalar], ...]
T = TypeVar("T")
TemporalEvaluator: TypeAlias = Callable[[Sequence[T]], Iterable[Snapshot]]


class TemporalLeakageStatus(str, Enum):
    PASS = "pass"
    LEAKAGE_DETECTED = "leakage_detected"
    INDETERMINATE = "indeterminate"


class StartupSensitivityStatus(str, Enum):
    STABLE = "stable"
    SENSITIVITY_DETECTED = "sensitivity_detected"
    INDETERMINATE = "indeterminate"


class TemporalAuditFindingCode(str, Enum):
    OUTPUT_CHANGED_WITH_FUTURE_TAIL = "output_changed_with_future_tail"
    OUTPUT_CHANGED_WITH_STARTUP_HISTORY = "output_changed_with_startup_history"
    EVALUATOR_ERROR = "evaluator_error"
    OUTPUT_CONTRACT_ERROR = "output_contract_error"
    OUTPUT_LENGTH_MISMATCH = "output_length_mismatch"


@dataclass(frozen=True)
class TemporalAuditFinding:
    code: TemporalAuditFindingCode
    message: str
    cutoff: int | None = None
    history_length: int | None = None
    changed_fields: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not self.message.strip():
            raise ValueError("finding message must not be empty")
        if self.cutoff is not None and self.cutoff < 0:
            raise ValueError("finding cutoff must be non-negative")
        if self.history_length is not None and self.history_length <= 0:
            raise ValueError("finding history_length must be positive")


@dataclass(frozen=True)
class TemporalLeakageReport:
    status: TemporalLeakageStatus
    total_history_rows: int
    requested_cutoffs: tuple[int, ...]
    audited_cutoffs: tuple[int, ...]
    findings: tuple[TemporalAuditFinding, ...]

    def __post_init__(self) -> None:
        if self.total_history_rows < 2:
            raise ValueError("total_history_rows must be at least 2")
        if not self.requested_cutoffs:
            raise ValueError("requested_cutoffs must not be empty")
        if not set(self.audited_cutoffs).issubset(self.requested_cutoffs):
            raise ValueError("audited_cutoffs must be a subset of requested_cutoffs")


@dataclass(frozen=True)
class StartupSensitivityReport:
    status: StartupSensitivityStatus
    target_index: int
    requested_history_lengths: tuple[int, ...]
    audited_history_lengths: tuple[int, ...]
    findings: tuple[TemporalAuditFinding, ...]

    def __post_init__(self) -> None:
        if self.target_index < 0:
            raise ValueError("target_index must be non-negative")
        if len(self.requested_history_lengths) < 2:
            raise ValueError("at least two requested history lengths are required")
        if not set(self.audited_history_lengths).issubset(self.requested_history_lengths):
            raise ValueError(
                "audited_history_lengths must be a subset of requested_history_lengths"
            )


def audit_prefix_invariance(
    *,
    history: Sequence[T],
    evaluator: TemporalEvaluator[T],
    cutoffs: Sequence[int],
) -> TemporalLeakageReport:
    """Detect future-dependent implementation output using prefix invariance.

    ``evaluator`` receives a history slice and must return exactly one snapshot
    per input row.  For each requested cutoff ``c`` this function compares the
    full-history output at row ``c`` with the final output produced when the
    evaluator sees only ``history[:c + 1]``.

    Every cutoff must leave at least one future row hidden (``c < len(history)-1``);
    auditing the final row would be a vacuous comparison with no future tail.
    Malformed inputs raise ``ValueError``.  Evaluator/runtime/output-contract
    failures are audit evidence and produce ``INDETERMINATE`` rather than a
    false PASS.  A definite mismatch dominates indeterminate findings and
    yields ``LEAKAGE_DETECTED``.
    """

    rows = _require_history(history, minimum_size=2)
    requested = _normalize_cutoffs(cutoffs, len(rows))
    if not callable(evaluator):
        raise ValueError("evaluator must be callable")

    baseline, baseline_finding = _run_evaluator(
        evaluator=evaluator,
        history=rows,
        expected_length=len(rows),
        context="full-history baseline",
    )
    if baseline_finding is not None:
        return TemporalLeakageReport(
            status=TemporalLeakageStatus.INDETERMINATE,
            total_history_rows=len(rows),
            requested_cutoffs=requested,
            audited_cutoffs=(),
            findings=(baseline_finding,),
        )
    assert baseline is not None

    audited: list[int] = []
    findings: list[TemporalAuditFinding] = []
    leakage_found = False

    for cutoff in requested:
        prefix = rows[: cutoff + 1]
        prefix_outputs, finding = _run_evaluator(
            evaluator=evaluator,
            history=prefix,
            expected_length=len(prefix),
            context=f"prefix ending at cutoff {cutoff}",
            cutoff=cutoff,
        )
        if finding is not None:
            findings.append(finding)
            continue
        assert prefix_outputs is not None

        audited.append(cutoff)
        full_snapshot = baseline[cutoff]
        prefix_snapshot = prefix_outputs[-1]
        if full_snapshot != prefix_snapshot:
            leakage_found = True
            changed = _changed_fields(full_snapshot, prefix_snapshot)
            findings.append(
                TemporalAuditFinding(
                    code=TemporalAuditFindingCode.OUTPUT_CHANGED_WITH_FUTURE_TAIL,
                    cutoff=cutoff,
                    changed_fields=changed,
                    message=(
                        "output at cutoff changed when rows after the cutoff were hidden"
                    ),
                )
            )

    if leakage_found:
        status = TemporalLeakageStatus.LEAKAGE_DETECTED
    elif len(audited) != len(requested) or findings:
        status = TemporalLeakageStatus.INDETERMINATE
    else:
        status = TemporalLeakageStatus.PASS

    return TemporalLeakageReport(
        status=status,
        total_history_rows=len(rows),
        requested_cutoffs=requested,
        audited_cutoffs=tuple(audited),
        findings=tuple(findings),
    )


def audit_startup_history_sensitivity(
    *,
    history: Sequence[T],
    evaluator: TemporalEvaluator[T],
    target_index: int,
    history_lengths: Sequence[int],
) -> StartupSensitivityReport:
    """Detect endpoint sensitivity to how much prior history was supplied.

    Every run ends at ``target_index`` but starts at a different earlier row.
    The longest requested history is the reference.  A mismatch is reported as
    startup-history sensitivity, not look-ahead.  This is suitable for
    diagnosing warmup/recursive instability before deciding whether more
    history or a strategy-specific fix is required.
    """

    rows = _require_history(history, minimum_size=2)
    if isinstance(target_index, bool) or not isinstance(target_index, int):
        raise ValueError("target_index must be an int")
    if target_index < 0 or target_index >= len(rows):
        raise ValueError("target_index is outside history")
    if not callable(evaluator):
        raise ValueError("evaluator must be callable")

    lengths = _normalize_history_lengths(history_lengths, target_index + 1)
    reference_length = max(lengths)
    reference_slice = rows[target_index + 1 - reference_length : target_index + 1]
    reference_outputs, reference_finding = _run_evaluator(
        evaluator=evaluator,
        history=reference_slice,
        expected_length=reference_length,
        context=f"startup reference length {reference_length}",
        history_length=reference_length,
    )
    if reference_finding is not None:
        return StartupSensitivityReport(
            status=StartupSensitivityStatus.INDETERMINATE,
            target_index=target_index,
            requested_history_lengths=lengths,
            audited_history_lengths=(),
            findings=(reference_finding,),
        )
    assert reference_outputs is not None
    reference_snapshot = reference_outputs[-1]

    audited: list[int] = [reference_length]
    findings: list[TemporalAuditFinding] = []
    sensitivity_found = False

    for history_length in lengths:
        if history_length == reference_length:
            continue
        window = rows[target_index + 1 - history_length : target_index + 1]
        outputs, finding = _run_evaluator(
            evaluator=evaluator,
            history=window,
            expected_length=history_length,
            context=f"startup history length {history_length}",
            history_length=history_length,
        )
        if finding is not None:
            findings.append(finding)
            continue
        assert outputs is not None

        audited.append(history_length)
        snapshot = outputs[-1]
        if snapshot != reference_snapshot:
            sensitivity_found = True
            changed = _changed_fields(reference_snapshot, snapshot)
            findings.append(
                TemporalAuditFinding(
                    code=TemporalAuditFindingCode.OUTPUT_CHANGED_WITH_STARTUP_HISTORY,
                    history_length=history_length,
                    changed_fields=changed,
                    message=(
                        "endpoint output changed when the available startup history changed"
                    ),
                )
            )

    if sensitivity_found:
        status = StartupSensitivityStatus.SENSITIVITY_DETECTED
    elif len(audited) != len(lengths) or findings:
        status = StartupSensitivityStatus.INDETERMINATE
    else:
        status = StartupSensitivityStatus.STABLE

    return StartupSensitivityReport(
        status=status,
        target_index=target_index,
        requested_history_lengths=lengths,
        audited_history_lengths=tuple(sorted(audited)),
        findings=tuple(findings),
    )


def temporal_leakage_gate_result(report: TemporalLeakageReport) -> GateResult:
    """Adapt a prefix-invariance report to the frozen ``lookahead`` Hard Gate.

    The gate is fail-closed: only a complete PASS for the requested cutoffs may
    proceed.  Both detected leakage and an indeterminate audit fail the gate,
    with different reasons preserved for governance and debugging.
    """

    if not isinstance(report, TemporalLeakageReport):
        raise ValueError("report must be a TemporalLeakageReport")

    if report.status is TemporalLeakageStatus.PASS:
        reason = "implementation_prefix_invariant"
        passed = True
    elif report.status is TemporalLeakageStatus.LEAKAGE_DETECTED:
        reason = "implementation_future_dependency_detected"
        passed = False
    else:
        reason = "implementation_leakage_audit_indeterminate"
        passed = False

    return GateResult(
        gate="lookahead",
        passed=passed,
        reason=reason,
        evidence={
            "audit_status": report.status.value,
            "total_history_rows": report.total_history_rows,
            "requested_cutoffs": report.requested_cutoffs,
            "audited_cutoffs": report.audited_cutoffs,
            "finding_codes": tuple(finding.code.value for finding in report.findings),
        },
    )


def _require_history(history: Sequence[T], *, minimum_size: int) -> tuple[T, ...]:
    if isinstance(history, (str, bytes)):
        raise ValueError("history must be a sequence of rows, not text")
    try:
        rows = tuple(history)
    except TypeError as exc:
        raise ValueError("history must be an iterable sequence") from exc
    if len(rows) < minimum_size:
        raise ValueError(f"history requires at least {minimum_size} rows")
    return rows


def _normalize_cutoffs(cutoffs: Sequence[int], history_length: int) -> tuple[int, ...]:
    if isinstance(cutoffs, (str, bytes)):
        raise ValueError("cutoffs must be a sequence of ints")
    try:
        raw = tuple(cutoffs)
    except TypeError as exc:
        raise ValueError("cutoffs must be iterable") from exc
    if not raw:
        raise ValueError("cutoffs must not be empty")

    normalized: list[int] = []
    for cutoff in raw:
        if isinstance(cutoff, bool) or not isinstance(cutoff, int):
            raise ValueError("every cutoff must be an int")
        if cutoff < 0 or cutoff >= history_length - 1:
            raise ValueError(
                "every cutoff must be non-negative and leave at least one future row"
            )
        normalized.append(cutoff)
    if len(set(normalized)) != len(normalized):
        raise ValueError("cutoffs must not contain duplicates")
    return tuple(sorted(normalized))


def _normalize_history_lengths(
    history_lengths: Sequence[int],
    maximum_length: int,
) -> tuple[int, ...]:
    if isinstance(history_lengths, (str, bytes)):
        raise ValueError("history_lengths must be a sequence of ints")
    try:
        raw = tuple(history_lengths)
    except TypeError as exc:
        raise ValueError("history_lengths must be iterable") from exc
    if len(raw) < 2:
        raise ValueError("at least two history_lengths are required")

    normalized: list[int] = []
    for length in raw:
        if isinstance(length, bool) or not isinstance(length, int):
            raise ValueError("every history length must be an int")
        if length <= 0 or length > maximum_length:
            raise ValueError("history length must be positive and fit before target_index")
        normalized.append(length)
    if len(set(normalized)) != len(normalized):
        raise ValueError("history_lengths must not contain duplicates")
    return tuple(sorted(normalized))


def _run_evaluator(
    *,
    evaluator: TemporalEvaluator[T],
    history: Sequence[T],
    expected_length: int,
    context: str,
    cutoff: int | None = None,
    history_length: int | None = None,
) -> tuple[tuple[NormalizedSnapshot, ...] | None, TemporalAuditFinding | None]:
    try:
        raw_outputs = tuple(evaluator(history))
    except Exception as exc:  # audit a black-box implementation; do not false-pass.
        return None, TemporalAuditFinding(
            code=TemporalAuditFindingCode.EVALUATOR_ERROR,
            cutoff=cutoff,
            history_length=history_length,
            message=f"{context} evaluator raised {type(exc).__name__}: {exc}",
        )

    if len(raw_outputs) != expected_length:
        return None, TemporalAuditFinding(
            code=TemporalAuditFindingCode.OUTPUT_LENGTH_MISMATCH,
            cutoff=cutoff,
            history_length=history_length,
            message=(
                f"{context} returned {len(raw_outputs)} outputs for "
                f"{expected_length} input rows"
            ),
        )

    try:
        normalized = tuple(_normalize_snapshot(snapshot) for snapshot in raw_outputs)
    except ValueError as exc:
        return None, TemporalAuditFinding(
            code=TemporalAuditFindingCode.OUTPUT_CONTRACT_ERROR,
            cutoff=cutoff,
            history_length=history_length,
            message=f"{context} violated snapshot contract: {exc}",
        )
    return normalized, None


def _normalize_snapshot(snapshot: Snapshot) -> NormalizedSnapshot:
    if not isinstance(snapshot, Mapping):
        raise ValueError("each evaluator output must be a mapping")
    normalized: list[tuple[str, Scalar]] = []
    for key, value in snapshot.items():
        if not isinstance(key, str) or not key:
            raise ValueError("snapshot keys must be non-empty strings")
        if value is None or isinstance(value, (str, bool, int)):
            scalar: Scalar = value
        elif isinstance(value, float):
            if not isfinite(value):
                raise ValueError(f"snapshot field {key!r} must be finite")
            scalar = value
        else:
            raise ValueError(
                f"snapshot field {key!r} must be str/int/float/bool/None, "
                f"got {type(value).__name__}"
            )
        normalized.append((key, scalar))
    return tuple(sorted(normalized, key=lambda item: item[0]))


def _changed_fields(
    left: NormalizedSnapshot,
    right: NormalizedSnapshot,
) -> tuple[str, ...]:
    left_map = dict(left)
    right_map = dict(right)
    return tuple(
        sorted(
            key
            for key in set(left_map) | set(right_map)
            if left_map.get(key, _MISSING) != right_map.get(key, _MISSING)
        )
    )


_MISSING = object()
