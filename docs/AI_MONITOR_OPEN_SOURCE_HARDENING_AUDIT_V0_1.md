# AI Monitor — Open-Source Hardening Audit V0.1

Status: ACTIVE AUDIT / IMPLEMENTATION TRACK

This document starts the Build-vs-Borrow hardening track for the AI portfolio monitor / realtime_monitor. It does not promote any external implementation to production merely because it is mature or popular.

## Governing rule

Every external component follows:

`DISCOVER -> AUDIT -> EXTRACT -> ADAPT -> HARDEN -> ADVERSARIAL TEST -> REPLAY/OOS -> SHADOW LIVE -> PROMOTE`

External components are classified as one of:

- `DIRECT_ADOPT`
- `ADAPT`
- `BORROW_TEST`
- `RESEARCH_ONLY`
- `REPLACE_WITH_OURS`
- `REJECT`

Core Stock Razor / AI Monitor semantics remain ours: Portfolio State, Ownership/Exposure/Add Right, Leadership/RS, Market/Risk State, Trigger semantics, Risk Budget, and Evidence -> Gate -> Narrative.

## Current repository findings

### P0 — Live Feed Reliability foundation exists and is usable

PR #28 added a provider-neutral streaming capability boundary, immutable provider event/identity models, single-writer LiveFeedController, desired subscription registry, nonblocking provider command boundary, immutable snapshots, and LiveFeedHealth facts.

Current deliberate gaps in the merged controller remain:

- DeliveryMode / entitlement qualification (F04 remains provider-semantic P0)
- CurrentnessBoundary
- Continuity
- RecoveryCandidate
- cache live-trust revocation
- final health aggregation policy
- LIVE promotion
- final provider-worker isolation policy

These gaps are not cosmetic: the frozen contract explicitly forbids `CONNECTED -> LIVE`, `RECONNECTING -> LIVE`, and forbids DELAYED/UNKNOWN delivery modes from reaching LIVE.

### P0 — Legacy/runtime alert path can evaluate numeric quote values without an explicit freshness hard gate

`src/services/alert_service.py` and `src/agent/events.py` obtain a realtime quote, validate that a numeric price/change exists, then evaluate threshold conditions. They expose/extract a data timestamp, but the current threshold path does not first prove that the quote is fresh/current enough for an actionable realtime alert.

Risk: a stale-but-numeric quote can satisfy a price/percent threshold unless upstream provider behavior happens to prevent it. Data Health must be a hard gate, not an incidental provider assumption.

Required repair:

1. one shared quote-health/currentness contract, not duplicate ad-hoc checks;
2. stale / missing / semantically-indeterminate realtime timestamps fail closed for actionable realtime alerts;
3. explicit result reason/status such as `STALE_QUOTE_BLOCKED` / `DATA_UNHEALTHY`, never silent non-trigger;
4. retain provider/source/timestamp provenance;
5. permanent regression fixtures.

## Open-source extraction decisions

### VeighNa / vn.py — `ADAPT`

Borrow/port the proven event-queue and bar-aggregation shape. Do not import its trading execution semantics. Our bar layer must remain session-aware for A-share lunch breaks and U.S. premarket/regular/after-hours boundaries.

### PKScreener — `BORROW_TEST` + selective `ADAPT`

Borrow the data-freshness regression scenarios:

- fresh realtime data beats stale cache;
- stale data is rejected;
- timestamps must be current for the intended decision horizon;
- fallback is explicit and only used when realtime is unavailable;
- database failure must not poison the fresh realtime path.

VCP/pattern code is a Radar concern and should be handled separately.

### TradingAgents — `ADAPT`

Borrow structured-output, checkpoint/resume, persistent decision-log, and bull/bear counter-thesis orchestration ideas. Do not adopt autonomous BUY/SELL decision semantics.

### Freqtrade — `RESEARCH_ONLY` (GPL code boundary)

Borrow the operational idea of Protection/Cooldown state, not source code. Cooldown must allow severity escalation or material state change to break suppression.

### NautilusTrader / LEAN — `RESEARCH_ONLY`

Borrow live/replay parity, reconciliation, event-driven boundaries, cache/portfolio/message-bus separation, and restart-recovery design. Do not migrate the project onto either engine in P0.

## P0 implementation sequence

1. **DeliveryMode F04 closure** — prove/normalize provider delivery mode; UNKNOWN/DELAYED remain fail-closed.
2. **Currentness / stale-data hard gate** — unify Live Feed and actionable alert currentness semantics at the correct layer without creating a Health God Object.
3. **Session-aware progress expectation** — active session vs expected silence vs closed session; no false outage during A-share lunch or legitimate silence.
4. **Continuity + RecoveryCandidate** — two-phase recovery; duplicate/correction/backfill cannot restore LIVE.
5. **Restart Reconciliation** — restart resets live trust to zero; desired subscriptions/portfolio/alert protection state are reconciled explicitly.
6. **Protection State** — cooldown/dedup becomes stateful suppression with escalation overrides.
7. **AI checkpoint + Decision Journal** — structured review, resumable model chain, persistent evidence/state-change log.
8. **Shadow Live** — same evidence/trigger/state-machine code path as Replay; no production promotion until false-positive/false-negative and failure-injection review passes.

## Permanent regression additions

Minimum new regression set:

- `fresh_quote_allows_evaluation`
- `stale_numeric_quote_cannot_trigger`
- `missing_quote_time_cannot_be_promoted_to_fresh`
- `delayed_delivery_never_live`
- `unknown_delivery_never_live`
- `fresh_received_at_with_stuck_source_progress_not_live`
- `stale_cache_cannot_masquerade_as_realtime`
- `db_failure_does_not_poison_live_feed`
- `a_share_lunch_expected_silence_not_outage`
- `us_after_hours_semantics_not_mixed_with_regular_session`
- `restart_resets_live_trust`
- `duplicate_post_reconnect_event_does_not_prove_continuity`
- `same_progress_correction_does_not_prove_continuity`
- `cooldown_suppresses_duplicate_but_not_severity_escalation`

## Scope boundary

This track does not add automatic order placement or execution permission. AI Monitor remains decision support and alerting only.

## Source-code availability note

The standalone/local `realtime_monitor` body is not currently present in this GitHub repository and was not found in the connected file library during this audit. The repository already contains important shared/live-feed/alert foundations that can be hardened immediately; full monitor-state-machine audit requires the local realtime_monitor source to be pushed or uploaded without pre-cleaning.
