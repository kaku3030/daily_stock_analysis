# Live Feed — Permanent Adversarial Test Mapping (Draft R1)

Status: **PLANNING ONLY.** No `LiveFeedController` or Futu streaming
adapter exists in this repository yet, so almost every case below is
`SPEC_ONLY` or `NOT_YET_TESTABLE` — there is nothing to run these tests
against. This document maps future test responsibility, not present
coverage.

## Source of the 50 cases

The frozen Live Feed Reliability V0.1 contract and its permanent 50-case
adversarial set are now persisted verbatim at
`docs/LIVE_FEED_RELIABILITY_CONTRACT_V0_1.md` §19 (superseding the
original `MISSING_REPO_CONTRACT_ARTIFACT` gap noted below). Case IDs,
wording, and expected invariants below remain reproduced
verbatim/unmodified from that source: not renumbered, not merged, not
reinterpreted.

**Wave 2 status: CLOSED** (`tools/provider_semantics/futu/FUTU_SEMANTIC_CONTRACT_V0_1.md`
§4). This changes *why* several cases below are not yet software-tested
— from "the underlying provider fact is unknown" to "the provider fact is
now known, but no controller exists to test the invariant against it,
and/or this case's specific premise was not the scenario naturally
observed." Provider qualification is not software testing — see §C1
below for the precise, case-by-case distinction; no case in this document
is marked `SOFTWARE_TESTED` as a result of this update, because no
controller exists.

## Column definitions

- `test_layer`: UNIT / COMPONENT / INTEGRATION / FAULT_INJECTION /
  LIVE_PROVIDER / MANUAL_PROVIDER_QUALIFICATION — the primary layer
  recommended for this case, not the only layer it could ever run at.
- `requires_real_Futu`, `requires_active_market`, `requires_fault_proxy`,
  `requires_clock_injection`, `requires_provider_semantic_fixture`:
  requirements for testing at the recommended layer above.
- `implementation_module`: the repo module (existing) or future module
  (not yet built) most likely responsible.
- `current_status`: `SPEC_ONLY` (no implementation or test exists),
  `HARNESS_COVERED` (the semantics-research harness already tests the
  underlying mechanic, not the production behavior), `EMPIRICALLY_OBSERVED`
  (the underlying provider-level fact has direct raw evidence, even
  though no controller-level test exists yet), `NOT_YET_TESTABLE`
  (blocked by an unresolved Wave 2 P0 provider fact, independent of
  whether any code exists).

**Two distinct questions, not one.** `test_layer` answers "what kind of
software test exercises this case's logic" (UNIT/COMPONENT/INTEGRATION
are all satisfiable today with fakes, independent of Futu). It does
**not** answer "is this case's oracle trustworthy against real Futu
behavior" — that is a separate axis, provider semantic qualification,
answered by `requires_real_Futu` + `current_status=NOT_YET_TESTABLE`
together. A case can have a perfectly buildable `COMPONENT` test today
(the controller logic can be exercised with fake command results) while
still being provider-semantically unqualified (nobody has ever confirmed
real Futu produces the inputs that test assumes). Cases 4, 5, 10, 12, 21,
22, 25, 35, 38, 46 are the ones where `test_layer=FAULT_INJECTION` *and*
`current_status=NOT_YET_TESTABLE` coincide — for those, even a
software-correct implementation cannot be called validated until F15/
F17/F18 close, because there is no confirmed real-provider scenario to
qualify the test's own fixture against. Every other case's `COMPONENT`/
`UNIT`/`INTEGRATION` designation below can be built and run in software
now, using fakes, with no Futu dependency — but "buildable now" is not
"provider-semantically qualified," and this table does not claim the
latter for any case beyond CASE 41 (see §C1).

## Case table

