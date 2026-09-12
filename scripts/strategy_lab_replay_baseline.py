"""Research-only replay baseline helper; never imported by production runtime."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.services.stock_radar_v2.observation_ledger import LatencyTrace, Observation
from src.services.strategy_lab.opportunity_cost import (
    DATASET_CONTRACT_VERSION, HARNESS_VERSION, OpportunityTruth, TruthStatus,
    calibration_summary,
)

DATASET_ID = "historical-fixture-recall-v0.1"
CREATED_FROM = "df0560a773d25d04deb2fbe0eef36e15ee4ec479"


def build_baseline() -> dict:
    observations = [
        Observation("o1", "NOT_DETECTED", opportunity_id="miss-detector"),
        Observation("o2", "DETECTED", opportunity_id="miss-strategy", strategy_eligible=False),
        Observation("o3", "DETECTED", opportunity_id="blocked", strategy_eligible=True, portfolio_admissible=False),
        Observation("o4", "DETECTED", opportunity_id="infeasible", strategy_eligible=True, portfolio_admissible=True, execution_feasible=False),
        Observation("o5", "DETECTED", opportunity_id="protected", strategy_eligible=True, portfolio_admissible=False, portfolio_block_reasons=("PROTECTION",)),
        Observation("o6", "DETECTED", opportunity_id="captured", strategy_eligible=True, portfolio_admissible=True, execution_feasible=True, canonical_permission="ALLOW", latency=LatencyTrace(detected_at=13)),
    ]
    def truth(opportunity_id: str, status=TruthStatus.OPPORTUNITY, censored=False):
        return OpportunityTruth(opportunity_id, "fixture-universe-v0.1", "truth-v1", 10, 21, 20, status, censored, mfe=5, reference_onset_at=10)
    truths = [truth(item) for item in ("miss-detector", "miss-strategy", "blocked", "infeasible", "protected", "captured")]
    truths += [truth("censored", TruthStatus.UNKNOWN, True), truth("unknown", TruthStatus.UNKNOWN)]
    summary = calibration_summary(observations, truths, dataset_id=DATASET_ID)
    return {
        "dataset_contract": {
            "contract_version": DATASET_CONTRACT_VERSION, "dataset_id": DATASET_ID,
            "source_type": "HISTORICAL_FIXTURE_BASELINE", "market": "UNKNOWN",
            "time_range": {"start": None, "end": None, "status": "UNKNOWN"},
            "universe_definition": "fixture-universe-v0.1", "truth_definition_version": "truth-v1",
            "harness_version": HARNESS_VERSION, "created_from": CREATED_FROM,
            "record_counts": {"observations": len(observations), "truths": len(truths), "opportunities": 6},
            "dq_caveats": ["No persisted production ledger or market timestamps found", "market and time_range UNKNOWN", "fixture sample is not statistically reliable"],
        },
        "baseline": summary,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", type=Path)
    args = parser.parse_args()
    payload = json.dumps(build_baseline(), ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    if args.write:
        args.write.parent.mkdir(parents=True, exist_ok=True)
        args.write.write_text(payload, encoding="utf-8")
    else:
        print(payload, end="")


if __name__ == "__main__":
    main()
