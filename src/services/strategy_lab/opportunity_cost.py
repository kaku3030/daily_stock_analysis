"""PIT-safe, research-only opportunity recall and miss attribution."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Any, Iterable, Sequence

from src.services.stock_radar_v2.execution_reality import ShadowExecutionRecord
from src.services.stock_radar_v2.observation_ledger import LatencyTrace, Observation


DEFINITION_VERSION = "opportunity-truth-v0.1"
HARNESS_VERSION = "recall-calibration-harness-v0.1"


class TruthStatus(StrEnum):
    OPPORTUNITY = "OPPORTUNITY"
    NOT_OPPORTUNITY = "NOT_OPPORTUNITY"
    UNKNOWN = "UNKNOWN"


class MissReason(StrEnum):
    DETECTOR_FN = "DETECTOR_FN"
    STRATEGY_GATE_FN = "STRATEGY_GATE_FN"
    PORTFOLIO_BLOCK = "PORTFOLIO_BLOCK"
    EXECUTION_INFEASIBLE = "EXECUTION_INFEASIBLE"
    COOLDOWN = "COOLDOWN"
    ATTEMPT_BUDGET_EXHAUSTED = "ATTEMPT_BUDGET_EXHAUSTED"
    CORRECT_REJECTION_OR_PROTECTION = "CORRECT_REJECTION_OR_PROTECTION"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class OpportunityTruth:
    opportunity_id: str
    universe_snapshot_id: str
    definition_version: str
    horizon: float
    label_available_at: float
    outcome_end_at: float
    status: TruthStatus
    censored: bool
    mfe: float | None = None
    mae: float | None = None
    independent_leadership: bool | None = None
    rs_persistence: float | None = None
    reference_onset_at: float | None = None
    eligible_at: float | None = None

    def __post_init__(self) -> None:
        if self.horizon <= 0 or self.label_available_at <= self.outcome_end_at:
            raise ValueError("truth labels must become available after the outcome horizon")
        if self.censored and self.status is not TruthStatus.UNKNOWN:
            raise ValueError("censored truth must remain UNKNOWN")

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["status"] = self.status.value
        return value

    def serialize(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))


@dataclass(frozen=True)
class RecallEvaluationRecord:
    opportunity_id: str
    observation_id: str | None
    truth: OpportunityTruth
    detector_seen: bool
    strategy_eligible: bool | None
    portfolio_admissible: bool | None
    execution_feasible: bool | None
    canonical_permission: str
    earliest_executable_at: float | None
    miss_reason: MissReason
    simulated_execution_id: str | None = None
    lifecycle_outcome: str | None = None
    exit_at: float | None = None
    lifecycle_mae: float | None = None
    lifecycle_mfe: float | None = None
    capture_at: float | None = None

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["truth"] = self.truth.to_dict()
        value["miss_reason"] = self.miss_reason.value
        return value

    def serialize(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))


class RecallEvaluationLedger:
    """Idempotent research replay store; it has no production/runtime hooks."""

    def __init__(self) -> None:
        self._records: dict[str, RecallEvaluationRecord] = {}

    def append(self, record: RecallEvaluationRecord) -> RecallEvaluationRecord:
        previous = self._records.get(record.opportunity_id)
        if previous is not None and previous.serialize() != record.serialize():
            raise ValueError("opportunity replay conflicts with existing record")
        self._records.setdefault(record.opportunity_id, record)
        return self._records[record.opportunity_id]

    def records(self) -> tuple[RecallEvaluationRecord, ...]:
        return tuple(self._records.values())


def attribute_miss(observation: Observation | None, truth: OpportunityTruth) -> MissReason:
    if truth.status is not TruthStatus.OPPORTUNITY or truth.censored:
        return MissReason.UNKNOWN
    if observation is None or observation.detector_status in {"NOT_DETECTED", "UNKNOWN"}:
        return MissReason.DETECTOR_FN
    if observation.strategy_eligible is False:
        return MissReason.STRATEGY_GATE_FN
    if observation.portfolio_admissible is False:
        reasons = set(observation.portfolio_block_reasons)
        if "COOLDOWN" in reasons:
            return MissReason.COOLDOWN
        if "ATTEMPT_BUDGET_EXHAUSTED" in reasons:
            return MissReason.ATTEMPT_BUDGET_EXHAUSTED
        if "PROTECTION" in reasons or "RISK" in reasons:
            return MissReason.CORRECT_REJECTION_OR_PROTECTION
        return MissReason.PORTFOLIO_BLOCK
    if observation.execution_feasible is False:
        return MissReason.EXECUTION_INFEASIBLE
    return MissReason.UNKNOWN


@dataclass(frozen=True)
class CounterfactualLifecycle:
    execution: ShadowExecutionRecord
    outcome: str
    exit_at: float | None = None
    mae: float | None = None
    mfe: float | None = None


def counterfactual_execution(execution: ShadowExecutionRecord) -> ShadowExecutionRecord:
    """Pure research boundary; the record constructor enforces causal timing."""
    return execution


def simulate_counterfactual_lifecycle(
    *,
    observation: Observation,
    execution: ShadowExecutionRecord | None,
    exit_at: float | None = None,
    mae: float | None = None,
    mfe: float | None = None,
) -> CounterfactualLifecycle | None:
    """Replay eligibility -> executable fill -> lifecycle, without hindsight."""
    if observation.earliest_executable_at is None:
        return None
    if execution is None or execution.order_intent_at < observation.earliest_executable_at:
        return None
    if execution.simulated_fill_at is None or execution.simulated_fill_at < observation.earliest_executable_at:
        return None
    return CounterfactualLifecycle(execution, "FILLED", exit_at, mae, mfe)


def time_to_capture(truth: OpportunityTruth, observation: Observation | None) -> float | None:
    """Opportunity-capture delay only; excludes policy and infrastructure latency."""
    onset = truth.reference_onset_at if truth.reference_onset_at is not None else truth.eligible_at
    capture = observation.latency.detected_at if observation is not None else None
    if truth.status is not TruthStatus.OPPORTUNITY or truth.censored or onset is None or capture is None:
        return None
    if capture < onset or onset > truth.label_available_at:
        return None
    return capture - onset


def evaluate(observations: Iterable[Observation], truths: Iterable[OpportunityTruth]) -> tuple[RecallEvaluationRecord, ...]:
    by_opportunity: dict[str, list[Observation]] = {}
    for item in observations:
        key = item.opportunity_id or (item.observation_id if item.observation_id else None)
        if key is not None:
            by_opportunity.setdefault(key, []).append(item)
    result = []
    for truth in truths:
        candidates = by_opportunity.get(truth.opportunity_id, [])
        observation = candidates[0] if len(candidates) == 1 else None
        result.append(RecallEvaluationRecord(
            truth.opportunity_id, observation.observation_id if observation else None, truth,
            observation is not None and observation.detector_status not in {"NOT_DETECTED", "UNKNOWN"},
            observation.strategy_eligible if observation else None,
            observation.portfolio_admissible if observation else None,
            observation.execution_feasible if observation else None,
            observation.canonical_permission if observation else "UNKNOWN",
            observation.earliest_executable_at if observation else None,
            MissReason.UNKNOWN if len(candidates) > 1 else attribute_miss(observation, truth),
            capture_at=observation.latency.detected_at if observation else None,
        ))
    return tuple(result)


def calibration_summary(
    observations: Iterable[Observation], truths: Iterable[OpportunityTruth],
    *, dataset_id: str, execution_outcomes: Iterable[tuple[str, str]] = (),
) -> dict[str, Any]:
    """Stable, read-only research summary; never writes or changes observations."""
    records = evaluate(observations, truths)
    outcomes = dict(execution_outcomes)
    eligible = tuple(r for r in records if r.truth.status is not TruthStatus.UNKNOWN and not r.truth.censored)
    opportunities = tuple(r for r in eligible if r.truth.status is TruthStatus.OPPORTUNITY)
    reasons = {reason.value: sum(r.miss_reason is reason for r in opportunities) for reason in MissReason}
    captured = tuple(r for r in opportunities if r.detector_seen and r.strategy_eligible is True
                     and r.portfolio_admissible is not False and r.execution_feasible is not False
                     and r.canonical_permission == "ALLOW")
    ttc = [value for r in captured for value in [time_to_capture(r.truth, Observation(
        r.observation_id or "", "DETECTED", latency=LatencyTrace(detected_at=r.capture_at)))] if value is not None]
    missed_mfe = [r.truth.mfe for r in opportunities if r not in captured and r.truth.mfe is not None]
    return {
        "harness_version": HARNESS_VERSION, "dataset_id": dataset_id,
        "truth_definition_versions": sorted({r.truth.definition_version for r in records}),
        "eligible_truth_opportunities_count": len(opportunities),
        "detector_recall": {"numerator": sum(r.detector_seen for r in opportunities) if opportunities else None, "denominator": len(opportunities) or None},
        "strategy_recall": {"numerator": sum(r.strategy_eligible is True for r in opportunities) if opportunities else None, "denominator": len(opportunities) or None},
        "miss_attribution_counts": reasons,
        "time_to_capture": {"count": len(ttc), "p50": sorted(ttc)[(len(ttc)-1)//2] if ttc else None},
        "missed_mfe": {"count": len(missed_mfe), "mean": sum(missed_mfe)/len(missed_mfe) if missed_mfe else None},
        "captured_opportunities": len(captured), "missed_opportunities": len(opportunities) - len(captured),
        "execution_outcomes_count": len(outcomes),
        "status": "KNOWN" if opportunities else "UNKNOWN",
    }


def metrics(records: Iterable[RecallEvaluationRecord]) -> dict[str, float | str]:
    items = tuple(records)
    eligible = tuple(r for r in items if r.truth.status is not TruthStatus.UNKNOWN and not r.truth.censored)
    if not eligible:
        return {"status": "UNKNOWN", "reason": "NO_UNCENSORED_TRUTH"}
    opportunities = tuple(r for r in eligible if r.truth.status is TruthStatus.OPPORTUNITY)
    if not opportunities:
        return {"status": "UNKNOWN", "reason": "NO_OPPORTUNITY_LABELS"}
    def rate(n: int, d: int) -> float: return n / d
    ttc = [r.capture_at - (r.truth.reference_onset_at if r.truth.reference_onset_at is not None else r.truth.eligible_at)
           for r in opportunities
           if r.capture_at is not None
           and (r.truth.reference_onset_at is not None or r.truth.eligible_at is not None)
           and (r.truth.reference_onset_at if r.truth.reference_onset_at is not None else r.truth.eligible_at) <= r.capture_at
           and (r.truth.reference_onset_at if r.truth.reference_onset_at is not None else r.truth.eligible_at) <= r.truth.label_available_at]
    result = {
        "status": "KNOWN", "opportunity_recall": rate(sum(r.canonical_permission == "ALLOW" and r.execution_feasible is True for r in opportunities), len(opportunities)),
        "detector_recall": rate(sum(r.detector_seen for r in opportunities), len(opportunities)),
        "strategy_recall": rate(sum(r.strategy_eligible is True for r in opportunities), len(opportunities)),
        "missed_mfe": sum(r.truth.mfe or 0 for r in opportunities if r.miss_reason is not MissReason.UNKNOWN),
        "missed_expectancy_contribution": "PLACEHOLDER_RISK_ADJUSTED_V0.1",
    }
    result["time_to_capture_count"] = len(ttc)
    result["time_to_capture_p50"] = sorted(ttc)[(len(ttc) - 1) // 2] if ttc else "UNKNOWN"
    return result
