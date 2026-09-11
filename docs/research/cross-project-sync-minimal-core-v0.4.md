# STOCK RAZOR Cross-Project Sync — Minimal Core V0.4

**Sync type:** delta packet  
**Supersedes no prior packet:** V0.1–V0.3 remain historical baselines  
**Production behavior change:** none

## Global delta

Minimal Core V0.4 adds five research surfaces without creating a new lane:

- **E08** Config Surface / Single-Source Metadata
- **E09** Pipeline Stage Contract / Read-Set
- **E10** Stable Provider Failure Taxonomy
- **E11** Cache Semantics Inventory
- **E12** Symbol Semantics Consolidation

Canonical detailed spec:

- `docs/research/minimal-core-v0.4-next-hotspots.md`

Canonical external Harvest ledger:

- `docs/research/minimal-core-harvest-ledger-v0.2.md`

Important evidence correction:

- `cachetools` is **not** declared in root `requirements.txt`;
- `tenacity` and `schedule` are existing dependencies;
- repository/runtime truth overrides research notes and chat memory.

---

## AI_MONITOR/HARVEST

### New responsibilities

**E10 — Provider Failure Taxonomy**

Inventory duplicate provider failure classifiers and prototype a stable normalized taxonomy while preserving native details. Do not merge retry/fallback/cooldown/no-retry semantics; E03 remains authoritative for those policies.

**E11 — Cache Semantics Inventory**

Inventory provider/runtime caches before proposing a shared primitive. Record success TTL, negative TTL, cooldown, timer, lock, maxsize, invalidation and currentness risk.

**E08 contribution**

Supply runtime-config evidence where provider/AI invocation settings are involved.

### Hard limits

- no new provider runtime;
- no generic plugin framework;
- no conversion of Currentness/Portfolio/Delivery/Lifecycle truth into ordinary cache state;
- no new dependency unless net semantic complexity decreases.

---

## AI_MONITOR/CONTROL_TOWER

### New review scope

- E08 production-config ownership where runtime behavior is affected;
- E10 normalized failure semantics and their impact on retry/fallback/circuit breaker;
- E11 cache vs authoritative-state boundary.

Promotion requires differential evidence and rollback. Research prototypes are not production truth.

---

## RADAR/HARVEST

### New responsibilities

**E09 — Pipeline Stage Contract / Read-Set**

Map the existing end-to-end path as explicit stages and measure state owners/read-set. Do not introduce a workflow framework merely to make the diagram prettier.

**E12 contribution**

Study generic symbol-contract/read-set simplification and external small-core patterns.

Continue external Harvest using `ADOPT / ADAPT / SHADOW / REJECT` with explicit net-complexity accounting.

---

## RADAR/PERCEPTION_DATA_INTELLIGENCE

### New responsibilities

**E12 — Market/Symbol semantic fixtures**

Provide canonical and adversarial fixtures for CN/HK/US/JP/KR/TW identities, aliases and ambiguous forms.

**E10 — Provider-native failure evidence**

Provide observed provider error/status semantics needed to distinguish timeout/disconnect/rate-limit/auth/entitlement/protocol/contract/data-unavailable/unknown.

**E11 — Currentness risk evidence**

Identify where stale/negative/provider caches could create false freshness/currentness.

### Hard limit

Evidence/fixtures only. No second Provider Worker, LiveFeed, Currentness runtime or production router.

---

## RADAR/CONTROL_TOWER

Review whether E09/E12 simplification alters:

- Candidate/Gate contracts;
- RS / Capital Persistence;
- Lifecycle;
- Replay/OOS;
- Strategy Lab;
- Model Evaluation.

Reject changes that reintroduce hidden fallback, compensatory scoring, or parallel production decision semantics.

---

## Main Trading Desk / A-Share Radar / US Stock Radar / Global Policy Intelligence

No implementation work is required for E08–E12.

Consume sync only when a promoted change affects:

- data freshness/confidence;
- symbol/market identity;
- provider fallback/failure reporting;
- market/session interpretation;
- Candidate/Gate semantics;
- Portfolio runtime truth;
- Risk Budget inputs.

---

## Recommended research order

```text
E12 Symbol Contract audit
        +
E10 Failure Taxonomy audit
        ↓
E11 Cache Inventory
        ↓
E08 Config Pilot
        ↓
E09 Pipeline Stage Map
```

This is research priority, not permission to merge production refactors.

---

## Required return packet

Each participating lane should return the existing `MINIMAL_CORE_SYNC_PACKET` with:

```text
timestamp
source_lane
experiment_id
scope
current_behavior
shadow_behavior
evidence/tests/replay
protected_invariants
semantic_complexity_delta
agent_read_set_delta
token_delta_if_measured
new_dependency_delta
conflicts_with_other_lanes
UNKNOWN/currentness/entitlement impact
recommendation
promotion_status
rollback
next_validation_condition
data_confidence
```

For V0.4 add one explicit line:

```text
net_complexity_result = SMALLER / SAME / LARGER / UNKNOWN
```

A candidate with `LARGER` or `UNKNOWN` cannot be promoted merely because its code looks cleaner.

---

## Cross-lane invariant

> A new abstraction is a failure unless it removes more semantic complexity than it adds.

Research can proceed in parallel. Production ownership remains singular.
