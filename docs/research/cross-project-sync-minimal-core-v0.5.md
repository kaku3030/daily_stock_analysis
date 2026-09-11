# STOCK RAZOR — Minimal Core Cross-Lane Sync V0.5

**Status:** RESEARCH / SHADOW  
**Source:** Cross-Lane Research Auditor / Integration Review  
**Production authority:** unchanged  
**Sync to:** AI_MONITOR/HARVEST, AI_MONITOR/CONTROL_TOWER, RADAR/HARVEST, RADAR/CONTROL_TOWER, RADAR/PERCEPTION_DATA_INTELLIGENCE

## Delta since V0.4

Minimal Core continues to avoid duplicating work already delegated under E01/E03/E05/E06/E07.

New bounded work now has concrete repository artifacts:

- **E08 — Config Drift Inventory**
  - keeps `ConfigManager` as a separate deep module;
  - compares duplicated field facts across runtime config, UI registry and `.env.example`;
  - records historical upstream documentation links as a real drift signal;
  - begins with a small LLM-backend config family, not a wholesale config rewrite.

- **E10 — Failure Taxonomy Shadow**
  - identifies a narrow shared transport-category surface in Efinance and AkShare;
  - adds executable Shadow evidence comparing both existing classifiers on identical exceptions;
  - preserves native error detail;
  - explicitly keeps classification separate from retry/fallback/cooldown/routing.

- **E11 — Cache Semantics Inventory**
  - inventories Efinance/AkShare realtime caches, AkShare HK failure-aware cache, Longbridge static-info cache and pipeline memoization as different semantic groups;
  - forbids treating circuit breakers, Currentness, Portfolio, Delivery or lifecycle state as generic caches;
  - corrects prior research drift: `cachetools` is **not** currently declared in root requirements.

- **E12 — Symbol Semantics Shadow**
  - separates canonical identity, lookup aliases and provider wire symbols;
  - treats the existing JP/KR/TW table-driven suffix helper as a good small-core pattern;
  - keeps provider wire formatting adapter-local;
  - requires explicit ambiguity/UNKNOWN handling rather than guessing.

## New executable Shadow evidence

`tests/test_minimal_core_e10_failure_taxonomy_evidence.py`

Current bounded evidence checks that existing Efinance and AkShare classifiers agree for:

```text
remote_disconnect
timeout
rate_limit_or_anti_bot
request_error
unknown_request_error
```

and that provider-native detail is retained.

Passing this test does **not** freeze a new taxonomy and does not authorize a production shared helper.

## Ownership / next actions

### AI_MONITOR/HARVEST

Continue E03/E05/E07 as already delegated.

For **E10-B**, inventory repeated failure-classification sites and record whether each site also mutates retry/fallback/cooldown. Do not change production code.

For **E11**, help classify provider cache/cooldown semantics. Do not create a universal cache manager.

### AI_MONITOR/CONTROL_TOWER

Own any later production promotion for E08/E10/E11 where runtime/provider/config boundaries are affected.

Reject abstractions that create a second runtime state owner or couple failure classification to retry/routing.

### RADAR/HARVEST

Continue E06.

Lead **E09 Pipeline/read-set** exploration and assist **E12** semantic simplification from an Agent-read-set perspective.

### RADAR/PERCEPTION_DATA_INTELLIGENCE

Support **E10** with real provider error evidence, **E11** with freshness/staleness semantics, and **E12** with provider-native symbol/timestamp semantics and adversarial fixtures.

Do not implement a second provider/currentness runtime.

### RADAR/CONTROL_TOWER

Review E09/E12 against Candidate/Gate/Replay/Lifecycle contracts before any promotion.

## Shared promotion rule

Every proposed abstraction must return:

```text
net_complexity_result = SMALLER | SAME | LARGER | UNKNOWN
```

Only `SMALLER` may continue toward production promotion.

`SMALLER` must mean fewer semantic owners / duplicated branches / read-set, not merely fewer lines or files.

## Protected invariants

No Minimal Core work may weaken:

- canonical raw evidence;
- `UNKNOWN` / `INDETERMINATE`;
- timestamp/currentness semantics;
- entitlement/subscription evidence;
- provider identity/provenance;
- Gate/reason/risk fields;
- Portfolio runtime truth;
- lifecycle/replay determinism;
- fail-loud behavior where evidence is incomplete.

## Current promotion status

```text
E08: SHADOW / INVENTORY
E10: SHADOW; E10-A evidence implemented, E10-B inventory next
E11: INVENTORY FIRST
E12: SHADOW / FIXTURE DESIGN
```

No production promotion is authorized by this sync packet.

## Next validation conditions

1. latest PR #71 exact head must pass Repository CI + Research Radar Tests;
2. E10-B must show enough repeated semantics to justify a shared primitive;
3. E08 bounded config matrix must identify actual duplicate facts before schema prototyping;
4. E11 inventory must distinguish cache vs authoritative timed state;
5. E12 fixture corpus must expose current disagreements before any consolidation;
6. each candidate must demonstrate lower Agent read-set or semantic-owner count.

## MINIMAL_CORE_SYNC_PACKET

```text
timestamp: 2026-09-11 JST
source_lane: CROSS_LANE_RESEARCH_AUDIT
scope: E08/E10/E11/E12 expansion
production_behavior_change: NONE
new_executable_evidence: E10-A classifier differential
protected_invariants: PRESERVED BY SCOPE
conflicts_with_other_lanes: NONE KNOWN; E01/E03/E05/E06/E07 ownership unchanged
promotion_status: SHADOW / INVENTORY ONLY
data_confidence: HIGH for cited repository facts; UNKNOWN for unmeasured complexity/token savings
next_validation: exact-head CI + inventories/fixtures described above
```