| ID | Short name | Contract area | test_layer | real_Futu | active_market | fault_proxy | clock_inj | semantic_fixture | Expected invariant | implementation_module | current_status |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | Connected-not-subscribed | Connection/generation | COMPONENT | N | N | N | N | Y | CONNECTED transport alone must never produce LIVE | LiveFeedController (future) | SPEC_ONLY |
| 2 | subscribe() admin success | Subscription truth | COMPONENT | N | N | N | N | Y | Call success is administrative evidence only; must not confirm subscription or LIVE | LiveFeedController / Futu adapter (future) | SPEC_ONLY |
| 3 | ACK, no data follows | Subscription truth | COMPONENT | N | N | N | N | Y | ACK alone must not produce LIVE | LiveFeedController (future) | SPEC_ONLY |
| 4 | Reconnect, no replay | Continuity/recovery | FAULT_INJECTION | Y | N | Y | N | Y | Reconnect != recovery; no LIVE | Futu adapter + LiveFeedController (future) | NOT_YET_TESTABLE — provider fact no longer blocking (F17 VERIFIED, TESTED SCOPE, Wave 2 Closure R2); but this case's exact premise (subscriptions *not* replayed) was not the observed scenario — SDK auto-resubscribe successfully re-established both streams in all 3 tested cycles. No controller exists to test the invariant itself. |
| 5 | Resubscribe admin only | Continuity/recovery | FAULT_INJECTION | Y | Y | Y | N | Y | No LIVE until data-plane recovery is proven | LiveFeedController (future) | NOT_YET_TESTABLE — provider fact no longer blocking (F17/AUTO_RESUBSCRIBE VERIFIED, TESTED SCOPE); but this case's premise (admin resubscribe succeeds with *no* data-plane recovery) was not the observed scenario — data-plane recovery occurred in 3/3 tested cycles. No controller exists to test the invariant itself. |
| 6 | Old-generation callback | Connection/generation | COMPONENT | N | N | N | N | Y | Old-generation evidence cannot advance liveness/subscription/LIVE | LiveFeedController §B1 staleness check (future) | SPEC_ONLY — provider evidence now confirms this case's underlying premise genuinely occurs: F15 (Wave 2 Closure R2) VERIFIED that one Python `OpenQuoteContext` object spans multiple distinct transport incarnations (4 proxy-level TCP connections + an incrementing SDK-internal `conn_id`), so "old-generation evidence arriving after a newer generation exists" is a real, confirmed mechanism to design against, not a hypothetical. Still no controller to test. |
| 7 | QUOTE up, 1M_BAR stalled | Progress/currentness | COMPONENT | N | N | N | N | Y | QUOTE must not keep 1M_BAR alive; per-SemanticStreamKey liveness | LiveFeedController (future) | SPEC_ONLY |
| 8 | Fresh receipt, stuck source | Progress/currentness | COMPONENT | N | N | N | N | Y | Receipt activity != source progress | LiveFeedController (future) | SPEC_ONLY |
| 9 | SEED fills cache | Cache trust | UNIT | N | N | N | N | N | SEED cannot establish live subscription/progress/recovery/LIVE | `RealtimeMarketDataService.seed()` (existing, unchanged) + LiveFeedController (future) | SPEC_ONLY |
| 10 | Backfill via normal push path | Continuity/recovery | FAULT_INJECTION | Y | N | Y | N | Y | Backfill evidence must not masquerade as genuine live recovery | Futu adapter + LiveFeedController (future) | NOT_YET_TESTABLE — provider fact no longer blocking (F18 VERIFIED_NEGATIVE_OBSERVATION: `NO_AUTHORITATIVE_REPLAY_MARKER_OBSERVED` across 274 QUOTE + 253 K_1M payloads, Wave 2 Closure R2); but this case's premise (backfill actually arriving) was not the observed scenario — no backfill/replay occurred in any of the 3 tested cycles (`DIRECT_CURRENT_ONLY`, F17). No controller exists to test the invariant itself. |
| 11 | Disconnect, cache remains | Cache trust | COMPONENT | N | N | N | N | N | Cache may remain for context; live trust must be revoked | LiveFeedController (future) + `RealtimeMarketDataService` (existing cache, unchanged) | SPEC_ONLY |
| 12 | Partial symbol/stream recovery | Continuity/recovery | INTEGRATION | N | Y | N | N | Y | Health must expose per-stream/per-symbol truth | LiveFeedController (future) | SPEC_ONLY — not addressed by Wave 2 Closure R2: QUOTE and K_1M recovered together in all 3 tested cycles, so partial/single-stream recovery remains unreproduced. |
| 13 | Entitlement revoked | Entitlement/clock | COMPONENT | N | N | N | N | Y | Affected capability loses LIVE immediately | LiveFeedController + Futu adapter ENTITLEMENT event (future) | SPEC_ONLY |
| 14 | Retry #50 | Connection/generation | UNIT | N | N | N | N | N | Retry count must not transform TRANSIENT into REQUIRES_INTERVENTION | LiveFeedController error/retry classifier (future) | SPEC_ONLY |
| 15 | Unclassifiable error | Connection/generation | UNIT | N | N | N | N | Y | Remain UNKNOWN; never guess from strings/retry count | LiveFeedController error classifier (future) | SPEC_ONLY |
| 16 | Slow clock drift | Entitlement/clock | COMPONENT | N | N | N | Y | N | Untrusted absolute time must degrade ClockTrust/freshness | LiveFeedController (future) | SPEC_ONLY |
| 17 | NTP jump | Entitlement/clock | COMPONENT | N | N | N | Y | N | Monotonic timeout logic stable; absolute freshness trust reassessed | LiveFeedController (future) | SPEC_ONLY |
| 18 | Lunch break silence | Session/trading expectation | COMPONENT | N | Y | N | N | Y | Expected silence must not be misclassified as feed failure | LiveFeedController + `market_gate.py`-style session logic (harness precedent, not production) | SPEC_ONLY |
| 19 | Legit zero-trade silence | Session/trading expectation | COMPONENT | N | Y | N | N | Y | Absence of progress interpreted via session/trading semantics, not automatic outage | LiveFeedController (future) | SPEC_ONLY |
| 20 | Normal shutdown | Shutdown/restart | COMPONENT | N | N | N | N | N | `stop_requested` must prevent reconnect; clean termination | LiveFeedController shutdown path (future) | SPEC_ONLY |
| 21 | Reconnect push newer but not current | Continuity/recovery | FAULT_INJECTION | Y | Y | Y | N | Y | Progress beyond old watermark alone is insufficient for recovery | LiveFeedController CurrentnessBoundary (future) | NOT_YET_TESTABLE — F17/F18 provider facts are now CLOSED, but this case's specific premise (a stale-but-newer-looking push) did not occur; all 3 tested cycles resumed at genuinely current progress (`DIRECT_CURRENT_ONLY`). Producing this scenario would need a deliberately engineered/synthetic fixture, not naturally observed provider behavior. |
| 22 | Reconnect repeats last pre-loss event | Continuity/recovery | FAULT_INJECTION | Y | Y | Y | N | Y | Duplicate/repeated prior progress cannot advance recovery | LiveFeedController (future) | NOT_YET_TESTABLE — F17/F18 provider facts are now CLOSED, but no repeat-of-pre-loss-event was observed; post-recovery payload hashes were confirmed distinct from pre-fault payloads in all 3 cycles. Same synthetic-fixture caveat as case 21. |
| 23 | Same identity, changed payload | Progress/currentness | COMPONENT | N | N | N | N | Y | Correction may count as transport activity, not source progress/continuity | LiveFeedController comparator (future) | SPEC_ONLY |
| 24 | DELAYED/UNKNOWN, fresh timestamps | Entitlement/clock | COMPONENT | N | N | N | N | Y | Fresh timestamps do not prove realtime entitlement; never LIVE | LiveFeedController DeliveryMode gate (future, see spec §A4) | SPEC_ONLY |
| 25 | One stream silently revoked | Subscription truth | INTEGRATION | Y | Y | Y | N | Y | Only affected stream degrades; healthy streams cannot mask it | LiveFeedController (future) | NOT_YET_TESTABLE — not addressed by Wave 2 Closure R2 (both streams always recovered together); single-stream revocation remains unreproduced. |
| 26 | One symbol rejected | Subscription truth | COMPONENT | N | N | N | N | Y | Per-symbol rejection must not force entire provider feed to FAILED | LiveFeedController (future) | SPEC_ONLY |
| 27 | Suspend/resume discontinuity | Entitlement/clock | COMPONENT | N | N | N | Y | N | ClockTrust degrades appropriately; no false outage/currentness | LiveFeedController (future) | SPEC_ONLY |
| 28 | Process restart, old cache | Shutdown/restart | COMPONENT | N | N | N | N | N | Runtime restart resets all live trust; old generation never auto-regains LIVE | LiveFeedController startup path (future) | SPEC_ONLY |
| 29 | Registry changes mid-reconnect | Subscription truth | COMPONENT | N | N | N | N | Y | Current desired truth wins; stale replay/ACK cannot resurrect/omit | LiveFeedController §B1 staleness check (future) | SPEC_ONLY |
| 30 | Recovery during CLOSED_SESSION | Session/trading expectation | COMPONENT | N | N | N | N | Y | System waits safely; absence != FAILED; currentness not fabricated | LiveFeedController + `market_gate.py`-style logic | SPEC_ONLY |
| 31 | Future timestamp, bad clock | Entitlement/clock | UNIT | N | N | N | Y | Y | Freshness indeterminate/ClockTrust degrades; no LIVE from future ts | LiveFeedController (future) | SPEC_ONLY |
| 32 | Remove+re-add same stream | Subscription truth | COMPONENT | N | N | N | N | Y | Old buffered evidence must not auto-prove new control-plane incarnation | LiveFeedController (future) | SPEC_ONLY |
| 33 | Bar source-ts earlier than reconnect walltime | Progress/currentness | COMPONENT | N | N | N | N | Y | `source_timestamp > reconnect_time` must never be the recovery rule | LiveFeedController CurrentnessBoundary rule (future) | SPEC_ONLY |
| 34 | Connection-local sequence resets | Progress/currentness | COMPONENT | N | N | N | N | Y | Connection-local sequence values never compared across generations as globally ordered | LiveFeedController comparator (future) | SPEC_ONLY — reconfirmed by Wave 2 Closure R2: no provider sequence/cursor field appeared across any of the 3 reconnects (527 total raw callbacks), so this case remains theoretical for Futu. Positive counterpart now known: K_1M `time_key` (calendar-anchored, not connection-local) remained cross-reconnect comparable in all 3 cycles — see case notes on F15 in the implementation spec §A3. |
| 35 | Replay burst ends on Phase-1-satisfying event | Continuity/recovery | FAULT_INJECTION | Y | Y | Y | N | Y | One current-looking event cannot establish full recovery; CONTINUITY independently proven | LiveFeedController two-phase recovery (future) | NOT_YET_TESTABLE — F17/F18 provider facts are now CLOSED, but no replay burst was ever observed to end on anything (`DIRECT_CURRENT_ONLY`, no replay at all in 3/3 cycles); this case's premise needs a synthetic fixture, not a naturally-reproduced scenario. |
| 36 | Runtime entitlement REALTIME→DELAYED | Entitlement/clock | COMPONENT | N | N | N | N | Y | Live qualification revoked immediately; asymmetric downgrade | LiveFeedController (future) | SPEC_ONLY |
| 37 | No-token remove/re-add, buffered old evidence | Subscription truth | COMPONENT | N | N | N | N | Y | Unproven control-plane incarnation cannot be treated as provider-attested identity | LiveFeedController (future) | SPEC_ONLY |
| 38 | Catch-up above watermark, below CurrentnessBoundary | Continuity/recovery | FAULT_INJECTION | Y | Y | Y | N | Y | May advance historical progress but cannot prove CURRENTNESS | LiveFeedController (future) | NOT_YET_TESTABLE — F17/F18 provider facts are now CLOSED, but no catch-up data of any kind was observed (recovery went straight to current progress in 3/3 cycles); same synthetic-fixture caveat as cases 21/22/35. |
| 39 | Heartbeat-only after Phase-1 proof | Continuity/recovery | COMPONENT | N | N | N | N | Y | Ordinary transport heartbeat cannot prove stream CONTINUITY | LiveFeedController (future) | SPEC_ONLY |
| 40 | Per-symbol entitlement divergence | Entitlement/clock | COMPONENT | N | N | N | N | Y | Market-level REALTIME evidence must not leak beyond proven scope | LiveFeedController (future) | SPEC_ONLY — informed by (not proven by) the existing empirical finding that entitlement differs by *access path* for one symbol |
| 41 | unsubscribe no callback-drain barrier | Subscription truth | COMPONENT | N | N | N | N | Y | unsubscribe ACK must not be treated as a clean incarnation barrier | LiveFeedController + Futu adapter (future) | **EMPIRICALLY_OBSERVED at the provider-fact level** — real callbacks arrived after a successful unsubscribe return, `FUTU_SEMANTIC_CONTRACT_V0_1.md` §2 UNSUBSCRIBE. No controller-level test exists yet. |
| 42 | Correction as Phase-2 evidence | Continuity/recovery | COMPONENT | N | N | N | N | Y | Correction cannot satisfy CONTINUITY_PROVEN | LiveFeedController (future) | SPEC_ONLY |
| 43 | Entitlement evidence expires | Entitlement/clock | COMPONENT | N | N | N | N | Y | Expired entitlement becomes UNKNOWN; fresh data still can't establish LIVE | LiveFeedController (future) | SPEC_ONLY |
| 44 | Session closes between Phase1/Phase2 | Session/trading expectation | COMPONENT | N | N | N | N | Y | RecoveryCandidate invalidated; next session re-proves CURRENTNESS | LiveFeedController + `market_gate.py`-style logic | SPEC_ONLY |
| 45 | Desired subscription removed between phases | Subscription truth | COMPONENT | N | N | N | N | Y | Pending RecoveryCandidate invalidated; removed stream never promoted | LiveFeedController (future) | SPEC_ONLY |
| 46 | No-token survival across reconnect (46A/46B) | Continuity/recovery | FAULT_INJECTION | Y | Y | Y | N | Y | 46A: buffered-only cannot prove CONTINUITY. 46B: genuine surviving future progress may validly prove data-plane LIVE even with `INCARNATION_UNVERIFIED` control-plane state | LiveFeedController + Futu adapter (future) | NOT_YET_TESTABLE — F15 (transport-vs-context identity) and F17 are now VERIFIED/TESTED SCOPE, no longer blocking; still requires confirming whether Futu's server-side subscription genuinely survives a client-side remove/re-add specifically, which Wave 2 Closure R2 did not perform (it only cut/restored transport on an already-desired subscription, never removed and re-added one). No-token confirmed (still no subscription token/barrier field observed anywhere). |
| 47 | OS clock sync evidence stale | Entitlement/clock | COMPONENT | N | N | N | Y | N | ClockTrust becomes UNKNOWN; absolute freshness INDETERMINATE | LiveFeedController (future) | SPEC_ONLY |
| 48 | Remove/re-add changed key, old stream continues | Subscription truth | COMPONENT | N | N | N | N | Y | Old-key data must never prove new requested stream semantics LIVE | LiveFeedController (future) | SPEC_ONLY |
| 49 | No-token changed-key, unattributable data | Subscription truth | COMPONENT | N | N | N | N | Y | Unattributable event proves neither new key nor its LIVE qualification | LiveFeedController (future) | SPEC_ONLY |
| 50 | EXPECTED_SILENCE between phases | Session/trading expectation | COMPONENT | N | N | N | N | Y | RecoveryCandidate retained, cadence suspended, continuity resumes after; differs from CLOSED_SESSION | LiveFeedController + `market_gate.py`-style logic | SPEC_ONLY |

