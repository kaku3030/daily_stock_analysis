import pytest

from services.stock_radar_v2 import Observation, ShadowExecutionRecord
from services.strategy_lab.opportunity_cost import (
    MissReason, OpportunityTruth, RecallEvaluationLedger, TruthStatus, attribute_miss, metrics,
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
