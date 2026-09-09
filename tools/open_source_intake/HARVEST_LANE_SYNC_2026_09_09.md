# Open-Source Intake / Harvesting Lane — Sync 2026-09-09

Status: ACTIVE SUB-LANE under the Stock Razor / Radar program.

## Coordination rule
- This chat/workstream is the **Open-Source Intake / Harvesting Lane**.
- Peer sub-lane: **Architecture & Promotion Control Tower**.
- Both report into the Radar main engineering line / 总工程.
- Harvest Lane owns external discovery, screening, gap analysis, harvesting, defect audit, hardening candidates, adversarial validation evidence, and promotion-ready handoff packages.
- Harvest Lane does **not** unilaterally reopen frozen architecture or promote work to SHADOW/CORE.
- Architecture/Promotion decisions remain governed by the Control Tower and Radar main line.
- Durable synchronization should be written to shared GitHub governance/evidence surfaces so all lanes read the same source of truth rather than rely on conversational memory.

## Current Harvest outputs

### LiveFeed / provider reliability
- PR #30 — stale/foreign ProviderEvent identity relevance repair; Research Radar Tests and repository CI have passed on its validated exact head.
- PR #32 — Hypothesis state-machine testing for LiveFeed invariants; automated gates passed on its validated exact head.
- Network-fault audit completed; existing localhost TransportProxy is sufficient for current cut/restore P0, so Toxiproxy remains deferred.
- Blocking-provider-call audit completed; stdlib ProcessPoolExecutor rejected as a strict hard-timeout boundary.
- Provider Worker Supervisor V0.1 reached DESIGN:FROZEN after staged adversarial reviews; implementation is intentionally narrow-sliced and remains separate from promotion.

### Futu K_15M / K_60M currentness authority — P0 blocker
- Radar main engineering requested authoritative provider semantics before freezing realtime_monitor 15m/1h currentness rules.
- Official Futu v10.10 docs define `time_key` only as Time / Candlestick time; they do **not** define bar-start vs bar-end semantics for K_15M or K_60M.
- Existing controlled evidence only establishes interval-end-like behavior for tested HK K_1M and cannot be generalized to US K_15M/K_60M.
- US K_60M 09:30-anchor vs clock-hour alignment remains UNKNOWN.
- K_15M/K_60M forming-bar behavior, same-day historical forming-row inclusion, close behavior, and half-day construction remain UNKNOWN.
- Provider-evidence recommendation: `BLOCK_CURRENTNESS_TIMING_FREEZE`; use `CURRENTNESS_UNVERIFIED` rather than inventing a threshold.
- Draft PR #41 — `P0 Evidence: Futu K_15M/K_60M timestamp semantics`.
- PR #41 remains evidence/test/CI only; no production code changes.
- Executable closure pack now exists on #41:
  - `kline_timestamp_probe.py`: bounded long live callback capture only;
  - `kline_snapshot_probe.py`: per-RPC bounded current/history observations;
  - `analyze_kline_timestamp_semantics.py`: offline mechanical observations only;
  - `tests/test_futu_kline_timestamp_semantics_tools.py`: mechanics / anti-false-promotion tests.
- Critical safety split: long live callback capture is physically separated from synchronous snapshot/history RPCs so a hanging SDK call cannot destroy the long capture.
- Same-day historical observation derives date from `America/New_York`, not the execution host timezone.
- Research Radar CI is explicitly wired to execute the closure-pack mechanics tests.
- Semantic promotion remains manual/provider-evidence review only. The analyzer cannot self-declare VERIFIED.

### Data Reliability
- PR #35 — malformed provider numerics become explicit Health evidence instead of silent/coerced success; automated gates passed.
- PR #36 — stale-good-health revocation candidate remains stacked / requires independent validation before promotion.
- Currentness/Continuity audit found the intraday false-green risk: same trading date does not prove current progress.

### Strategy Validation
- PR #38 — Radar-native temporal leakage / startup-history audit harvested from Freqtrade methodology without GPL source coupling; automated gates passed on exact head.

### A-share provider lane
- A-share is now a first-class Harvest track, not a later add-on.
- Existing Stock Razor / upstream DSA implementation already contains a mature multi-source provider layer: Efinance, AkShare, Tencent, PyTDX, BaoStock, Tushare, TickFlow and related route/fallback tests.
- Decision: do not rebuild the A-share provider framework from zero; harvest the mature implementation and repair only gaps against Radar frozen invariants.
- Key gaps identified:
  1. adapter identity vs upstream data lineage are currently conflated;
  2. multiple wrappers may hit the same upstream family (e.g. Eastmoney), so naive reconciliation could double-count one source;
  3. malformed vs missing must remain distinct evidence;
  4. wall-clock TTL/staleness cannot substitute for Currentness/LIVE qualification;
  5. circuit-breaker elapsed/deadline logic should converge on monotonic time;
  6. 15m / 1H / trading calendar / corporate actions / point-in-time fundamentals still need explicit capability contracts.
- PR #40 — `A-share A0.1: freeze realtime provider lineage identity` opened as a Draft, schema/test-only slice. It does not change routing or live behavior.
- PR #40 exact head `e4a8c5a3e6f1220bc86173fb860a2136f111b109`: Research Radar Tests PASS; repository CI PASS.
- Therefore PR #40 may be considered `VALIDATING` in Harvest terminology, but remains Draft and is not SHADOW/CORE.

## External candidate dispositions
- Hypothesis: DIRECT USE for tests / VALIDATING.
- Toxiproxy: TEST-REUSE candidate; defer dependency until fine-grained latency/jitter/asymmetry faults become explicit acceptance criteria.
- Nautilus Trader: ADAPT / TEST-REUSE methodology source for reconnect/reconciliation sequencing.
- Freqtrade: TEST-REUSE / METHOD HARVEST for lookahead/temporal-leakage validation.
- Lean: ADAPT / TEST-REUSE later for execution realism / Strategy Lab.
- Qlib: ADAPT / TEST-REUSE later for experiment lineage / Benchmark Harness.
- vn.py: ADAPT / TEST-REUSE for China-market gateway/provider patterns; do not import auto-order scope.
- AKShare: broad A-share enrichment/data candidate; validate endpoint-by-endpoint, never treat aggregate library identity as independent upstream lineage.
- mootdx/TDX: fallback / protocol-method candidate; pytdx upstream is archived, so no new direct dependency should be assumed without review.
- BaoStock: historical/backfill/cross-check candidate, not a realtime production primary.
- Tushare: token/service-backed candidate whose entitlement, limits, fields, latency and cost must be explicit capability metadata.
- TickFlow: existing optional A-share provider already present in Stock Razor; useful, but permission/capability semantics remain explicit.

## Next Harvest priorities
1. Execute/review Futu US K15/K60 closure pack when a reachable OpenD + relevant US session window is available; keep currentness timing freeze blocked until then.
2. A-share A0.2 additive DataCapability lineage exposure and reconciliation-safe tests, without routing changes.
3. A-share intraday capability inventory for 15m/1H and currentness evidence boundaries.
4. Continue Currentness / Continuity / RecoveryCandidate harvest against frozen LiveFeed contracts.
5. Validate stacked Data R2 independently after its base is stable.
6. Keep Control Tower/main line informed of any architecture-impacting finding before implementation exceeds frozen boundaries.

## Handoff truth
Harvest produces evidence and bounded adaptations. Promotion authority remains outside this lane.
