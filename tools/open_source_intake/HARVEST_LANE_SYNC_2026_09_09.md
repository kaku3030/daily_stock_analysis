# Open-Source Intake / Harvesting Lane — Sync 2026-09-09

Status: ACTIVE SUB-LANE under the Stock Razor / Radar program.

Governance: `CROSS_WINDOW_SYNC_CONSTITUTION_V0_1.md` applies to this status surface.

## CURRENT AUTHORITATIVE STATUS

This section is authoritative only for the exact heads stated below. Historical narrative below is retained for traceability and must not override this section.

### Provider Worker Supervisor V0.1 / Slice A

**STATUS DRIFT RESOLVED:** an earlier Harvest narrative described implementation as not yet started / intentionally separate. GitHub now contains a real implementation PR, so that wording is historical only.

`PR #42 | branch feature/live-feed-provider-worker-v0.1-slice-a | head 0d5f748cf9f52e3b8d6a2eb985c4db1750e88e8f | IMPLEMENTED (Slice A contracts/config only) | CI PASS | Research Radar Tests PASS | INDEPENDENT REVIEW ACCEPTED | PROMOTION: VALIDATING / ACCEPT | blocker: Slice B authorization NOT IMPLIED`

Dimensions:
- DESIGN STATUS: `DESIGN:FROZEN` for Provider Worker Supervisor V0.1 and Slice A brief.
- IMPLEMENTATION STATUS: Slice A implemented; exact PR changes are contracts/config/tests/public exports/CI wiring only.
- CI STATUS: exact-head repository CI SUCCESS; exact-head Research Radar Tests SUCCESS.
- REVIEW STATUS: independent review completed; no confirmed defects; architecture changes NONE.
- PROVIDER EVIDENCE STATUS: separate dimension; Slice A implementation does not close Futu provider-semantic unknowns.
- PROMOTION STATUS: `VALIDATING — ACCEPT`; not SHADOW/CORE; Slice B not authorized by this status.
- NOTE: frozen dataclasses containing `MappingProxyType` payloads are not necessarily hashable. Contract does not require hashability; this is NOTE-only, not a Slice A defect.

### Futu K_15M / K_60M timestamp semantics P0

`PR #41 | branch harvest/futu-kline-timestamp-semantics-p0 | head 7ccab96f3eea4b2e7b1141a4111c08ef12c444cd | EVIDENCE HARNESS/REPORT IMPLEMENTED | CI PASS | Research Radar Tests PASS | REVIEW: evidence scope reviewed, live semantic closure still pending | PROMOTION: N/A evidence track | blocker: controlled live US K_15M/K_60M observation required`

Dimensions:
- DESIGN STATUS: evidence-capture scope bounded; no production Currentness rule freeze.
- IMPLEMENTATION STATUS: evidence report + bounded read-only empirical closure tooling exist on the exact head.
- CI STATUS: exact-head repository CI SUCCESS; exact-head Research Radar Tests SUCCESS.
- REVIEW STATUS: tooling/evidence scope reviewed; no production implementation approval implied.
- PROVIDER EVIDENCE STATUS:
  - official documentation facts: partially verified where explicitly documented;
  - K_15M start-vs-end semantic: `UNKNOWN`;
  - K_60M start-vs-end semantic: `UNKNOWN`;
  - US K_60M RTH alignment / expected sequence: `UNKNOWN`;
  - K_15M/K_60M forming-bar semantic: `UNKNOWN`;
  - history API currently-forming-bar inclusion: `UNKNOWN`;
  - half-day interval truncation/alignment: `UNKNOWN`.
- PROMOTION STATUS: evidence track only; authoritative realtime_monitor 15m/1h Currentness timing freeze remains BLOCKED.
- GOVERNANCE: do not invent a Currentness threshold while required provider semantics remain UNKNOWN.

### A-share Provider Lineage A0.1

`PR #40 | branch harvest/a-share-provider-lineage-a0 | head e4a8c5a3e6f1220bc86173fb860a2136f111b109 | IMPLEMENTED A0.1 identity/schema/test slice | CI PASS | Research Radar Tests PASS | REVIEW: Harvest validation only | PROMOTION: VALIDATING | blocker: no routing change authorized; A0.2 remains separate`

Dimensions:
- DESIGN STATUS: A0 lineage identity contract established for current CN realtime tokens.
- IMPLEMENTATION STATUS: identity/schema/test-only slice implemented; no live routing change.
- CI STATUS: exact-head repository CI SUCCESS; exact-head Research Radar Tests SUCCESS.
- REVIEW STATUS: Harvest mechanical validation complete; no claim of independent promotion review unless separately recorded.
- PROVIDER EVIDENCE STATUS: per-provider semantics remain capability-specific and must not be inferred from adapter identity.
- PROMOTION STATUS: `VALIDATING`; Draft/unmerged; not SHADOW/CORE.

