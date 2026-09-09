# Open-Source Intake / Harvesting Lane — Sync 2026-09-09

Status: ACTIVE SUB-LANE under the Stock Razor / Radar program.

## Coordination rule
- This chat/workstream is the **Open-Source Intake / Harvesting Lane**.
- Peer sub-lane: **Architecture & Promotion Control Tower**.
- Both report into the Radar main engineering line / 总工程.
- Harvest Lane owns external discovery, screening, gap analysis, harvesting, defect audit, hardening candidates, adversarial validation evidence, and promotion-ready handoff packages.
- Harvest Lane does **not** unilaterally reopen frozen architecture or promote work to SHADOW/CORE.
- Architecture/Promotion decisions remain governed by the Control Tower and Radar main line.
- Durable synchronization is written to shared GitHub governance/evidence surfaces so all lanes read the same source of truth rather than rely on conversational memory.

## Current Harvest outputs

### LiveFeed / provider reliability
- PR #30 — stale/foreign ProviderEvent identity relevance repair; validated exact head had Research Radar Tests + repository CI PASS.
- PR #32 — Hypothesis state-machine testing for LiveFeed invariants; validated exact head had automated gates PASS.
- Network-fault audit: current localhost TransportProxy is sufficient for CUT/RESTORE P0, so Toxiproxy remains deferred.
- Blocking-provider-call audit: stdlib ProcessPoolExecutor rejected as a strict hard-timeout boundary.
- Provider Worker Supervisor V0.1 reached DESIGN:FROZEN after staged adversarial reviews; implementation remains separately sliced and outside Harvest promotion authority.

### Futu K_15M / K_60M currentness authority — P0 blocker
- Radar main engineering requested authoritative provider semantics before freezing realtime_monitor 15m/1h currentness timing.
- Official Futu v10.10 docs define `time_key` only as Time / Candlestick time; they do **not** define bar-start vs bar-end semantics for K_15M or K_60M.
- Existing controlled evidence only establishes interval-end-like behavior for tested HK K_1M and cannot be generalized to US K_15M/K_60M.
- US K_60M 09:30-anchor vs clock-hour alignment remains UNKNOWN.
- K_15M/K_60M forming-bar behavior, same-day historical forming-row inclusion, close behavior, and half-day construction remain UNKNOWN.
- Provider-evidence recommendation: `BLOCK_CURRENTNESS_TIMING_FREEZE`; use `CURRENTNESS_UNVERIFIED` rather than inventing a threshold.
- Draft PR #41 — `P0 Evidence: Futu K_15M/K_60M timestamp semantics`.
- PR #41 contains only evidence tools, tests, CI wiring and governance/docs; no production currentness/provider/trading code.
- Executable closure pack on #41:
  - `kline_timestamp_probe.py`: bounded long live callback capture only;
  - `kline_snapshot_probe.py`: per-RPC bounded current/history observations;
  - `analyze_kline_timestamp_semantics.py`: offline mechanical observations only;
  - `tests/test_futu_kline_timestamp_semantics_tools.py`: mechanics / anti-false-promotion tests.
- Safety split: long live callback capture is physically separated from synchronous snapshot/history RPCs so a hanging SDK call cannot destroy the long capture.
- Same-day historical observation derives date from `America/New_York`, not execution-host timezone.
- Research Radar workflow has explicit path trigger + pytest execution for the closure-pack mechanics tests.
- Semantic promotion remains manual/provider-evidence review only. The analyzer cannot self-declare VERIFIED.
- Current pre-CI branch head: `8bd99c51a69a36be225fbadbc339d31fe59fb7f1` before this sync-only commit. CI truth must be checked on the resulting current PR head; do not inherit earlier checks.

### Data Reliability
- PR #35 — malformed provider numerics become explicit Health evidence; automated gates passed on validated head.
- PR #36 — stale-good-health revocation candidate remains stacked / requires independent validation before promotion.
- Currentness/Continuity audit found intraday false-green risk: same trading date does not prove current progress.

### Strategy Validation
- PR #38 — Radar-native temporal leakage / startup-history audit harvested from Freqtrade methodology without GPL source coupling; automated gates passed on exact head.

### A-share provider lane
- A-share is a first-class Harvest track.
- Existing Stock Razor / upstream DSA already contains mature multi-source provider assets: Efinance, AkShare, Tencent, PyTDX, BaoStock, Tushare, TickFlow and route/fallback tests.
- Decision: do not rebuild the A-share provider framework from zero; harvest mature implementation and repair only gaps against Radar frozen invariants.
- Key gaps: adapter-vs-upstream lineage, shared upstream double-count risk, malformed-vs-missing evidence, TTL≠Currentness, monotonic breaker timing, and missing explicit 15m/1H/calendar/corporate-action/PIT-fundamental capabilities.
- PR #40 — `A-share A0.1: freeze realtime provider lineage identity` remains Draft, schema/test-only, no routing change.
- PR #40 exact head `e4a8c5a3e6f1220bc86173fb860a2136f111b109`: Research Radar Tests PASS; repository CI PASS.
- Harvest terminology: #40 is `VALIDATING`, not SHADOW/CORE.

## Next Harvest priorities
1. Verify current exact-head CI for PR #41 and repair any mechanics failure.
2. Execute/review Futu US K15/K60 closure pack when a reachable OpenD + relevant US session window is available; keep currentness timing freeze blocked until then.
3. A-share A0.2 additive DataCapability lineage exposure and reconciliation-safe tests, without routing changes.
4. A-share intraday capability inventory for 15m/1H and currentness evidence boundaries.
5. Continue Currentness / Continuity / RecoveryCandidate harvest against frozen LiveFeed contracts.
6. Validate stacked Data R2 independently after its base is stable.

## Handoff truth
Harvest produces evidence and bounded adaptations. Promotion authority remains with Radar main engineering / Architecture & Promotion Control Tower.