## Implementation gates

| Gate | Theme | Case IDs |
|---|---|---|
| A | Connection / generation | 1, 6, 14, 15, 20, 28 |
| B | Subscription truth | 2, 3, 25, 26, 29, 32, 37, 41, 45, 48, 49 |
| C | Progress / currentness | 7, 8, 23, 33, 34 |
| D | Continuity / recovery | 4, 5, 10, 12, 21, 22, 35, 38, 39, 42, 46 |
| E | Entitlement / clock | 13, 16, 17, 24, 27, 31, 36, 40, 43, 47 |
| F | Cache trust | 9, 11 |
| G | Concurrency / queue | — (no case in the 50 is dedicated to queue/ingress mechanics specifically; this gate is populated by the execution-model tests in `LIVE_FEED_BLOCKING_EXECUTION_MODEL_V0_1.md` §B1 instead, not by a case ID here) |
| H | Session / trading expectation | 18, 19, 30, 44, 50 |
| I | Shutdown / restart | 20, 28 (shared with Gate A — both a connection-identity concern and a shutdown concern) |

Gate assignment above is one case → one primary gate for table clarity;
several cases (e.g. 20, 46) genuinely touch two themes and are noted where
that overlap matters.

### Minimum subset before "VALIDATING"

Recommended minimum: **Gates A, B, C, D must fully pass** before
LiveFeed implementation can be considered VALIDATING. These four gates
cover the core claim the whole contract exists to protect — that a `LIVE`
declaration means what it says (correct connection identity, genuine
subscription truth, genuine progress, genuine continuity). Gates E
(entitlement/clock), F (cache trust), H (session expectation), and I
(shutdown/restart) are real hardening requirements but are secondary to
that core claim — a system that gets A–D right but has an entitlement bug
is dangerously overconfident about `LIVE`; a system that gets A–D wrong
is unsound regardless of how well it handles entitlement or shutdown.
This is a recommendation, not something already decided elsewhere.

