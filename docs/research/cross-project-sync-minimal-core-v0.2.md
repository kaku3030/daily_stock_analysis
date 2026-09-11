# CROSS-PROJECT SYNC — Minimal Core Initiative V0.2 Delta

Timestamp: 2026-09-11 JST  
Canonical PR: #71  
Source: Minimal Core Initiative V0.2 Deep Harvest  
Status: RESEARCH / SHADOW ONLY — NO PRODUCTION BEHAVIOR CHANGE

## Delta since V0.1

V0.2 moves Minimal Core from a reference list into a repo-mapped, measurable program.

New external design references:

- `python-hyper/h11` — Sans-I/O / pure protocol state
- Hypothesis stateful testing — generated action sequences + invariants
- SQLite VDBE architecture — compact explicit intermediate execution model
- John Ousterhout — deep modules / information hiding
- Trio — structured concurrency / owned task lifetime
- `pytest-dev/pluggy` — narrow extension contracts, with strong anti-premature-plugin guard

New repo findings:

1. `compare_analysis_states()` already provides a Razor-native precedent for a pure deterministic semantic core.
2. Currentness already has explicit deterministic statuses/reason codes and is suitable for differential replay/state modeling.
3. Delivery transport deliberately uses single-attempt/no-retry semantics; generic retry consolidation must not override it.
4. Root requirements confirm `tenacity` and `schedule`; the V0.1 statement that `cachetools` is already installed is not supported and is corrected by V0.2.
5. Future Harvest must distinguish three claims: external design value, installed dependency status, and actual runtime usage.

## Shared rule for every lane

A simplification is valid only when it reduces **semantic complexity**, not merely LOC.

Measure:

- authoritative state owners
- decision branches
- duplicated contracts/schema definitions
- module fan-out
- mixed I/O + decision sites
- safe-change agent read-set
- representative context tokens
- hidden fallbacks
- governed bypass paths
- replay determinism
- UNKNOWN/currentness semantic preservation

If LOC decreases while ambiguity, hidden fallback, duplicate authority, or bypass risk increases, reject the simplification.

## AI_MONITOR/HARVEST

Priority:

1. MCI-E01 Currentness Differential Replay design
2. MCI-E03 Retry Semantic Inventory
3. MCI-E05 Provider Escape-Surface Audit
4. map worker/background task ownership before any structured-concurrency proposal
5. measure agent read-set/token cost for representative runtime fixes

Harvest principle:

```text
I/O adapter → normalized event/evidence → pure semantic core → governed state → I/O shell
```

Headroom remains downstream-only LLM projection/compression research.

## AI_MONITOR/CONTROL_TOWER

Promotion authority remains here for Provider Worker, LiveFeed, Currentness runtime, Portfolio runtime truth, continuity/restart, notifications and AI runtime.

Do not approve a simplification without:

- before/after semantic-complexity metrics
- differential/replay evidence
- protected-field inventory
- adversarial UNKNOWN/currentness tests
- rollback
- proof that production ownership remains singular

Delivery no-retry semantics are protected unless a separately governed design explicitly changes policy.

## RADAR/HARVEST

Apply V0.2 principles to:

- Replay/OOS loops
- Gate evaluation
- model evaluation harness
- lifecycle research
- research orchestration

Preferred shape: pure fixture-driven transformations and explicit rule tables where semantics are stable. Do not create a generic IR/VM merely because SQLite uses one.

## RADAR/CONTROL_TOWER

Reject any simplification that:

- reintroduces compensatory scoring
- moves Gate authority into narrative/model output
- creates duplicated lifecycle state
- weakens replay determinism
- hides UNKNOWN/risk flags

Track agent read-set as an architecture metric for research tasks too.

## RADAR/PERCEPTION_DATA_INTELLIGENCE

Own fixture/evidence contribution for MCI-E01/E04/E05:

- pre-open / open / lunch / resume / close
- weekend / holiday
- timezone/session boundary
- missing/future timestamp
- delayed provider
- disconnect/reconnect
- entitlement loss/restore
- partial timeframe availability

This lane remains research/perception only and must not implement a second Currentness runtime.

## STOCK RAZOR｜Main Control & Trading Desk

No portfolio/trading behavior changes from this initiative.

Consume only promoted engineering outcomes that preserve the existing analysis/trading contracts. Treat architectural simplification as reliability/velocity work, not as new market evidence.

## STOCK RAZOR｜A-Share Radar

No signal/gate change. When future simplification touches A-share provider or session semantics, validate against A-share calendar/lunch/session fixtures before promotion.

## STOCK RAZOR｜US Stock Radar

No signal/gate change. When future simplification touches US provider/session semantics, validate market-session/timezone/currentness behavior independently rather than assuming A-share rules transfer.

## STOCK RAZOR｜Global Policy Intelligence

No macro/policy intelligence change. External software-design research belongs to engineering Harvest and must not be mixed into policy-event confidence or market transmission scoring.

## Experiment queue

- **MCI-E01** — Currentness Differential Replay
- **MCI-E02** — Trigger Pure-Core Read-Set Benchmark
- **MCI-E03** — Retry Semantic Inventory
- **MCI-E04** — Generated Currentness State Sequences
- **MCI-E05** — Provider Escape-Surface Audit

## Promotion state

```yaml
minimal_core_v0_2: RESEARCH
h11_sans_io_principle: ADAPT_CANDIDATE
hypothesis_stateful_testing: TEST_SHADOW
sqlite_ir_principle: ADAPT_NARROWLY
ousterhout_deep_modules: ADAPT_CANDIDATE
trio_structured_concurrency: SHADOW_PRINCIPLE
pluggy_extension_model: SHADOW_LIKELY_REJECT_UNTIL_PRESSURE_PROVEN
headroom: SHADOW_ONLY
production_runtime_changes: NONE
```

## CONTROL_TOWER_SYNC_PACKET

```yaml
timestamp: 2026-09-11
source_lane: MINIMAL_CORE_INITIATIVE
version: V0.2
market_regime_change: NONE
crisis_level_risk_budget_implication: NONE
new_hard_catalysts: NONE
sector_theme_state_changes: NONE
capital_persistence_changes: NONE
relative_strength_changes: NONE
entry_gate_changes: NONE
exit_risk_changes: NONE
portfolio_relevant_impacts: NONE
cross_market_transmission: NONE
urgent_main_attention: NONE
engineering_findings:
  - pure semantic core pattern already exists in compare_analysis_states
  - Currentness is first high-value differential-replay candidate
  - Delivery single-attempt/no-retry semantics are protected
  - cachetools installed-dependency claim corrected to unsupported
next_validation_conditions:
  - MCI-E01 design + fixture matrix
  - MCI-E03 retry inventory
  - MCI-E05 provider escape-surface baseline
  - read-set/token baseline for representative fixes
data_confidence:
  repo_facts: HIGH
  architecture_transferability: MEDIUM_HIGH
  measured_speed_token_savings: UNKNOWN_PENDING_BENCHMARK
```

**Sync to:** `AI_MONITOR/HARVEST`, `AI_MONITOR/CONTROL_TOWER`, `RADAR/HARVEST`, `RADAR/CONTROL_TOWER`, `RADAR/PERCEPTION_DATA_INTELLIGENCE`, `STOCK RAZOR｜Main Control & Trading Desk`, `STOCK RAZOR｜A-Share Radar`, `STOCK RAZOR｜US Stock Radar`, `STOCK RAZOR｜Global Policy Intelligence`.
