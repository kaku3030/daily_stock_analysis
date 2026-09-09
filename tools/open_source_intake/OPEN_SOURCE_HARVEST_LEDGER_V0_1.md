# Open-Source Intake / Harvesting Ledger V0.1

Status: RESEARCH LEDGER — non-production governance/evidence asset.

This ledger records external engineering candidates against the current Radar frozen contracts and invariants. Entry in this file is **not** approval for production use. External maturity, stars, or official-provider status never bypass Defect Audit, Validation, Shadow Live, or the normal Promotion path.

Promotion vocabulary:

`EXTERNAL CANDIDATE -> ADAPTED -> VALIDATING -> SHADOW -> CORE`

Disposition vocabulary:

`DIRECT USE / ADAPT / TEST-REUSE / REJECT`

## Current search map

### Live Feed / Provider Reliability
- live market data feed / streaming quote / realtime feed / market data client
- subscription lifecycle / subscribe / unsubscribe / resubscribe / reconciliation
- reconnect / retry / exponential backoff / jitter / heartbeat / connection state
- provider acknowledgement / subscription ack / push handler / error semantics
- freshness / staleness / currentness / liveness / watchdog
- continuity / sequence gap / duplicate / out-of-order / missing event
- replay / recovery / catch-up / snapshot+delta / backfill
- event time / source time / receive time / observed time / monotonic clock
- idempotency / deduplication / at-least-once / stale result
- deterministic test / fake clock / fault injection / network partition

### Strategy Lab / Validation
- lookahead bias / temporal leakage / recursive indicator bias
- walk-forward / purged cross-validation / embargo / CPCV
- event-driven backtest / fill model / slippage / fee model / brokerage model
- benchmark harness / experiment tracker / reproducibility / replay
- property-based testing / state-machine testing / invariant testing

## Intake batch 2026-09-09

### FutunnOpen/py-futu-api
- URL: https://github.com/FutunnOpen/py-futu-api
- License: Apache-2.0
- Radar problem: Futu/Moomoo provider mechanics, subscription lifecycle, reconnect/resubscribe semantics, provider blocking behavior.
- Initial judgment: official provider SDK and primary semantics evidence source. Do not treat SDK transport recovery as controller recovery or LIVE qualification.
- Harvestable:
  - retained subscription registry pattern;
  - autonomous reconnect/resubscribe behavior;
  - official request/response and callback surfaces;
  - provider-specific failure and blocking behavior for empirical probes.
- Defects / risks already observed by Radar provider-semantics work:
  - subscribe return is administrative evidence only;
  - query-subscription visibility does not prove push delivery;
  - successful unsubscribe is not a callback-drain barrier;
  - autonomous reconnect uses provider-owned mechanics and cannot be equated with Radar recovery;
  - synchronous provider calls can have unbounded blocking risk under fault conditions.
- Disposition: `TEST-REUSE / ADAPT`
- Promotion: existing provider evidence source; no production code promotion implied.

### nautechsystems/nautilus_trader
- URL: https://github.com/nautechsystems/nautilus_trader
- License: LGPL-3.0
- Radar problem: production-grade event-driven market-data lifecycle, reconnect, retained subscription replay, deterministic architecture.
- Initial judgment: high-value architecture and test-method source; direct engine adoption is not justified for Radar's current Python architecture and frozen contracts.
- Harvestable:
  - reconnect backoff/max/jitter configuration patterns;
  - retained subscription replay / `resubscribe_all` patterns;
  - re-authentication-before-resubscribe sequencing where required;
  - deterministic event-driven adapter boundaries;
  - adapter failure/reconnect tests and fixtures.
- Defect Audit focus:
  - separate transport restoration from data trust;
  - do not inherit provider-specific assumptions across venues;
  - review LGPL implications before copying source rather than methods/tests.
- Disposition: `ADAPT / TEST-REUSE`
- Promotion: `EXTERNAL CANDIDATE`.

### HypothesisWorks/hypothesis
- URL: https://github.com/HypothesisWorks/hypothesis
- License: MPL-2.0 (repository metadata is not authoritative here; project source/contributor docs state MPL-2.0).
- Radar problem: adversarial state-machine coverage for LiveFeed invariants and later Strategy Lab contracts.
- Initial judgment: strong candidate for direct use as a **test-only** dependency rather than source-code harvesting.
- Harvested:
  - `RuleBasedStateMachine`;
  - rule preconditions and generated operation sequences;
  - invariants checked after arbitrary valid state transitions;
  - shrinking of failing state-machine traces to minimal reproducible cases.