## C1. Existing empirical coverage — explicit mapping, no overclaiming

- **Wave 2 Closure R2 (active-session, 3 completed reconnect cycles on
  `HK.00700`)** — the single largest evidence addition since this
  document was first written. It resolved F17 (reconnect catch-up:
  `DIRECT_CURRENT_ONLY`, 3/3 cycles), F18 (replay marker:
  `NO_AUTHORITATIVE_REPLAY_MARKER_OBSERVED`, 527 payloads scanned),
  AUTO_RESUBSCRIBE (behavioral confirmation, 3/3 cycles), and the
  transport-vs-context-identity + K_1M-ordering halves of F15. **What it
  does NOT do**: it does not test any of cases 4/5/10/12/21/22/25/35/38/46
  at the controller level (no controller exists), and for most of them it
  did not even reproduce their specific adversarial *premise* — every
  tested cycle resumed cleanly at current progress with both streams
  recovering together, so the failure/edge scenarios those cases describe
  (partial recovery, replay bursts, stale-but-newer pushes, single-stream
  revocation) remain unreproduced. See the per-case notes in the table
  above for exactly which cases changed and how. Evidence:
  `runs/2026-09-09T01-43-02-875121Z/` + `derived/r2_classification.json`.
- **CASE 41** (unsubscribe not a drain barrier) — directly supported by
  raw empirical evidence: a successful `unsubscribe()` return, followed
  minutes later by real callbacks for the just-unsubscribed symbol
  (`runs/2026-09-08T07-28-29-758854Z/lifecycle.jsonl` seq 129→138/139,
  per the Futu semantic contract). This confirms the *provider fact* the
  case invariant depends on. It does **not** mean CASE 41 is tested at
  the controller level — no controller exists.
