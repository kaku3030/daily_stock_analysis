# Live Feed Reliability V0.1 — Frozen Contract

STATUS: **DESIGN FROZEN**
IMPLEMENTATION: **PENDING**
VALIDATION: **PENDING**

This document is a **persistence** of a contract already frozen in a
prior design session, not a new design. It is authoritative. Nothing in
this document may be silently reinterpreted, weakened, renumbered, or
extended by implementation convenience.

This document distinguishes two kinds of content, and they must never be
mixed without an explicit label:

- **FROZEN CONTRACT** (Sections 1–20, 22) — provider-neutral. Applies to
  any market-data provider this system ever integrates, not just Futu.
- **FUTU PROVIDER-SPECIFIC EMPIRICAL FACTS** (Section 21 only) —
  implementation evidence for one specific provider, not architecture.
  Where it constrains implementation, it is labeled as a constraint, not
  folded into the provider-neutral invariants above it.

The companion readiness-pack documents
(`docs/LIVE_FEED_FUTU_IMPLEMENTATION_SPEC_V0_1.md`,
`docs/LIVE_FEED_BLOCKING_EXECUTION_MODEL_V0_1.md`,
`docs/LIVE_FEED_ADVERSARIAL_TEST_MAP_V0_1.md`,
`docs/LIVE_FEED_IMPLEMENTATION_SEQUENCE_V0_1.md`,
`docs/LIVE_FEED_REPO_INTEGRATION_RISKS_V0_1.md`) should treat this
document as the canonical source rather than re-deriving the principles
or the 50 cases independently.

---

## SECTION 1 — GOVERNING PRINCIPLES

1. Connected is not Live.
2. Evidence may upgrade state; absence of evidence must not be converted
   into evidence of success.
3. Provider ACK != Live.
4. `subscribe()` success/no exception != subscription confirmation.
5. SEED and RECOVERY_BACKFILL data cannot establish live readiness.
6. Fresh `received_at` != fresh source progress.
7. DELAYED or UNKNOWN DeliveryMode != LIVE.
8. Recovery is two-phase: `CURRENTNESS_PROVEN` → `CONTINUITY_PROVEN` → `LIVE`.
9. Control-plane subscription truth != data-plane liveness truth.
10. Connection generation != subscription incarnation != desired registry
    revision != SemanticStreamKey.
11. SemanticStreamKey equality is necessary, not sufficient, evidence of
    semantic equivalence.
12. Cached data does not durably own LIVE truth; live trust is
    interpreted against current runtime/controller trust.
13. Provider/SDK transport reconnect cannot self-promote the system to LIVE.
14. Authoritative lifecycle, desired-registry, subscription-health, and
    live-health state transitions occur through one serialized writer.
15. Potentially blocking provider operations must not execute on the
    authoritative controller writer.
16. Unknown facts remain UNKNOWN / UNVERIFIED / UNPROVABLE rather than
    being guessed.

## SECTION 2 — PUBLIC STATE MACHINE

States: `DISCONNECTED`, `CONNECTING`, `CONNECTED`, `SUBSCRIBING`, `LIVE`,
`DEGRADED`, `RECONNECTING`, `FAILED`.

**`CONNECTED → LIVE` is forbidden.**
**`RECONNECTING → LIVE` is forbidden.**

Normal recovery path:

```
RECONNECTING
  → CONNECTING
  → CONNECTED
  → SUBSCRIBING
  → CURRENTNESS_PROVEN
  → CONTINUITY_PROVEN
  → LIVE
```

`LifecycleState != FailureClass`.

`FailureClass`: `TRANSIENT`, `REQUIRES_INTERVENTION`, `UNKNOWN`.
FailureClass controls recovery policy, not lifecycle-state identity.

## SECTION 3 — PROVIDER / CONTROLLER AUTHORITY

**Provider adapter owns provider mechanics:**
SDK context mechanics; callback normalization; provider timestamps;
provider raw errors/events; subscribe/unsubscribe API invocation;
provider semantic normalization.

**Controller owns:**
desired registry; `desired_registry_revision`; connection generation
identity; stream subscription intent epoch; liveness; health; recovery
qualification; live trust; reconciliation policy.

If a provider SDK has unavoidable autonomous transport reconnect
behavior:

> SDK transport reconnect != controller recovery != LIVE.