- Radar adaptation:
  - Draft PR #32: https://github.com/kaku3030/stock-razor/pull/32
  - dependency is isolated to CI/test requirements, not production runtime requirements;
  - generated LiveFeed add/remove/readd/stop/provider-event sequences exercise stale generation/provider/runtime evidence and lifecycle invariants.
- Validation evidence observed:
  - Research Radar Tests: PASS on PR #32 head;
  - repository CI: PASS on PR #32 head.
- Disposition: `DIRECT USE` for tests.
- Promotion: `VALIDATING` — automated gates passed on the adapted PR head; Draft/manual review and merge governance remain separate.

### Shopify/toxiproxy
- URL: https://github.com/Shopify/toxiproxy
- License: MIT
- Radar problem: reproducible provider/network failure injection.
- Initial judgment: strong external harness candidate; do not embed its Go implementation into Radar.
- Harvestable:
  - latency + jitter faults;
  - timeout / partial-failure scenarios;
  - TCP reset simulation;
  - probabilistic toxicity for intermittent faults;
  - repeatable network-fault fixtures for provider semantics and Shadow validation.
- Candidate Radar uses:
  - Futu/OpenD reconnect experiments;
  - disconnect during subscribe/unsubscribe;
  - delayed callback / stale result tests;
  - recovery under asymmetric or intermittent connectivity.
- Defect Audit focus: CI portability, process lifecycle cleanup, deterministic fault timing, environment isolation.
- Disposition: `TEST-REUSE` / harness candidate.
- Promotion: `EXTERNAL CANDIDATE`.

### freqtrade/freqtrade
- URL: https://github.com/freqtrade/freqtrade
- License: GPL-3.0
- Radar problem: Strategy Validation Gate, temporal leakage and lookahead detection.
- Initial judgment: high-value methodology source; crypto-specific engine and GPL coupling make wholesale/direct code adoption unattractive.
- Harvested method:
  - behavioral full-history vs sliced/prefix re-evaluation for lookahead detection;
  - recursive/startup-history sensitivity analysis kept conceptually distinct from lookahead;
  - explicit bias-test failure/control thinking;
  - coverage caveat: a passing analysis proves only the paths/cutoffs exercised.
- Radar-native adaptation:
  - Draft PR #38: https://github.com/kaku3030/stock-razor/pull/38
  - stdlib-only `audit_prefix_invariance` with fail-closed `lookahead` Hard Gate adaptation;
  - separate `audit_startup_history_sensitivity` diagnosis;
  - whole-series aggregate and next-row/negative-shift-equivalent adversarial fixtures;
  - no Freqtrade source/code dependency and no GPL coupling.
- Validation evidence at latest ledger sync:
  - Research Radar focused tests: PASS and the new temporal-leakage test file is explicitly executed;
  - repository main CI: still in progress at this sync point; do not call fully validated yet.
- Disposition: `TEST-REUSE / METHOD HARVEST`.
- Promotion: `VALIDATING` — focused gate passed, full repository CI pending.

### QuantConnect/Lean
- URL: https://github.com/QuantConnect/Lean
- License: Apache-2.0
- Radar problem: later backtest/execution realism and backtest-live parity.
- Initial judgment: high-value reference for transaction-model interfaces; wholesale engine adoption is unnecessary at the current Foundation phase.
- Harvestable:
  - brokerage model boundaries;
  - slippage models;
  - fee models;
  - fill/transaction simulation patterns;
  - asset/broker-specific execution constraints and test matrices.
- Defect Audit focus:
  - avoid importing execution assumptions into current Candidate Discovery scope;
  - keep Validation/Performance physically separated as frozen in Strategy Lab;
  - model A-share/ETF constraints independently rather than assuming US-market semantics.
- Disposition: `ADAPT / TEST-REUSE` for future Strategy Lab.
- Promotion: `EXTERNAL CANDIDATE`.

### microsoft/qlib
- URL: https://github.com/microsoft/qlib
- License: MIT
- Radar problem: experiment tracking, reproducible research workflows, rolling research/evaluation, model artifact lineage.
- Initial judgment: strong architecture/method source; do not replace Radar governance with Qlib's framework wholesale.
- Harvestable:
  - Experiment / Recorder abstraction;
  - parameter + artifact logging;
  - train/backtest analysis separation in workflows;
  - rolling workflow patterns;
  - reproducible experiment lineage.