- **CASE 3** (ACK but no data must not produce LIVE) — informed by the
  empirical finding that `query_subscription` visibility (control-plane)
  and actual callback delivery (data-plane) were shown to diverge (a
  freshly-visible symbol in `sub_list` with zero callbacks until an
  explicit `subscribe()` was issued). This is suggestive precedent for
  why the case's invariant is a real risk, not proof the future
  controller handles it correctly.
- **CASE 18/19/30/44/50** (session/trading-expectation gate) — the
  harness's `market_gate.py` (`is_market_active()`) is a working,
  tested, fail-closed precedent for *one piece* of this
  (`ACTIVE_HK_STATES = {MORNING, AFTERNOON}`), but it is harness-only
  code, not wired into any production controller, and doesn't address
  the Phase-1/Phase-2 RecoveryCandidate lifecycle these cases actually
  test.
- **Multi-threaded callback delivery** (empirically confirmed, 5 distinct
  callback threads across all runs) is directly relevant to why Gate G
  (concurrency/queue) and LANE 1's "must be nonblocking/minimal" rule
  exist in the execution-model doc, but it does not map to any single
  case ID in the 50.
- **Duplicate quote payload observed** (2 exact-duplicate groups across
  3,911 distinct source-identity groups, one of them cross-run) is
  adjacent to CASE 23 but is not the same claim — the observed duplicates
  were *identical* payloads under an identical `data_time`, not a
  *changed* payload under the same progress identity (which is what CASE
  23 actually tests). Do not cite the duplicate finding as CASE 23
  coverage.
- **Synchronous blocking-risk discovery** (2 `KNOWN_BLOCKING_RISK` + 123
  `LIKELY_BLOCKING_RISK` methods) directly motivates
  `LIVE_FEED_BLOCKING_EXECUTION_MODEL_V0_1.md` and Gate A/D's operational
  safety but is not itself one of the 50 semantic cases.
- **Explicit caution**: zero out-of-order QUOTE/K_1M events were observed
  across 1,722+1,460 real callbacks. This is **not** a pass of CASE 34's
  invariant (connection-local sequence values must never be compared
  across generations) — no sequence field exists in Futu's payloads at
  all in the evidence gathered, so CASE 34 has not been tested for this
  provider in any direction; the absence-of-inversions finding is about
  ordinary single-session delivery order, a different and much weaker
  claim.

No other case in the 50 has any repository or harness evidence bearing on
it. Every case not mentioned above is `SPEC_ONLY` or `NOT_YET_TESTABLE`
with zero existing coverage of any kind.