Provider reconnect may only generate evidence.

## SECTION 4 — IDENTITY MODEL

- `runtime_instance_id` — process/runtime identity, random UUID,
  non-durable business identity.
- `provider_id`
- `connection_generation` — per provider-controller runtime, per
  connection attempt/recovery incarnation as defined by provider
  integration; never persisted as durable truth.
- `desired_registry_revision` — monotonic desired-set history.
- `stream_subscription_epoch` — controller intent incarnation; provider
  binding may be `VERIFIED` or `UNVERIFIED`.
- `SemanticStreamKey` — exact semantic identity of the data stream.

Connection identity and subscription identity must not be conflated.

## SECTION 5 — CONTROL-PLANE VS DATA-PLANE

Control-plane facts: `DESIRED`, `REQUESTED`, `ACKED`, `REJECTED`,
`INCARNATION_BOUND`, `INCARNATION_UNVERIFIED`.

Data-plane facts: `CURRENTNESS_PROVEN`, `CONTINUITY_PROVEN`, `LIVE`.

**Freeze: LIVE is a data-plane fact only.** Control-plane uncertainty
must be exposed in parallel. A consumer may not infer control-plane
health from data-plane LIVE.

## SECTION 6 — SEMANTIC STREAM KEY

Must contain all known semantics-affecting fields: `provider`,
`market`/venue, `symbol`, `stream_type`, `timeframe`, session mode when
relevant, adjustment mode when relevant, feed/access path/package when
semantically relevant.

Equality is necessary but not sufficient. Hidden provider semantic drift
outside known key fields is a Provider Semantic Contract trust boundary.

## SECTION 7 — DELIVERY MODE / ENTITLEMENT

`DeliveryMode`: `REALTIME`, `DELAYED`, `UNKNOWN`.

**Freeze: `DELAYED` → never LIVE. `UNKNOWN` → never LIVE.**

Fresh timestamps, successful subscription, or continuous pushes do not
prove REALTIME. REALTIME evidence may only be inherited within its proven
entitlement scope. Entitlement evidence requires scope/freshness
semantics. Authoritative downgrade immediately revokes qualification.
Upgrade requires new entitlement evidence plus normal live qualification.

## SECTION 8 — CLOCK TRUST

`ClockTrust`: `TRUSTED`, `SKEWED`, `UNKNOWN`.

Absolute source freshness uses canonical timezone-aware UTC. Elapsed
timeout logic uses monotonic time. `ClockTrust.TRUSTED` requires recent
bounded external synchronization evidence. No external bounded evidence
→ `ClockTrust.UNKNOWN`. `ClockTrust != TRUSTED` → absolute freshness
INDETERMINATE, full LIVE unavailable. Naive/ambiguous timestamps may not
be silently localized.

## SECTION 9 — PROGRESS IDENTITY

ProgressIdentity is provider-semantic. Possible forms: provider
sequence/cursor; provider event/bar identity; semantic interval identity;
normalized provider source time only when provider semantics support
ordered progress. Do not assume `source_timestamp == progress`.

Per stream preserve: prior progress watermark; CurrentnessBoundary
semantics; provider comparator.

Connection-local sequence values cannot be compared across generations
unless provider contract proves comparability. If safe cross-generation
progress cannot be established: `UNPROVABLE` is an explicit per-stream
qualification fact.

## SECTION 10 — CURRENTNESS

CurrentnessBoundary means: the provider-semantic minimum progress
expected to represent current market state at evaluation time.

It is **not**: `source_timestamp > reconnect_wall_clock`, and not merely
`source_timestamp > pre_loss_timestamp`.

Currentness evaluation depends on: provider progress semantics;
session/trading expectation; trusted clock semantics; provider
boundary/publication tolerance.

`CURRENTNESS_PROVEN` is Phase 1 only and does not mean LIVE.

## SECTION 11 — CONTINUITY

`CONTINUITY_PROVEN` requires a subsequent independent authoritative
progress opportunity. The second evidence must: have strictly later
progress identity than Phase 1; independently satisfy CurrentnessBoundary;
be evaluated using cadence anchored to Phase-1 progress position.

- Duplicate: no continuity.
- Same-progress correction: no continuity.
- Ordinary transport heartbeat: no continuity.
- A provider-specific heartbeat may substitute only if the provider
  contract proves it attests to the exact stream/subscription progress
  dependency.