- Defect Audit focus:
  - map Qlib experiment identity to Radar claim/evidence/gate versions rather than adopting opaque model-centric identity;
  - maintain frozen Strategy Validation/Performance separation;
  - ensure no implicit data leakage in custom dataset/feature adapters.
- Disposition: `ADAPT / TEST-REUSE` for future Benchmark Harness / Model Evaluation Lab.
- Promotion: `EXTERNAL CANDIDATE`.

### vnpy/vnpy
- URL: https://github.com/vnpy/vnpy
- License: MIT
- Radar problem: mature Python gateway boundaries and China-market quant/trading ecosystem patterns.
- Initial judgment: useful ecosystem/reference candidate; deeper provider/gateway-specific audit is required before harvesting concrete reconnect semantics.
- Harvestable now:
  - gateway abstraction and subscription boundary patterns;
  - China-market conventions and adapter organization;
  - test cases around gateway/event-engine integration after deeper review.
- Defect Audit focus:
  - reconnect/resubscribe semantics are gateway-specific and must not be inferred from the generic engine call surface;
  - avoid importing order-execution scope into Radar's current non-auto-trading architecture.
- Disposition: `ADAPT / TEST-REUSE` pending deeper audit.
- Promotion: `EXTERNAL CANDIDATE`.

## Concrete outputs already produced by this lane

### LiveFeed Repair R1 — identity relevance

Draft PR: https://github.com/kaku3030/stock-razor/pull/30

Verified gap:

- Frozen adversarial Case 6 says stale/old-generation provider callbacks cannot advance liveness/trust.
- Current Slice-1 writer previously had no runtime/provider/controller-generation relevance gate before applying a provider event.
- Harvest repair adds a minimal writer-side identity relevance gate and standalone regression coverage without implementing future LIVE/Currentness/Continuity behavior.

Promotion truth: `ADAPTED` unless/until its own reproducible validation evidence is confirmed. Do not infer status from dependent/stacked PRs.

### LiveFeed generative state-machine testing

Draft PR: https://github.com/kaku3030/stock-razor/pull/32

- Hypothesis is test-only.
- Generated state-machine operations cover far more orderings than a fixed hand-written case matrix.
- Automated Research Radar and repository CI gates have passed on the adapted head.

Promotion truth: `VALIDATING`.

### Data Reliability defect batch

See: `DATA_RELIABILITY_HARVEST_BATCH_2026_09_09.md`

Produced:

- PR #35 — malformed provider numerics become explicit Health evidence instead of adapter crashes; current automated gates are green.
- PR #36 — stale-good-health revocation for empty/invalid timestamp batches; stacked and still lacks independent CI.
- deliberate non-adoption of Pandera/GX-style heavy schema tooling for local boundary-semantics defects.

### Strategy Validation temporal-leakage batch

See: `STRATEGY_VALIDATION_HARVEST_BATCH_2026_09_09.md`

Produced:

- PR #38 — implementation-level prefix-invariance audit + startup-history sensitivity audit;
- permanent future-dependent implementation adversarial coverage;
- CI execution-list repair so the new test cannot exist without actually running in the focused workflow.

Promotion truth at latest sync: `VALIDATING` with focused suite PASS; main CI pending.

## Remaining near-term harvesting priority

Completed/advanced items are removed from the top of this queue rather than being repeatedly listed as future work.

1. Network/provider fault matrix using Toxiproxy-style reproducible faults, but only if the environment can keep lifecycle cleanup deterministic.
2. Deeper Nautilus reconnect/resubscription test-fixture harvest, especially transport-restored vs data-trusted separation.
3. After #35 becomes the validated base, independently validate stacked Data R2 / PR #36.
4. Lean transaction/fill/slippage test matrix for later Strategy Lab; no production execution scope expansion.
5. Qlib Experiment/Recorder ideas for Benchmark Harness / Model Evaluation Lab lineage.
6. vn.py gateway/provider-specific audit for China-market adapter ideas without importing auto-order scope.

## Governing rule

> Borrow aggressively. Trust nothing. Validate everything.

Harvest increases Radar quality only when external ideas are translated into Radar-native contracts, adversarial evidence, and independently reproducible validation. Code volume, stars, framework breadth, or dependency count are not success metrics.