## Coordination rule
- This chat/workstream is the **Open-Source Intake / Harvesting Lane**.
- Peer sub-lane: **Architecture & Promotion Control Tower**.
- Both report into the Radar main engineering line / 总工程.
- Harvest Lane owns external discovery, screening, gap analysis, harvesting, defect audit, hardening candidates, adversarial validation evidence, and promotion-ready handoff packages.
- Harvest Lane does **not** unilaterally reopen frozen architecture or promote work to SHADOW/CORE.
- Architecture/Promotion decisions remain governed by the Control Tower and Radar main line.
- Durable synchronization should be written to shared GitHub governance/evidence surfaces so all lanes read the same source of truth rather than rely on conversational memory.

## Cross-lane sharing authorization
- The user has explicitly authorized the Radar main line, Open-Source Intake / Harvesting Lane, and Architecture & Promotion Control Tower to **actively share, retrieve, reuse, cite, and synchronize** project material among themselves without requesting per-item approval.
- This authorization covers project-relevant code, tests, evidence, provider semantics, research notes, frozen contracts, review findings, PR state, CI state, defects, fixtures, harvest candidates, validation artifacts, implementation briefs, and promotion-readiness evidence.
- A lane should proactively read another lane's durable GitHub evidence when that material can prevent duplicate work, conflicting assumptions, stale status, or architecture drift.
- Sharing does **not** transfer promotion authority: Harvest findings may be consumed by Control Tower/main line, but SHADOW/CORE decisions remain under the existing governance model.
- Existing frozen-scope boundaries still apply. Cross-lane access is permission to coordinate, not permission to silently expand product scope.
- The default coordination behavior is therefore **share-first / reuse-first**, not ask-first.

## Historical Record / prior Harvest outputs

The items below retain historical process context. Where they conflict with `CURRENT AUTHORITATIVE STATUS`, the current section wins.

### LiveFeed / provider reliability
- PR #30 — stale/foreign ProviderEvent identity relevance repair; Research Radar Tests and repository CI passed on its validated exact head.
- PR #32 — Hypothesis state-machine testing for LiveFeed invariants; automated gates passed on its validated exact head.
- Network-fault audit completed; existing localhost TransportProxy is sufficient for current cut/restore P0, so Toxiproxy remains deferred.
- Blocking-provider-call audit completed; stdlib ProcessPoolExecutor rejected as a strict hard-timeout boundary.
- Provider Worker Supervisor V0.1 reached `DESIGN:FROZEN` after staged adversarial reviews. Historical wording that implementation had not begun is superseded by PR #42 in `CURRENT AUTHORITATIVE STATUS`.

### Data Reliability
- PR #35 — malformed provider numerics become explicit Health evidence instead of silent/coerced success; automated gates passed on its validated exact head.
- PR #36 — stale-good-health revocation candidate remains stacked / requires independent exact-head validation before promotion.
- Currentness/Continuity audit found the intraday false-green risk: same trading date does not prove current progress.

### Strategy Validation
- PR #38 — Radar-native temporal leakage / startup-history audit harvested from Freqtrade methodology without GPL source coupling; automated gates passed on its validated exact head.

### A-share provider lane
- A-share is a first-class Harvest track.
- Existing Stock Razor / upstream DSA implementation already contains a mature multi-source provider layer: Efinance, AkShare, Tencent, PyTDX, BaoStock, Tushare, TickFlow and related route/fallback tests.
- Decision: do not rebuild the A-share provider framework from zero; harvest the mature implementation and repair only gaps against Radar frozen invariants.
- Key gaps identified:
  1. adapter identity vs upstream data lineage can be conflated;
  2. multiple wrappers may hit the same upstream family, so naive reconciliation could double-count one source;
  3. malformed vs missing must remain distinct evidence;
  4. wall-clock TTL/staleness cannot substitute for Currentness/LIVE qualification;
  5. circuit-breaker elapsed/deadline logic should converge on monotonic time;
  6. 15m / 1H / trading calendar / corporate actions / point-in-time fundamentals need explicit capability contracts.

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
1. Preserve #42 exact-head acceptance truth and do not imply Slice B authorization.
2. Finish bounded US Futu K_15M/K_60M empirical closure pack and preserve `UNKNOWN` until real evidence exists.
3. A-share A0.2 additive DataCapability lineage exposure and reconciliation-safe tests, without routing changes.
4. A-share intraday capability inventory for 15m/1H and Currentness evidence boundaries.
5. Continue Currentness / Continuity / RecoveryCandidate Harvest against frozen LiveFeed contracts.
6. Validate stacked Data R2 independently after its base is stable.
7. Run drift detection before every next-step / implementation / promotion recommendation.

## Handoff truth
Harvest produces evidence and bounded adaptations. Promotion authority remains outside this lane.