`CURRENTNESS_PROVEN` + `CONTINUITY_PROVEN`: stream data-plane LIVE may be
established.

## SECTION 12 — RECOVERY CANDIDATE

`RecoveryCandidate` must bind at minimum: `runtime_instance_id`,
`provider_id`, `generation_id`, `SemanticStreamKey`, `entitlement_epoch`,
clock-trust evidence/epoch, `phase1_progress_key`, currentness evidence,
`created_at`.

Where provider subscription binding is available: `stream_subscription_epoch`,
`binding_strength`.

`BindingStrength`: `VERIFIED`, `UNVERIFIED`.

Before Phase 2 all prerequisites must be revalidated.

Candidate invalidation includes: generation changes; SemanticStreamKey
changes; entitlement downgrade/epoch change; ClockTrust loss; desired
stream removal; binding facts invalidation; `CLOSED_SESSION`.

`EXPECTED_SILENCE`: retain candidate and suspend cadence expectation.
`CLOSED_SESSION`: invalidate candidate; next `ACTIVE_SESSION` must
re-prove Currentness.

## SECTION 13 — SUBSCRIPTION ATTRIBUTION

Provider ACK is administrative evidence only. ACK is neither necessary
nor sufficient for LIVE.

If provider supplies a subscription token/barrier: binding may become
`VERIFIED`. If provider does not: do not fabricate provider-attested
incarnation identity.

Event attribution follows the same proof standard as subscription
binding. Unattributable event must not be assigned to a changed
SemanticStreamKey using subscribe-call order or payload heuristics.

For same SemanticStreamKey: control-plane incarnation may remain
`UNVERIFIED` while genuine future current+continuous data may establish
data-plane LIVE.

For changed SemanticStreamKey: old stream evidence cannot establish the
new requested semantics.

## SECTION 14 — SESSION / TRADING EXPECTATION

`session_phase`: `ACTIVE_SESSION`, `EXPECTED_SILENCE`, `CLOSED_SESSION`.

`trading_expectation`: `PROGRESS_EXPECTED`, `SILENCE_EXPECTED`, `UNKNOWN`.

`UNKNOWN`: silence alone cannot prove failure. Progress timeout applies
only where progress is expected. LiveFeed does not own exchange-calendar
or symbol-tradability truth.

## SECTION 15 — CACHE TRUST

Disconnect/recovery failure does not require deleting cached context. It
revokes live trust. Cached records must not durably contain authoritative
LIVE truth. Use controller/stream trust epochs or equivalent read-time
trust binding. A snapshot is point-in-time evidence, not standing
authorization. Already-issued snapshot objects cannot be retroactively
revoked. Downstream actionable eligibility must revalidate current
health/trust.

## SECTION 16 — CONCURRENCY

Provider callbacks: normalize + enqueue only. No AI/heavy technical work
inside callback. All authoritative controller state transitions: single
serialized writer. Published state: immutable/read-only snapshot. Queue
loss/backpressure cannot be silently ignored. Lifecycle/control events
must not be silently dropped. Market-data ingress loss must produce
explicit continuity/data-loss findings.

## SECTION 17 — SHUTDOWN / RESTART

Normal shutdown: must not trigger reconnect. `stop_requested` or
equivalent internal control prevents new recovery actions.

Process restart: all previous live trust = ZERO. Previous
generations/cache records cannot automatically regain LIVE.

## SECTION 18 — NON-GOALS

Live Feed Reliability V0.1 does NOT own: DecisionEligibility; AI gating;
technical indicator semantics; portfolio temporal synchronization;
cross-timeframe snapshot integrity; adjustment policy; order
execution/routing; historical-backfill correctness; provider ranking;
multi-provider blending.

## SECTION 19 — PERMANENT ADVERSARIAL SET (Cases 1–50)

The 50 cases are persisted verbatim, unrenumbered, unmerged, with no
case 51+ and no rewritten invariants, exactly as supplied. Case 46
retains 46A/46B under one case ID.

**CASE 1** — Socket/transport connected but subscription failed.
Expected invariant: CONNECTED transport alone must never produce LIVE.

**CASE 2** — subscribe() returns successfully / no exception.
Expected invariant: Call success is administrative evidence only; it
must not confirm subscription or LIVE.

