"""Strategy Lab V0.1 -- Soft Validation layer.

Translates the three merged Foundation engines' *labels* (never their
numeric scores) into a shared, ordered evidence vocabulary that sits
alongside -- and never modifies -- the existing Hard Validation machinery
in ``validation_models.py`` / ``hard_gates.py``.

Hard vs. Soft, and why they stay separate:

- **Hard Validation** (``ValidationReport`` / ``HardGatePipeline``,
  unchanged by this module) is binary, ordered, and stops at the first
  failure. A Hard ``PASS`` means only that the experiment is eligible to
  continue validation -- it does **not** mean the strategy is validated,
  and it says nothing about robustness, concentration, or stability.
- **Soft Validation** (this module) is a four-level status
  (``ACCEPTABLE`` / ``CAUTION`` / ``FRAGILE`` / ``INCONCLUSIVE``) derived
  purely from each Foundation engine's own frozen label enum. It can never
  rewrite a Hard ``PASS`` into a Hard ``FAIL``, and this module introduces
  no combinator, no combined report type, and no higher-level
  "validated/promotable" decision -- that decision is explicitly out of
  scope for V0.1. What Soft Validation *can* do, at a level above this
  module, is prevent a future promotion conclusion when it comes back
  ``FRAGILE`` or ``INCONCLUSIVE``; this module only produces the evidence
  for that future decision, it does not make it.

This module does not implement ``logic_integrity``, ``execution_causality``,
or ``execution_reality`` -- those remain unimplemented Hard Gates, out of
scope here and reserved for separate briefs. In particular,
``execution_stress`` measures robustness to fees/slippage/delay, which is
categorically different from ``execution_reality`` (causal/physical
execution validity); cost fragility is Soft Validation evidence, never a
Hard execution-reality failure, and this module does not wire the two
together.

Exactly one ``SoftValidationResult`` is required from each of the three
frozen ``SoftValidationSource`` values -- ``PARAMETER_STABILITY``,
``EDGE_CONCENTRATION``, ``EXECUTION_STRESS``. Missing, duplicate, or
unknown sources fail closed (``ValueError``) rather than silently
producing a partial or misleading report; malformed/unknown sources are
rejected even earlier, at ``SoftValidationResult`` construction. Enum
fields (``source``, ``status``, ``overall_status``) use **strict**
runtime validation, not coercion: a value must already be an instance of
the corresponding enum. A raw string -- even an otherwise-valid one such
as ``"parameter_stability"`` or ``"acceptable"`` -- is rejected with
``ValueError`` rather than silently converted. Every element of
``SoftValidationReport.results`` must itself be a ``SoftValidationResult``
instance; a malformed child value fails closed with ``ValueError`` at
construction rather than surfacing later as an incidental
``AttributeError``.

Per-engine frozen label mapping (adapters read *only* the engine's own
label field -- ``stability_label`` / ``fragility_label`` /
``fragility_label`` -- never a numeric score, retention ratio, or any
other PnL-derived value; a mismatched or contrived numeric field on a
Foundation result cannot change the mapped status):

    Parameter Stability:
        STABLE_PLATEAU              -> ACCEPTABLE
        FRAGILE / NARROW_PEAK       -> CAUTION
        UNSTABLE_CLIFF              -> FRAGILE
        INSUFFICIENT_DATA           -> INCONCLUSIVE

    Edge Concentration:
        DIVERSIFIED                 -> ACCEPTABLE
        MODERATE                    -> CAUTION
        CONCENTRATED / EXTREME      -> FRAGILE
        INSUFFICIENT_DATA           -> INCONCLUSIVE
        NO_POSITIVE_EDGE            -> INCONCLUSIVE

    Execution Stress:
        ROBUST                      -> ACCEPTABLE
        MODERATE                    -> CAUTION
        FRAGILE / EXTREME           -> FRAGILE
        INSUFFICIENT_DATA           -> INCONCLUSIVE
        NO_POSITIVE_BASELINE_EDGE   -> INCONCLUSIVE

``NO_POSITIVE_EDGE`` / ``NO_POSITIVE_BASELINE_EDGE`` map to
``INCONCLUSIVE``, not a Hard-Gate-style failure: "no trustworthy edge
could be computed" is a different claim from "the edge is bad", exactly as
the Foundation engines themselves already distinguish (see their own
module docstrings).

Aggregation is a pure precedence pick over the *set* of per-source
statuses -- deliberately no averaging, weighting, voting, or composite
score, matching the "no averaging across gates" philosophy already frozen
for Hard Validation:

    FRAGILE > INCONCLUSIVE > CAUTION > ACCEPTABLE

Any ``FRAGILE`` source makes the aggregate ``FRAGILE``; otherwise any
``INCONCLUSIVE`` source makes it ``INCONCLUSIVE``; otherwise any
``CAUTION`` makes it ``CAUTION``; otherwise ``ACCEPTABLE``. Because this is
a set-membership precedence pick, not a sequential fold, the result is
structurally order-invariant -- shuffling the input results cannot change
it. ``SoftValidationReport.__post_init__`` re-derives and cross-checks
``overall_status`` against its own ``results`` independently of
``aggregate_soft_validation``, so even a directly (not via
``aggregate_soft_validation``) and inconsistently constructed report fails
closed at construction time.

While ``overall_status`` was always order-invariant, ``results`` itself is
canonicalized (after source-set validation) to the fixed order defined by
``SOFT_VALIDATION_SOURCES`` -- parameter stability, edge concentration,
execution stress -- regardless of the order the caller supplied. This
makes ``SoftValidationReport.results`` deterministic and directly
comparable across differently-ordered inputs.

This module has no dependency on performance: it does not import
``performance_models``, does not accept a ``PerformanceReport``, and no
adapter or aggregation path reads CAGR, Sharpe, max drawdown, or any other
absolute-return metric. ``evidence`` on both dataclasses is diagnostic
only (currently: each source's own ``warnings`` tuple) -- it is never
read back by any function in this module to influence a status.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping, Sequence

from .edge_concentration import EdgeConcentrationResult, EdgeFragilityLabel
from .execution_stress import ExecutionFragilityLabel, ExecutionStressResult
from .parameter_stability import ParameterStabilityLabel, ParameterStabilityResult


class SoftValidationStatus(str, Enum):
    ACCEPTABLE = "acceptable"
    CAUTION = "caution"
    FRAGILE = "fragile"
    INCONCLUSIVE = "inconclusive"


class SoftValidationSource(str, Enum):
    PARAMETER_STABILITY = "parameter_stability"
    EDGE_CONCENTRATION = "edge_concentration"
    EXECUTION_STRESS = "execution_stress"


SOFT_VALIDATION_SOURCES = (
    SoftValidationSource.PARAMETER_STABILITY,
    SoftValidationSource.EDGE_CONCENTRATION,
    SoftValidationSource.EXECUTION_STRESS,
)

# Highest precedence first. Aggregation is a precedence pick over the set
# of statuses present -- see module docstring.
_STATUS_PRECEDENCE = (
    SoftValidationStatus.FRAGILE,
    SoftValidationStatus.INCONCLUSIVE,
    SoftValidationStatus.CAUTION,
    SoftValidationStatus.ACCEPTABLE,
)

_PARAMETER_STABILITY_MAPPING: Mapping[ParameterStabilityLabel, SoftValidationStatus] = {
    ParameterStabilityLabel.STABLE_PLATEAU: SoftValidationStatus.ACCEPTABLE,
    ParameterStabilityLabel.FRAGILE: SoftValidationStatus.CAUTION,
    ParameterStabilityLabel.NARROW_PEAK: SoftValidationStatus.CAUTION,
    ParameterStabilityLabel.UNSTABLE_CLIFF: SoftValidationStatus.FRAGILE,
    ParameterStabilityLabel.INSUFFICIENT_DATA: SoftValidationStatus.INCONCLUSIVE,
}

_EDGE_CONCENTRATION_MAPPING: Mapping[EdgeFragilityLabel, SoftValidationStatus] = {
    EdgeFragilityLabel.DIVERSIFIED: SoftValidationStatus.ACCEPTABLE,
    EdgeFragilityLabel.MODERATE: SoftValidationStatus.CAUTION,
    EdgeFragilityLabel.CONCENTRATED: SoftValidationStatus.FRAGILE,
    EdgeFragilityLabel.EXTREME: SoftValidationStatus.FRAGILE,
    EdgeFragilityLabel.INSUFFICIENT_DATA: SoftValidationStatus.INCONCLUSIVE,
    EdgeFragilityLabel.NO_POSITIVE_EDGE: SoftValidationStatus.INCONCLUSIVE,
}

_EXECUTION_STRESS_MAPPING: Mapping[ExecutionFragilityLabel, SoftValidationStatus] = {
    ExecutionFragilityLabel.ROBUST: SoftValidationStatus.ACCEPTABLE,
    ExecutionFragilityLabel.MODERATE: SoftValidationStatus.CAUTION,
    ExecutionFragilityLabel.FRAGILE: SoftValidationStatus.FRAGILE,
    ExecutionFragilityLabel.EXTREME: SoftValidationStatus.FRAGILE,
    ExecutionFragilityLabel.INSUFFICIENT_DATA: SoftValidationStatus.INCONCLUSIVE,
    ExecutionFragilityLabel.NO_POSITIVE_BASELINE_EDGE: SoftValidationStatus.INCONCLUSIVE,
}


@dataclass(frozen=True)
class SoftValidationResult:
    source: SoftValidationSource
    status: SoftValidationStatus
    label: str
    reason: str
    evidence: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.source, SoftValidationSource):
            raise ValueError(
                f"source must be a SoftValidationSource instance, got {self.source!r}"
            )
        if not isinstance(self.status, SoftValidationStatus):
            raise ValueError(
                f"status must be a SoftValidationStatus instance, got {self.status!r}"
            )

        if not self.label.strip():
            raise ValueError("label must not be empty")
        if not self.reason.strip():
            raise ValueError("reason must not be empty")


@dataclass(frozen=True)
class SoftValidationReport:
    strategy_id: str
    overall_status: SoftValidationStatus
    results: tuple[SoftValidationResult, ...]
    evidence: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.strategy_id.strip():
            raise ValueError("strategy_id must not be empty")

        if not isinstance(self.overall_status, SoftValidationStatus):
            raise ValueError(
                f"overall_status must be a SoftValidationStatus instance, got {self.overall_status!r}"
            )

        for result in self.results:
            if not isinstance(result, SoftValidationResult):
                raise ValueError(
                    f"results must contain only SoftValidationResult instances, got {result!r}"
                )

        sources = [result.source for result in self.results]
        if len(sources) != len(set(sources)):
            raise ValueError("SoftValidationReport must not contain duplicate sources")
        required = set(SOFT_VALIDATION_SOURCES)
        present = set(sources)
        if present != required:
            missing = sorted(source.value for source in required - present)
            extra = sorted(source.value for source in present - required)
            raise ValueError(
                f"SoftValidationReport requires exactly one result from each frozen "
                f"source: missing={missing}, extra={extra}"
            )

        canonical_order = {
            source: index for index, source in enumerate(SOFT_VALIDATION_SOURCES)
        }
        canonical_results = tuple(
            sorted(self.results, key=lambda result: canonical_order[result.source])
        )
        object.__setattr__(self, "results", canonical_results)

        derived_status = _derive_overall_status(self.results)
        if self.overall_status is not derived_status:
            raise ValueError(
                f"overall_status {self.overall_status.value!r} does not match the "
                f"precedence-derived status {derived_status.value!r} for the given results"
            )


def _derive_overall_status(results: Sequence[SoftValidationResult]) -> SoftValidationStatus:
    present = {result.status for result in results}
    for status in _STATUS_PRECEDENCE:
        if status in present:
            return status
    raise ValueError("cannot derive an overall status from empty results")


def soft_validation_from_parameter_stability(
    result: ParameterStabilityResult,
) -> SoftValidationResult:
    """Adapter: consumes only ``result.stability_label``."""

    label = result.stability_label
    status = _PARAMETER_STABILITY_MAPPING[label]
    return SoftValidationResult(
        source=SoftValidationSource.PARAMETER_STABILITY,
        status=status,
        label=label.value,
        reason=f"parameter_stability_label_{label.value}_maps_to_{status.value}",
        evidence={"warnings": tuple(result.warnings)},
    )


def soft_validation_from_edge_concentration(
    result: EdgeConcentrationResult,
) -> SoftValidationResult:
    """Adapter: consumes only ``result.fragility_label``."""

    label = result.fragility_label
    status = _EDGE_CONCENTRATION_MAPPING[label]
    return SoftValidationResult(
        source=SoftValidationSource.EDGE_CONCENTRATION,
        status=status,
        label=label.value,
        reason=f"edge_concentration_label_{label.value}_maps_to_{status.value}",
        evidence={"warnings": tuple(result.warnings)},
    )


def soft_validation_from_execution_stress(
    result: ExecutionStressResult,
) -> SoftValidationResult:
    """Adapter: consumes only ``result.fragility_label``."""

    label = result.fragility_label
    status = _EXECUTION_STRESS_MAPPING[label]
    return SoftValidationResult(
        source=SoftValidationSource.EXECUTION_STRESS,
        status=status,
        label=label.value,
        reason=f"execution_stress_label_{label.value}_maps_to_{status.value}",
        evidence={"warnings": tuple(result.warnings)},
    )


def aggregate_soft_validation(
    *,
    strategy_id: str,
    results: Sequence[SoftValidationResult],
) -> SoftValidationReport:
    """Build a ``SoftValidationReport`` from exactly one result per frozen
    source. Fails closed (``ValueError``) on empty, missing, or duplicate
    sources -- ``SoftValidationReport.__post_init__`` performs the
    authoritative check; this function does not bypass it.
    """

    if not results:
        raise ValueError("results must not be empty")

    overall_status = _derive_overall_status(results)
    return SoftValidationReport(
        strategy_id=strategy_id,
        overall_status=overall_status,
        results=tuple(results),
    )
