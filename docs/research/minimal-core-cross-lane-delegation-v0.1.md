# STOCK RAZOR — Minimal Core Cross-Lane Delegation V0.1

**Date:** 2026-09-11  
**Status:** ACTIVE / research + Shadow only  
**Canonical initiative PR:** #71  
**Production behavior change:** none by this document  

`AI_MONITOR_PROVIDER_RUNTIME_PRODUCTION_APPROVAL_AUTHORITY = @kaku3030`. Valid
sign-off is an owner GitHub PR `APPROVED` review on the exact head, with the
review body confirming the concrete production scope, rollback, and ownership
boundary. A head change invalidates that approval; owner sign-off is not user
explicit authorization to implement.

## 1. Objective

Run Minimal Core work in parallel across the existing AI Monitor and Radar lanes instead of creating a new independent project lane.

The goal is not minimum LOC. The goal is **Minimum Semantic Code**:

- fewer authoritative state owners;
- fewer duplicated contracts and provider facts;
- fewer repeated decision branches;
- smaller agent read-set and tool-output context;
- lower diagnosis/review cost;
- preserved `UNKNOWN`, timestamp/currentness, entitlement/subscription, reason/risk and replay semantics.

Research may run in parallel. **Production ownership must remain singular.**

## 2. Global ownership boundary

### AI Monitor remains sole production owner of

- Provider Worker / provider runtime;
- LiveFeed runtime;
- Portfolio runtime truth;
- Currentness runtime enforcement;
- continuity / restart / reconciliation;
- notification runtime;
- AI invocation/runtime;
- Shadow/LIVE runtime.

### Radar remains sole owner of

- Candidate Discovery;
- Relative Strength;
- Capital Persistence;
- Lifecycle research;
- Replay/OOS research;
- Strategy Lab;
- Model Evaluation;
- Candidate/Research scoring.

### RADAR/PERCEPTION_DATA_INTELLIGENCE

Provides upstream research evidence, provider semantics, market microstructure, timestamp/currentness observations, raw capture/replay/fixtures and cross-market data semantics. It must not create a second Provider Worker, LiveFeed runtime or Currentness runtime.

## 3. Work allocation

### AI_MONITOR/HARVEST

Own research/Shadow evidence for:

- **E03 — Retry/Fallback Semantic Inventory**
  - classify retry vs provider fallback vs cooldown vs no-retry semantics;
  - finish Efinance single-attempt Tenacity differential evidence;
  - identify duplicated failure classification without collapsing different semantics;
  - output KEEP / SIMPLIFY / MERGE / DELETE / REJECT candidates.

- **E05 — Provider Escape Surface**
  - audit provider-specific facts leaking above `data_provider`;
  - compare current `DataCapabilityService` against a Shadow manager-owned read-only capability/routing snapshot;
  - reuse existing `tests/test_data_capability_service.py` as Golden Contract where applicable;
  - no plugin framework unless it demonstrably reduces total semantic complexity.

- **E07 — Headroom / Tool-Output Compression Benchmark**
  - benchmark only the LLM-facing tool-output layer;
  - never compress canonical raw evidence or canonical state;
  - protect `UNKNOWN`, timestamps/currentness, provider status, entitlement/subscription, gate/result/reason/risk, Portfolio State and lifecycle identifiers;
  - compare raw vs compressed outputs on the same model/task.

**Deliverable:** one evidence packet per experiment with current behavior, Shadow behavior, diff, semantic-complexity delta, rollback and promotion recommendation.

### AI_MONITOR/CONTROL_TOWER

Own final engineering governance for:

- **E01 — Currentness Differential Replay**;
- Promotion/rejection of E03/E05/E07 findings;
- ensuring all accepted changes preserve single runtime ownership;
- preventing simplification from weakening fail-loud, UNKNOWN, entitlement or Currentness semantics.

For E01, require the same fixtures against existing and Shadow core and compare at least:

- status;
- reason codes;
- `UNKNOWN`/indeterminate state;
- provider timestamp;
- expected session;
- currentness evidence;
- timezone/session boundaries.

No production Currentness replacement before differential/replay evidence closes.

### RADAR/PERCEPTION_DATA_INTELLIGENCE

Support E01/E05 with evidence only:

- pre-open / lunch / post-close / weekend / holiday fixtures;
- DST and timezone cases;
- missing/future/out-of-order timestamps;
- provider delay;
- disconnect/reconnect;
- entitlement/subscription loss;
- restart/continuity observations;
- raw provider-semantic examples.

**Restriction:** no second runtime implementation.

### RADAR/HARVEST

Own:

- **E06 — Agent Read-Set / Token Benchmark**;
- continued external Harvest for small-core engineering patterns;
- mapping external patterns to Razor hotspots before recommending adoption.

E06 must measure separately:

1. **Layer A — repository read-set**: files/bytes/tokens needed to safely complete a task;
2. **Layer B — tool output**: GitHub/CI/log/JSON payload context;
3. **Layer C — conversation/history**: prior design context required to resume work.

Do not claim token savings from file-size reduction alone.

External references should be judged `ADOPT / ADAPT / SHADOW / REJECT` and must include transferability, invariants at risk and likely read-set reduction.

### RADAR/CONTROL_TOWER

Review Minimal Core findings for impact on Radar-owned contracts:

- Candidate/Gate semantics;
- RS / Capital Persistence;
- Lifecycle;
- Replay/OOS;
- Strategy Lab;
- Model Evaluation.

Reject simplification that creates compensatory scoring, hidden fallbacks or a second production decision path.

### Main Control & Trading Desk / A-Share Radar / US Stock Radar / Global Policy Intelligence

These lanes are downstream consumers, not implementers of Minimal Core runtime work.

They should be notified only when a promoted change affects:

- data freshness/confidence;
- market/session interpretation;
- provider availability/fallback;
- candidate/gate semantics;
- portfolio runtime truth;
- risk budget or trading-desk inputs.

No direct production code ownership is transferred to these lanes.

## 4. Cross-Lane Research Auditor / Integration Reviewer

The coordinating reviewer is **not a new independent lane**.

Review only at key checkpoints:

1. **Design / Spec Locked**
2. **Shadow Evidence Ready**
3. **Promotion Candidate**

At those checkpoints perform cross-lane conflict review and issue one of:

- KEEP
- SIMPLIFY
- MERGE
- DELETE
- SHADOW MORE
- REJECT

The purpose is to detect conflicts between locally-correct lane decisions, not to reimplement every experiment.

## 5. Common promotion gate

No Minimal Core finding reaches production solely because it reduces LOC.

Required evidence:

- differential/replay equivalence unless an existing bug is explicitly accepted;
- exactly one authoritative production owner;
- fail-loud behavior where evidence is incomplete;
- preserved `UNKNOWN` / indeterminate semantics;
- preserved timestamps, timezone/session and provider evidence;
- preserved entitlement/subscription semantics;
- preserved reason/risk/gate fields;
- unchanged or explicitly governed fallback/routing behavior;
- adversarial / negative / bypass tests;
- lower semantic complexity or read-set;
- explicit rollback.

For Headroom/tool-output compression additionally require:

- Critical Field Recall = 100%;
- deterministic Gate/Currentness/Candidate equivalence = 100%;
- protected reason/risk field retention = 100%;
- `UNKNOWN → known` corruption = 0;
- invented timestamp/provider state = 0;
- only after correctness closes, evaluate token reduction.

## 6. Standard return packet

Each lane should return:

```text
MINIMAL_CORE_SYNC_PACKET
- timestamp
- source_lane
- experiment_id
- scope
- current_behavior
- shadow_behavior
- evidence/tests/replay
- protected_invariants
- semantic_complexity_delta
- agent_read_set_delta
- token_delta_if_measured
- conflicts_with_other_lanes
- UNKNOWN/currentness/entitlement impact
- recommendation: KEEP|SIMPLIFY|MERGE|DELETE|SHADOW_MORE|REJECT
- promotion_status
- rollback
- next_validation_condition
- data_confidence
```

## 7. Current experiment state to continue from

- **E01 Currentness Differential Replay:** specification exists; continue fixture/replay execution.
- **E03 Retry/Fallback:** audit exists; Efinance single-attempt Tenacity Shadow test exists; continue evidence, do not collapse AkShare transient retry with source fallback or Delivery no-retry semantics.
- **E05 Provider Escape Surface:** audit exists; use existing DataCapabilityService tests as Golden Contract; compare a manager-owned read-only capability/routing snapshot in Shadow only.
- **E06 Agent Read-Set / Token Benchmark:** measure Layer A/B/C separately; no token-saving claim without measurement.
- **E07 Headroom:** Shadow only; LLM-facing tool-output compression only; canonical truth remains uncompressed/retrievable.

## 8. Fixed global rule

> Research can be parallel. Production ownership must be unique.

> The target is not fewer files. The target is fewer semantic owners, fewer duplicated contracts, smaller read-set, faster diagnosis and equal-or-better reliability.

Sync to: `AI_MONITOR/HARVEST`, `AI_MONITOR/CONTROL_TOWER`, `RADAR/HARVEST`, `RADAR/CONTROL_TOWER`, `RADAR/PERCEPTION_DATA_INTELLIGENCE`, `STOCK RAZOR｜Main Control & Trading Desk`, `STOCK RAZOR｜A-Share Radar`, `STOCK RAZOR｜US Stock Radar`, `STOCK RAZOR｜Global Policy Intelligence`.