**CASE 3** — Provider ACK received but no data follows.
Expected invariant: ACK alone must not produce LIVE.

**CASE 4** — Transport reconnect succeeds but desired subscriptions are
not replayed/re-established.
Expected invariant: Reconnect != recovery; no LIVE.

**CASE 5** — Resubscription succeeds administratively but no qualified
fresh live progress follows.
Expected invariant: No LIVE until data-plane recovery is proven.

**CASE 6** — Old-generation callback arrives after a newer connection
generation exists.
Expected invariant: Old-generation evidence cannot advance liveness,
subscription confirmation, or restore LIVE.

**CASE 7** — QUOTE progresses while required 1M_BAR stream stalls.
Expected invariant: QUOTE must not keep 1M_BAR alive; liveness is per
SemanticStreamKey / stream dependency.

**CASE 8** — received_at remains fresh while provider source progress is
stuck.
Expected invariant: Receipt activity != source progress; stream cannot
remain LIVE from receipt timestamps alone.

**CASE 9** — Historical SEED data fills the realtime cache.
Expected invariant: SEED may provide context but cannot establish live
subscription, progress, recovery, or LIVE.

**CASE 10** — Recovery backfill/catch-up arrives through the normal push
path.
Expected invariant: Backfill evidence must not masquerade as genuine
live recovery.

**CASE 11** — Transport disconnects but cached market data remains
present.
Expected invariant: Cache may remain for context, but live trust must be
revoked.

**CASE 12** — Only some symbols/streams recover.
Expected invariant: Health must expose per-stream/per-symbol truth;
partial recovery must not create false global LIVE.

**CASE 13** — Realtime permission/entitlement is revoked.
Expected invariant: The affected capability loses LIVE qualification
immediately; classification must reflect provider evidence.

**CASE 14** — A transient network failure reaches retry attempt #50.
Expected invariant: Retry count must not transform TRANSIENT into
REQUIRES_INTERVENTION.

**CASE 15** — Provider error cannot be classified.
Expected invariant: Remain UNKNOWN; never silently guess TRANSIENT or
intervention-required from strings/retry count.

**CASE 16** — Local wall clock slowly drifts.
Expected invariant: Untrusted absolute time must degrade
ClockTrust/freshness qualification rather than silently producing false
currentness.

**CASE 17** — NTP wall-clock jump occurs.
Expected invariant: Monotonic timeout logic must remain stable; absolute
freshness trust must be reassessed.

**CASE 18** — Lunch break / expected closed-session silence.
Expected invariant: Expected silence must not be misclassified as feed
failure.

**CASE 19** — Legitimate zero-trade silence.
Expected invariant: Absence of source progress must be interpreted using
provider/session/trading-expectation semantics, not automatically as
outage.

**CASE 20** — Normal shutdown triggers provider disconnect callback /
reconnect timer.
Expected invariant: stop_requested must prevent reconnect; shutdown must
terminate cleanly.

**CASE 21** — Reconnect push contains catch-up data that looks newer
than the old watermark but does not satisfy currentness semantics.
Expected invariant: Progress beyond old watermark alone is insufficient
for recovery.

**CASE 22** — Reconnect repeats the last pre-loss event.
Expected invariant: Duplicate/repeated prior progress cannot advance
recovery.

**CASE 23** — Same progress identity arrives with changed payload.
Expected invariant: Correction may count as transport activity but not
source progress / continuity.

**CASE 24** — DELAYED or UNKNOWN entitlement produces fresh-looking
timestamps.
Expected invariant: Fresh timestamps do not prove realtime entitlement;
never LIVE.

**CASE 25** — One stream's subscription is silently revoked while other
streams continue.
Expected invariant: Only affected stream qualification degrades; healthy
streams cannot mask it.

**CASE 26** — One symbol receives permission rejection while others
remain healthy.
Expected invariant: Per-symbol rejection must not incorrectly force
entire provider feed into global FAILED.

**CASE 27** — Machine suspend/resume causes wall/monotonic discontinuity.
Expected invariant: ClockTrust must degrade appropriately; system must
not falsely declare source outage/currentness.

**CASE 28** — Process restarts while old persisted cache/generation
metadata exists.
Expected invariant: Runtime restart resets all live trust; old
generation identity can never automatically regain LIVE.

