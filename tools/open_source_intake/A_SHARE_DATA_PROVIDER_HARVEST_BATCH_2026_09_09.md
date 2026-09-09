# Open-Source Intake — A-share Data Provider Harvest Batch 2026-09-09

Status: RESEARCH / GAP-ANALYSIS / ADAPTATION LEDGER. Non-production.

## Goal

Make A-share market-data providers a first-class Stock Razor Foundation concern without creating a new provider framework where mature implementation already exists.

## Key discovery

The upstream DSA implementation already contains a mature multi-source A-share layer, including Efinance, AkShare, Tencent, PyTDX, BaoStock, Tushare, TickFlow and related routing/fallback tests. Stock Razor also retains provider-capability definitions and scenario-aware routing concepts.

Decision:

> **Do not rebuild the A-share provider framework from zero. Harvest the existing mature implementation, then repair only gaps against Radar frozen invariants.**

## Candidate disposition

### AKShare
- broad A-share coverage and useful research/enrichment surface;
- multiple AkShare routes may ultimately wrap different external upstreams;
- library identity must not be used as upstream independence identity;
- endpoint-by-endpoint semantics, timestamps and availability remain subject to validation.
- disposition: `ADAPT / TEST-REUSE`, not sole production authority.

### Efinance
- existing Eastmoney-oriented path;
- useful realtime/daily fallback implementation;
- must be lineage-linked with other Eastmoney-backed routes so reconciliation does not double count one upstream.
- disposition: `ADAPT`.

### Tencent / AkShare Tencent
- current realtime source token `tencent` belongs to the AkShare/Tencent realtime route;
- separate `TencentFetcher` exists for daily/index use;
- adapter identity and upstream identity therefore must stay separate.
- disposition: `ADAPT`, identity repair required.

### PyTDX / TDX
- useful protocol/fallback ideas, multi-server retry behavior and no-token access;
- pytdx upstream is archived, so new direct dependency assumptions require review;
- existing cooldown uses wall-clock time and should not become the Foundation deadline pattern.
- disposition: `ADAPT / METHOD HARVEST`; prefer maintained implementations where needed.

### BaoStock
- historical/backfill/cross-check candidate;
- not a realtime production primary.
- disposition: `ADAPT / TEST-REUSE` for history/reconciliation.

### Tushare
- useful structured service/data candidate;
- token entitlement, rate limits, latency, fields and cost must be explicit capability metadata.
- disposition: `ADAPT` subject to entitlement/capability evidence.

### TickFlow
- already implemented as optional A-share provider with daily/realtime/index/market-review surfaces;
- uses monotonic timing for several caches/capability checks;
- permission/capability semantics are explicit enough to harvest;
- normalization still needs Radar's malformed-vs-missing discipline.
- disposition: `ADAPT`.

## Proven gaps against Radar Foundation invariants

1. **Adapter identity != upstream lineage.**
   - `efinance` and `akshare_em` are distinct code paths but both belong to Eastmoney lineage.
   - `akshare_qq` and realtime token `tencent` represent the same AkShare/Tencent route.
   - future reconciliation must not treat wrappers over one upstream as multiple independent votes.
2. **Malformed != missing.** Some existing convenience coercion collapses dirty tokens to `None`, which conflicts with Data R1's explicit `INVALID_NUMERIC` evidence discipline.
3. **TTL != Currentness.** Existing stale diagnostics may compare fetched/provider timestamps, but wall-clock age alone cannot become authoritative Currentness/LIVE qualification.
4. **Monotonic timing required for elapsed/deadline semantics.** Some legacy breaker/cooldown paths use `time.time()`.
5. **Capability vocabulary is incomplete for Radar.** Explicit contracts are still needed for at least 15m bars, 1H bars, trading calendar/session shape, corporate actions and point-in-time fundamentals.

## A0.1 — Realtime provider lineage identity

Draft PR #40: `A-share A0.1: freeze realtime provider lineage identity`

Introduced an immutable `RealtimeSourceLineage` manifest separating:

- `source_token`;
- `adapter_id`;
- `upstream_lineage_id`;
- `endpoint_id`;
- markets.

Important examples:

- `efinance` -> adapter `efinance`, upstream `eastmoney`;
- `akshare_em` -> adapter `akshare`, upstream `eastmoney`;
- `akshare_sina` -> adapter `akshare`, upstream `sina`;
- `akshare_qq` / `tencent` -> adapter `akshare`, upstream `tencent`, same semantic endpoint identity;
- `tushare` and `tickflow` retain their own lineage.

Anti-shrink test requires the manifest to exactly match currently admitted CN realtime source tokens.

## A0.2 — Reconciliation-safe upstream lineage view

PR #40 now also contains a second narrow adaptation:

`src/services/a_share_reconciliation_lineage.py`

Purpose:

- consume an **already selected / ordered** realtime route;
- expose which source tokens share an upstream lineage;
- preserve route position for diagnostics;
- group evidence by `upstream_lineage_id`;
- leave unknown lineage visible but `independence_eligible=False`;
- never select a provider, change priority, assign a decision weight, perform I/O or mutate Health/Currentness.

Permanent invariants/tests include:

- `efinance + akshare_em` count as one Eastmoney independence group;
- `tencent + akshare_qq` count as one Tencent independence group;
- unknown lineage must not receive a fabricated independent identity;
- route order before/after lineage inspection remains unchanged;
- providers/datasets/priorities/warnings from `DataCapabilityService` remain unchanged after lineage view construction;
- duplicate/malformed route tokens fail closed;
- no numeric/compensatory decision weight exists in source/group output;
- explicit governance is `decision_weighting = NONE`.

Research Radar workflow has explicit path triggers and pytest execution for both A0.1 and A0.2 tests plus existing `test_data_capability_service.py`.

## Current promotion truth

- Previous A0.1 exact head had Research Radar Tests + repository CI PASS.
- A0.2 changed the PR head and therefore resets validation truth.
- Current PR head must pass its own Research Radar and repository CI before being described as current-head VALIDATING.
- PR remains Draft; no SHADOW/CORE promotion is implied.

## Next A-share Harvest steps

1. Validate the exact A0.2 head.
2. After validation, consider only an ultra-thin additive read-only exposure from `DataCapabilityService`; do not couple lineage with provider routing.
3. Build explicit capability inventory for `bars.15m`, `bars.1h`, trading calendar/session shape, corporate actions and point-in-time fundamentals.
4. Audit intraday timestamp/currentness semantics provider-by-provider before any provider becomes currentness authority.
5. Keep historical/backfill and realtime authority separate; provider maturity is not permission to collapse those roles.

## Governing rule

> Different wrappers over one upstream do not become independent evidence merely because they have different Python class names.

Harvest implementation remains Foundation-compatible: identity / evidence / test / CI, no auto-trading or strategy-scope expansion.
