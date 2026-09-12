import pytest

from services.stock_radar_v2 import Observation, ShadowExecutionRecord
from services.stock_radar_v2.observation_ledger import LatencyTrace
from services.strategy_lab.opportunity_cost import (
    MissReason, OpportunityTruth, RecallEvaluationLedger, TruthStatus, attribute_miss, metrics,
    simulate_counterfactual_lifecycle,
)


def truth(status=TruthStatus.OPPORTUNITY, *, censored=False):
    return OpportunityTruth("x", "u1", "opportunity-truth-v0.1", 10, 21, 20, status, censored, mfe=5)


@pytest.mark.parametrize(("observation", "reason"), [
    (None, MissReason.DETECTOR_FN),
    (Observation("x", "DETECTED", strategy_eligible=False), MissReason.STRATEGY_GATE_FN),
    (Observation("x", "DETECTED", strategy_eligible=True, portfolio_admissible=False), MissReason.PORTFOLIO_BLOCK),
    (Observation("x", "DETECTED", strategy_eligible=True, portfolio_admissible=False, portfolio_block_reasons=("COOLDOWN",)), MissReason.COOLDOWN),
    (Observation("x", "DETECTED", strategy_eligible=True, portfolio_admissible=True, execution_feasible=False), MissReason.EXECUTION_INFEASIBLE),
    (Observation("x", "DETECTED", strategy_eligible=True, portfolio_admissible=False, portfolio_block_reasons=("PROTECTION",)), MissReason.CORRECT_REJECTION_OR_PROTECTION),
])
def test_miss_attribution_is_layered(observation, reason):
    assert attribute_miss(observation, truth()) is reason


def test_unknown_and_censored_never_become_negative_or_denominator():
    assert attribute_miss(None, truth(TruthStatus.UNKNOWN)) is MissReason.UNKNOWN
    assert metrics([ ]) == {"status": "UNKNOWN", "reason": "NO_UNCENSORED_TRUTH"}
    assert metrics([ ])['status'] == 'UNKNOWN'


def test_truth_requires_future_label_and_metrics_boundaries():
    with pytest.raises(ValueError):
        OpportunityTruth("x", "u", "v", 10, 20, 20, TruthStatus.OPPORTUNITY, False)
    record = __import__('services.strategy_lab.opportunity_cost', fromlist=['evaluate']).evaluate(
        [Observation("x", "DETECTED", strategy_eligible=True, portfolio_admissible=True)], [truth()])[0]
    assert metrics([record])["detector_recall"] == 1.0
    assert metrics([record])["strategy_recall"] == 1.0
    ledger = RecallEvaluationLedger()
    assert ledger.append(record) is record
    assert ledger.append(record) is record


def test_execution_reality_rejects_same_bar_hindsight():
    with pytest.raises(ValueError, match="same-bar hindsight"):
        ShadowExecutionRecord("e", 11, 11, 100, 1, 1, False, "f", "s", 0, confirmed_at=10, bar_end_at=11)


def test_counterfactual_lifecycle_requires_earliest_executable_and_records_outcome():
    observation = Observation("x", "DETECTED", strategy_eligible=True, portfolio_admissible=True,
                              earliest_executable_at=11)
    execution = ShadowExecutionRecord("e", 11, 12, 101, 1, 1, False, "f", "s", 0)
    result = simulate_counterfactual_lifecycle(observation=observation, execution=execution,
                                               exit_at=15, mae=-2, mfe=6)
    assert result is not None and result.outcome == "FILLED" and result.mfe == 6
    assert simulate_counterfactual_lifecycle(observation=observation, execution=None) is None
    assert simulate_counterfactual_lifecycle(
        observation=Observation("x", "DETECTED", earliest_executable_at=None), execution=execution) is None


def test_ttc_is_capture_delay_and_unknown_samples_do_not_enter_summary():
    t = OpportunityTruth("x", "u1", "v", 10, 21, 20, TruthStatus.OPPORTUNITY, False, reference_onset_at=10, mfe=5)
    observation = Observation("x", "DETECTED", strategy_eligible=True, portfolio_admissible=True,
                              latency=LatencyTrace(detected_at=13))
    record = __import__('services.strategy_lab.opportunity_cost', fromlist=['evaluate']).evaluate([observation], [t])[0]
    assert record.capture_at == 13
    assert metrics([record])["time_to_capture_p50"] == 3
    unknown = OpportunityTruth("u", "u1", "v", 10, 21, 20, TruthStatus.UNKNOWN, False)
    assert metrics(__import__('services.strategy_lab.opportunity_cost', fromlist=['evaluate']).evaluate([], [unknown]))["status"] == "UNKNOWN"