**CASE 29** — Desired subscription registry changes during
reconnect/recovery.
Expected invariant: Current desired truth wins; stale replay/ACK/result
from prior revision cannot resurrect removed subscriptions or omit newly
desired ones.

**CASE 30** — Recovery happens during CLOSED_SESSION and no fresh
progress can occur.
Expected invariant: System waits safely; absence of progress does not
mean FAILED, and prior currentness cannot be fabricated.

**CASE 31** — Provider sends a future timestamp because provider/local
clock is wrong.
Expected invariant: Freshness becomes indeterminate / ClockTrust
degrades; future timestamp cannot establish LIVE.

**CASE 32** — Remove a stream and immediately re-add the same semantic
stream.
Expected invariant: Old buffered subscription evidence must not
automatically prove the new control-plane incarnation.

**CASE 33** — A genuine current 1m bar uses bar-start/source semantics
earlier than reconnect wall-clock.
Expected invariant: Raw source_timestamp > reconnect_time must never be
required as the recovery rule.

**CASE 34** — Provider sequence is connection-local, resets after
reconnect, and short-disconnect catch-up arrives with fresh new sequence
values.
Expected invariant: Connection-local sequence values must never be
numerically compared across generations as if globally ordered.

**CASE 35** — A replay/catch-up burst ends with one event that satisfies
all Phase-1 recovery gates, then the stream goes silent.
Expected invariant: One current-looking progress event cannot establish
full recovery; CONTINUITY must be independently proven.

**CASE 36** — Runtime entitlement changes REALTIME -> DELAYED.
Expected invariant: Live qualification must be revoked immediately;
entitlement downgrade is asymmetric and cannot wait for source
staleness.

**CASE 37** — No provider subscription token; remove -> re-add; buffered
old-incarnation evidence arrives.
Expected invariant: Unproven control-plane incarnation binding cannot be
treated as provider-attested identity.

**CASE 38** — Catch-up contains many bars newer than pre-loss watermark
but still below CurrentnessBoundary.
Expected invariant: They may advance historical progress but cannot
prove CURRENTNESS.

**CASE 39** — First event proves CURRENTNESS, then only a transport
heartbeat continues while the authoritative bar stream stalls.
Expected invariant: Ordinary transport heartbeat cannot prove stream
CONTINUITY.

**CASE 40** — Same market contains different per-symbol entitlement
states.
Expected invariant: Market-level REALTIME evidence must not leak to a
symbol/stream outside the proven entitlement scope.

**CASE 41** — unsubscribe returns success but provider does not
guarantee callback drain.
Expected invariant: unsubscribe ACK/return must not be treated as a
clean subscription-incarnation barrier.

**CASE 42** — A correction with the same progress identity and changed
payload is presented as Phase-2 evidence.
Expected invariant: Correction cannot satisfy CONTINUITY_PROVEN.

**CASE 43** — Entitlement evidence expires.
Expected invariant: Expired entitlement evidence becomes UNKNOWN;
fresh-looking data still cannot establish LIVE.

**CASE 44** — Session closes between Phase 1 CURRENTNESS and Phase 2
CONTINUITY.
Expected invariant: Lifecycle does not fail, but the RecoveryCandidate is
invalidated; next active session must re-prove CURRENTNESS.

**CASE 45** — Desired subscription is removed between Phase 1 and Phase
2.
Expected invariant: Pending RecoveryCandidate is invalidated and can
never promote the removed stream to LIVE.

**CASE 46** — No-token/no-barrier provider and old server-side
subscription survives reconnect/remove-readd.

This case has two required sub-scenarios and remains one authoritative
case ID:

- **46A**: Same SemanticStreamKey + only buffered old events.
  Expected: May possibly satisfy Phase 1 currentness, but cannot satisfy
  genuine future CONTINUITY; therefore no data-plane LIVE.
- **46B**: Same SemanticStreamKey + surviving old subscription continues
  producing genuine future authoritative progress.
  Expected: CURRENTNESS + CONTINUITY may validly establish data-plane
  LIVE even while control-plane incarnation remains
  INCARNATION_UNVERIFIED.

Important: LIVE here is a data-plane fact only. Control-plane uncertainty
must remain visible in parallel.

