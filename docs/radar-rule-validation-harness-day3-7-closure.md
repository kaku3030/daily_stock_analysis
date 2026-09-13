# Radar Rule Validation Harness V0.1 — Day 3–7 closure

## Evidence status

| Gate | Status | Meaning |
| --- | --- | --- |
| Dataset Capsule / PIT metadata | IMPLEMENTED | Source identity, adapter version, event hashes, and three causal timestamps are frozen. |
| Reservation → OOS claim | IMPLEMENTED | Matching reservation, manifest, contract, and dataset are required before the existing OOS Ledger claim. |
| Counterfactual plan execution | IMPLEMENTED | All five frozen variants run in canonical order and are fingerprint-bound. |
| Walk-forward / purge / embargo / parameter robustness | AVAILABLE_FOR_INTEGRATION | Existing Strategy Lab modules remain the authority; no second implementation was added. |
| Day 6 adversarial coverage | IMPLEMENTED | Mismatch, unknown PIT, exhausted budget, idempotency, SQLite contention, malformed schema, and irreversible OOS consumption are tested. |
| Day 7 end-to-end | PASS_SYNTHETIC_FIXTURE_ONLY | The RS-breakout fixture proves contract-to-burn orchestration, not market efficacy. |
| Real-data validation | PENDING_CAPTURE | BaoStock is the V0.1 A-share EOD research-capture candidate; no captured bytes have yet passed source/PIT validation. |
| Never-Seen Holdout on approved market data | PENDING | No approved CSV has been loaded. |
| Promotion / production use | NOT_AUTHORIZED | Synthetic evidence has no production authority. |

The post-implementation regression slice (Harness plus repaired lifecycle and
scheduler paths) is green: **45 passed**. This does not change the recorded
market-data and promotion blockers above.

## Release-blocking truth

The synthetic E2E test is deliberately not a backtest result, not a live run,
and not a real-data validation. It may only establish that the Harness refuses
unsafe inputs and preserves its irreversible research governance sequence.

To close real-data validation, load a versioned approved historical EOD OHLCV
CSV into a `ResearchDatasetCapsule`, bind PIT evidence for every field and
historical universe/corporate-action metadata, then run an untouched
chronological holdout with `train_end < holdout_start` and no post-holdout
parameter or rule edits.

## V0.1 source decision

BaoStock is the first A-share historical EOD **research-capture candidate**.
It is not yet an approved real-data source and does not create a live-provider
runtime. Every capture must be frozen to CSV and bound to the existing source
authority with its endpoint, request parameters, adapter revision, retrieval
time, raw-byte hash, timezone, adjustment semantics, and `available_at`
policy. A sample must be cross-checked before the dataset can be used for real
OOS validation; unknown or mismatched provenance fails closed.

TuShare Pro and AKShare are deferred candidate adapters. They may be added
only through this same single source-authority and Dataset Capsule path; they
must not introduce a second registry or silently replace recorded evidence.

The reproducible capture entry point is `scripts/capture_research_eod.py`.
It writes the raw CSV plus a sidecar manifest marked
`CAPTURED_NOT_APPROVED`; approval still requires source/PIT and cross-source
checks.
