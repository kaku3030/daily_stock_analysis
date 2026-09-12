import json

from src.services.stock_radar_v2.observation_ledger import LatencyTrace, Observation
from src.services.strategy_lab.opportunity_cost import (
    MissReason, OpportunityTruth, TruthStatus, calibration_summary, evaluate,
)


def _truth(i, status=TruthStatus.OPPORTUNITY, *, censored=False, onset=10):
    return OpportunityTruth(i, "snap-1", "truth-v1", 10, 21, 20, status, censored,
                            mfe=5, reference_onset_at=onset)


def test_fixture_summary_is_reconcilable_and_deterministic():
    observations = [
        Observation("o1", "NOT_DETECTED", opportunity_id="miss-detector"),
        Observation("o2", "DETECTED", opportunity_id="miss-strategy", strategy_eligible=False),
        Observation("o3", "DETECTED", opportunity_id="blocked", strategy_eligible=True, portfolio_admissible=False),
        Observation("o4", "DETECTED", opportunity_id="infeasible", strategy_eligible=True, portfolio_admissible=True, execution_feasible=False),
        Observation("o5", "DETECTED", opportunity_id="protected", strategy_eligible=True, portfolio_admissible=False, portfolio_block_reasons=("PROTECTION",)),
        Observation("o6", "DETECTED", opportunity_id="captured", strategy_eligible=True, portfolio_admissible=True, execution_feasible=True,
                     canonical_permission="ALLOW", latency=LatencyTrace(detected_at=13)),
    ]
    truths = [_truth(x) for x in ("miss-detector", "miss-strategy", "blocked", "infeasible", "protected", "captured")]
    truths += [_truth("censored", censored=True, status=TruthStatus.UNKNOWN), _truth("unknown", status=TruthStatus.UNKNOWN)]
    summary = calibration_summary(observations, truths, dataset_id="fixture-v1")
    assert summary["eligible_truth_opportunities_count"] == 6
    assert summary["detector_recall"] == {"numerator": 5, "denominator": 6}
    assert summary["captured_opportunities"] == 1 and summary["missed_opportunities"] == 5
    assert sum(summary["miss_attribution_counts"].values()) == 6
    assert summary["time_to_capture"] == {"count": 1, "p50": 3}
    encoded = json.dumps(summary, sort_keys=True, separators=(",", ":"))
    assert encoded == json.dumps(summary, sort_keys=True, separators=(",", ":"))


def test_ambiguous_stable_join_is_unknown_not_symbol_guess():
    truths = [_truth("op")]
    observations = [Observation("a", "DETECTED", opportunity_id="op"), Observation("b", "DETECTED", opportunity_id="op")]
    record = evaluate(observations, truths)[0]
    assert record.observation_id is None and record.miss_reason is MissReason.UNKNOWN


def test_empty_summary_is_explicit_unknown():
    result = calibration_summary([], [], dataset_id="empty")
    assert result["status"] == "UNKNOWN"
    assert result["detector_recall"] == {"numerator": None, "denominator": None}