**CASE 47** — OS/external clock synchronization evidence becomes
stale/expired.
Expected invariant: ClockTrust becomes UNKNOWN and absolute freshness
becomes INDETERMINATE.

**CASE 48** — Remove -> re-add with a changed SemanticStreamKey, no
token/barrier, while old stream continues producing genuine future data.
Expected invariant: Old-key data must never prove the new requested
stream semantics LIVE; new semantics remain UNPROVABLE until
attribution/binding is established.

**CASE 49** — No-token changed-key scenario where callback data is
indistinguishable and cannot be safely attributed to old vs new
subscription.
Expected invariant: Unattributable event proves neither new
SemanticStreamKey nor its LIVE qualification. Never assign by
subscribe-call ordering or payload heuristics.

**CASE 50** — EXPECTED_SILENCE (for example lunch break) occurs between
Phase 1 and Phase 2.
Expected invariant: RecoveryCandidate remains retained, cadence
expectation is suspended, and continuity evaluation resumes afterward.
This differs from CLOSED_SESSION, which invalidates the RecoveryCandidate.

## SECTION 20 — PROVIDER SEMANTIC CONTRACT DEPENDENCY

Provider-neutral design (Sections 1–19, 22) is frozen.

Provider integrations must empirically qualify facts including: timestamp
semantics; progress identity; currentness/boundary semantics;
DeliveryMode/entitlement; subscribe/ACK behavior; unsubscribe/barrier
behavior; duplicate/correction behavior; ordering; transport disconnect;
reconnect; catch-up/replay; subscription persistence; callback threading;
blocking SDK behavior.

Unknown provider semantics must select conservative contract paths.

## SECTION 21 — CURRENT FUTU IMPLEMENTATION CONSTRAINTS

**This section is implementation evidence, NOT provider-neutral frozen
architecture.** It exists to record what is currently known about one
specific provider (Futu/Moomoo, SDK 10.08.6808) and how that evidence
constrains implementation choices — it does not modify Sections 1–20/22.

Authoritative evidence source:
`tools/provider_semantics/futu/FUTU_SEMANTIC_CONTRACT_V0_1.md`.

**Recorded constraints:**

- Futu SDK autonomous transport reconnect exists (hardcoded
  `_auto_reconnect=True`, no public disable control, ~6s interval, no
  backoff/cap).
- SDK reconnect cannot self-promote LIVE (Section 3/13 apply — this is
  the provider-specific instance of the general rule, not an exception
  to it).
- Potentially blocking synchronous Futu calls cannot run on the
  controller writer (Section 15 applies; empirically confirmed blocking
  risk: `OpenQuoteContext.__init__` against an unreachable endpoint,
  `query_subscription()` during outage).
- `query_subscription` is control-plane/shared-registry evidence, not
  push-flow proof (Section 5/9 apply).
- unsubscribe return is not a callback-drain barrier (Section 13/CASE 41
  apply; directly empirically confirmed).
- Callback delivery is multi-threaded (Section 16 concurrency rules
  apply).
- QUOTE `data_time` alone is not ProgressIdentity (Section 9 applies;
  second-resolution, many-to-one with real changes, no sequence/cursor
  observed).
- K_1M `time_key` may be a progress candidate but is not bar-completeness
  evidence (Section 9/10 apply; no completeness flag exists in the
  payload).
- DeliveryMode remains UNKNOWN without authoritative entitlement evidence
  (Section 7 applies; no field anywhere confirms REALTIME/DELAYED for
  this provider).

**Explicitly unresolved (provider-specific, not architecture gaps):**

- **F15** — cross-reconnect ProgressIdentity behavior.
- **F17** — successful-reconnect catch-up behavior (never observed).
- **F18** — replay/backfill distinguishability (untestable without F17
  evidence).
- **Auto-resubscribe behavioral confirmation** — source-predicted, never
  behaviorally observed (an attempt deadlocked the harness before
  observation completed).
- **F04** — authoritative DeliveryMode/entitlement evidence.

## SECTION 22 — GOVERNANCE

DESIGN changes require explicit new design review.

Implementation may not silently weaken frozen invariants because provider
SDK behavior is inconvenient.

Provider-specific limitations must be represented as `UNKNOWN`,
`UNVERIFIED`, `UNPROVABLE`, or explicit provider constraints (Section 21
pattern). Do not compensate with optimistic assumptions.
