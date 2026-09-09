# Live Feed — Implementation Dependency / Sequencing Map (Draft R1)

Status: **PLANNING ONLY.**

## 0. MISSING_REPO_CONTRACT_ARTIFACT — RESOLVED

**Original finding (superseded):** the frozen Live Feed Reliability V0.1
contract and its permanent 50-case adversarial set once existed only as
prior-session chat context. **This is resolved** — the contract is now
persisted at `docs/LIVE_FEED_RELIABILITY_CONTRACT_V0_1.md` (all 16
governing principles plus the full 50-case adversarial set, verbatim).
This document and the rest of the readiness pack now link to that file as
the canonical source rather than re-quoting it.

**Wave 2 status: CLOSED** as of the Wave 2 Closure R2 documentation
sync. F17, F18, and AUTO_RESUBSCRIBE are VERIFIED within tested scope;
F15 is PARTIALLY_VERIFIED (K_1M cross-reconnect ordering VERIFIED, QUOTE
cross-reconnect ProgressIdentity remains UNRESOLVED). See
`tools/provider_semantics/futu/FUTU_SEMANTIC_CONTRACT_V0_1.md` §4. The
provider-semantic implementation blockers formerly tied to F15/F17/F18/
auto-resubscribe below are now resolved sufficiently for implementation
planning — items previously marked `BLOCKED_BY_PROVIDER_FACT` for those
reasons are updated below. **F04 (DeliveryMode) remains the sole open
provider-semantic P0** and continues to block only final REALTIME
entitlement qualification / full LIVE promotion where it would be
required — it does not block scaffolding or implementation of the
machinery itself.

## 1. Status categories

- `READY_TO_IMPLEMENT_AFTER_DOC_REVIEW` — interface and provider
  semantics are both known well enough to build now that Wave 2 has
  closed; only a documentation/design review is needed before starting,
  not further provider evidence. (Supersedes the former
  `READY_TO_IMPLEMENT_AFTER_WAVE2_CLOSE` label, which is now moot since
  Wave 2 is closed.)
- `BLOCKED_BY_PROVIDER_FACT` — cannot be correctly implemented until a
  specific named unresolved fact is closed; building it now risks baking
  in a guess.
- `SAFE_TO_SCAFFOLD_ONLY` — types/interfaces can be defined now (no
  runtime semantics depend on unresolved facts), but the runtime logic
  inside must wait.
- `DO_NOT_IMPLEMENT_YET` — depends on architectural decisions not yet
  made anywhere in this pack (e.g. the open PRODUCTION_REQUIRED vs
  HARNESS_ONLY question in the execution-model doc), not just on
  provider facts.

## 2. Item map

| Item | Status | Dependencies | Provider facts required | Reason | Safe implementation boundary |
|---|---|---|---|---|---|
| Futu adapter event normalization | SAFE_TO_SCAFFOLD_ONLY | ProviderEvent envelope shape | none for the shape itself | field *shapes* are known; the *values* for `delivery_mode_evidence`/`progress_identity_candidate` depend on unresolved facts | define the dataclass/types now; leave semantic-comparator logic as stubs |
| Callback handlers (`on_quote`, `on_cur_kline`, `on_disconnect`) | SAFE_TO_SCAFFOLD_ONLY | Futu SDK registration API (known, SOURCE_VERIFIED) | none for registration itself | wiring the SDK's own callback registration is fully known from source; what the handler *does* with the payload is where unresolved facts bite | scaffold registration + minimal normalization → envelope; leave `delivery_mode_evidence` as `UNKNOWN` always |
| Immutable ProviderEvent DTO | SAFE_TO_SCAFFOLD_ONLY | none | none | pure data shape, per §A1 of the Futu implementation spec | implement now as a frozen dataclass |
| Controller ingress queue | SAFE_TO_SCAFFOLD_ONLY | ProviderEvent DTO | none | queue mechanics are provider-agnostic | implement the queue interface now; do not wire real Futu traffic through it until the adapter is ready |
| Single-writer controller skeleton | SAFE_TO_SCAFFOLD_ONLY | ingress queue | none for the skeleton; BLOCKED for the actual recovery/qualification logic inside | frozen principle 14 (single-writer) is architectural, not provider-dependent | build the empty event loop + dispatch skeleton; leave every Gate A–I decision as `NotImplementedError`/TODO until its dependencies close |
| Connection lifecycle state | SAFE_TO_SCAFFOLD_ONLY | controller skeleton | `connection_generation` minting scheme is controller-owned, no SDK fact needed | state machine shape is knowable now | implement CONNECTED/DISCONNECTED/RECONNECTING states; leave "how a Futu reconnect maps to a new generation" (§A5 pending question) unresolved |
| Subscription desired registry | SAFE_TO_SCAFFOLD_ONLY | controller skeleton | none | pure controller-owned bookkeeping | implement now |
| Registry revision | SAFE_TO_SCAFFOLD_ONLY | desired registry | none | simple monotonic counter | implement now |
| `stream_subscription_epoch` | BLOCKED_BY_PROVIDER_FACT | connection lifecycle | whether Futu subscriptions have any concept of incarnation at all (still no token/barrier observed — reconfirmed by Wave 2 Closure R2, no token field appeared in any of the 3 reconnect cycles) | implementing this as if a provider incarnation exists, when none was ever observed, risks inventing false precision | scaffold the field as controller-local-only (never provider-attested) until/unless evidence changes that |
| `SemanticStreamKey` | READY_TO_IMPLEMENT_AFTER_DOC_REVIEW (core fields) / BLOCKED (session-mode, adjustment-mode fields) | none | session-mode and adjustment-mode relevance to Futu untested (§A2) — untouched by Wave 2 Closure R2, still open | core 5-field key (`provider, market, symbol, stream_type, timeframe`) is well evidenced; the optional extra dimensions are not | implement the core key now; leave session/adjustment-mode fields absent rather than guessed-default |
| `DeliveryMode` | BLOCKED_BY_PROVIDER_FACT (sole remaining provider-semantic P0) | entitlement evidence path (does not exist yet) | F04 (authoritative REALTIME/DELAYED evidence) — the only UNRESOLVED provider-semantic P0 after Wave 2 closure | no field anywhere confirms delivery mode; hardcoding a default risks a silent false-REALTIME claim | implement the enum with `UNKNOWN` as the only reachable value from the Futu adapter until entitlement evidence is found; this does not block the rest of the machinery (see doc §0) |
| `ProgressIdentity` — K_1M | READY_TO_IMPLEMENT_AFTER_DOC_REVIEW (including cross-reconnect comparator) | connection lifecycle | none — F15's K_1M half is VERIFIED, TESTED SCOPE (Wave 2 Closure R2: `time_key` ordering held calendar-anchored across all 3 reconnects) | single-session and cross-reconnect K_1M comparator logic are both now evidenced within tested scope (HK, `HK.00700`, 3 cycles) | implement the K_1M comparator for both within-generation and cross-generation use; keep scope caveats (HK-tested only) in comments/docs, not as a runtime gate |
| `ProgressIdentity` — QUOTE | READY_TO_IMPLEMENT_AFTER_DOC_REVIEW (single-session comparator only) / BLOCKED (cross-reconnect comparator) | connection lifecycle | F15's QUOTE half remains UNRESOLVED/INSUFFICIENT — no stress test beyond confirming no new sequence field appeared | single-session QUOTE comparator logic (§A3) is well evidenced; cross-generation QUOTE behavior is not, and must not be manufactured | implement the single-session comparator now; explicitly reject/flag any cross-generation QUOTE progress comparison as UNPROVABLE until further evidence exists |
| `CurrentnessBoundary` | READY_TO_IMPLEMENT_AFTER_DOC_REVIEW (as part of "recovery state machinery") | ProgressIdentity | none blocking the mechanism itself — F17 is VERIFIED, TESTED SCOPE (Wave 2 Closure R2: 3/3 cycles resumed DIRECT_CURRENT_ONLY); final REALTIME-dependent qualification still gated by F04 | the Phase-1 currentness mechanism can now be built against known, tested reconnect behavior; only the DeliveryMode-dependent edge of "full LIVE" stays conservative | implement the boundary-crossing rule against the tested DIRECT_CURRENT_ONLY behavior; the resulting Phase-1 proof still cannot alone promote to LIVE while DeliveryMode is UNKNOWN (frozen principle 7) |
| Continuity recovery | READY_TO_IMPLEMENT_AFTER_DOC_REVIEW (as part of "recovery state machinery") | CurrentnessBoundary | none blocking the mechanism itself — F18 is VERIFIED_NEGATIVE_OBSERVATION (`NO_AUTHORITATIVE_REPLAY_MARKER_OBSERVED`, 274 QUOTE + 253 K_1M payloads scanned) | Phase 2's core requirement — must not classify replay from timing heuristics — is now backed by a confirmed absence-of-marker finding rather than an open question; the machinery can be built to always treat provenance as UNKNOWN absent an authoritative field | implement Phase 2 against the confirmed rule "no timing-based replay inference, ever"; final LIVE promotion still gated by F04 where REALTIME is required |
| Auto-reconnect adaptation (§A5) | READY_TO_IMPLEMENT_AFTER_DOC_REVIEW (both the tolerance rule and the generation-mapping boundary) | connection lifecycle | none — AUTO_RESUBSCRIBE is VERIFIED, TESTED SCOPE (3/3 cycles, behavioral confirmation, not just source prediction); generation-mapping boundary (controller generation != SDK conn_id != OpenQuoteContext identity) is now documented in the Futu implementation spec §A5 | both the defensive rule and the generation-identity boundary are evidenced; the exact generation-allocation algorithm is still intentionally unspecified (architectural choice, not a provider-fact gap) | implement now: adapter emits reconnect as transport evidence only; controller mints its own generation per observed transport loss, never per SDK-internal retry/conn_id/object-identity |
| Health data structures (the shape of a LiveFeedController health signal) | SAFE_TO_SCAFFOLD_ONLY | controller skeleton | none | the *shape* of a controller-owned, data-plane-scoped health signal is knowable now — it is a documented peer to `CircuitBreaker`/`FallbackStateMachine`/`MarketDataHealth.signal_permission`, not a replacement for or unification of them (see repo-integration-risks doc — do not unify) | define the type now |
| Health aggregation / final health policy (how the controller's signal and the three existing ones interact for a given consumer decision) | DO_NOT_IMPLEMENT_YET | health data structures, entitlement/DeliveryMode | none provider-specific, but depends on first documenting the authority boundary between the repo's three existing health/fallback concepts (see repo-integration-risks doc, BLOCKER) | wiring aggregation/policy logic before that authority boundary is written down risks encoding an undocumented, ad hoc precedence order between four legitimately-separate signals | write the authority-separation documentation first, at the architecture level, before implementing aggregation/policy logic |
| Cache trust epoch | SAFE_TO_SCAFFOLD_ONLY | controller skeleton | none | pure controller-owned bookkeeping (frozen principle 12) | implement now |
| Session/trading expectation | READY_TO_IMPLEMENT_AFTER_DOC_REVIEW | none | none — `market_gate.py`'s fail-closed pattern is already validated in the harness | well-precedented, low-risk, no unresolved provider facts | port the fail-closed `is_market_active`-style pattern into the controller; still needs EXPECTED_SILENCE vs CLOSED_SESSION distinction (CASE 18/19/30/44/50) built out, which is new logic but not provider-fact-blocked |
| Futu blocking-command executor (LANE 3) | DO_NOT_IMPLEMENT_YET | none provider-specific | none provider-specific, but blocked on the open PRODUCTION_REQUIRED vs HARNESS_ONLY design question in the execution-model doc | building this before deciding process-isolation-vs-thread-timeout risks having to redo the whole executor | resolve the isolation-mechanism design question first; the harness's `bounded_probe.py` is explicitly not a production answer |
| Reconnect generation mapping | READY_TO_IMPLEMENT_AFTER_DOC_REVIEW (as a design boundary, not a fixed algorithm) | connection lifecycle, auto-reconnect adaptation | none blocking — F15 (transport-vs-context identity), F17, and behavioral auto-resubscribe confirmation are all VERIFIED/TESTED SCOPE (Wave 2 Closure R2, 3 completed cycles) | the identity-separation boundary (`connection_generation != sdk conn_id != OpenQuoteContext identity != stream_subscription_epoch != desired_registry_revision`) is now evidenced, not merely asserted; the exact generation-minting algorithm remains an open architectural choice, not a provider-fact gap | implement the boundary (never derive generation from Python object identity or SDK conn_id); the controller mints its own generation on each observed transport loss it recognizes |
| AI/DecisionEligibility integration | OUT OF SCOPE | — | — | explicitly out of scope for Live Feed V0.1 per the frozen contract | do not touch |

## D1. Proposed implementation sequence (candidate, not binding)

```
Phase 0  — provider contract closure — DONE
           + frozen contract persisted in the repo (§0 above)
           + F17/F18/F15(K_1M half)/AUTO_RESUBSCRIBE closed
             (Wave 2 Closure R2, active-session evidence)
           + F04 DeliveryMode / QUOTE cross-reconnect ProgressIdentity
             (F15 QUOTE half) remain open — see below

Phase 1  — immutable event/data types
           SemanticStreamKey (core fields)
           ProviderEvent DTO
           ingress queue interface

Phase 2  — Futu callback normalization
           disconnect normalization
           NO recovery claims anywhere in this phase

Phase 3  — single-writer controller lifecycle skeleton
           connection lifecycle state (generation minting, controller-owned)
           desired registry + revision

Phase 4  — subscription reconciliation / command executor
           (blocked until the PRODUCTION_REQUIRED vs HARNESS_ONLY
           isolation-mechanism question is resolved — see execution-model
           doc; this blocker is architectural, not provider-fact-based,
           and is unaffected by Wave 2 closure)

Phase 5  — progress/currentness implementation
           now buildable — F17 is VERIFIED/TESTED SCOPE and the K_1M half
           of F15 is VERIFIED/TESTED SCOPE; the QUOTE half of F15 stays
           conservative (comparator returns UNPROVABLE for cross-reconnect
           QUOTE progress rather than blocking the phase entirely)

Phase 6  — recovery qualification (CurrentnessBoundary → Continuity → LIVE)
           buildable — F18 is VERIFIED_NEGATIVE_OBSERVATION (no replay
           marker, so Phase 2's classification rule is simply "always
           UNKNOWN absent an authoritative field"); the final promotion
           to full LIVE remains gated by F04 (DeliveryMode) wherever
           REALTIME entitlement would be required — this is a fail-closed
           runtime gate inside Phase 6, not a reason to defer building it

Phase 7  — cache trust integration

Phase 8  — adversarial validation against the 50-case set (Gates A-D
           minimum, per the test-map doc's recommendation)
```

This candidate sequence matches the repo's actual dependency structure
reasonably well. Phases 1-3 never needed the Wave 2 facts and remain
`SAFE_TO_SCAFFOLD_ONLY`/`READY_TO_IMPLEMENT_AFTER_DOC_REVIEW`. Phases 5-6,
formerly gated on `F15`/`F17`/`F18`, are now buildable: those items closed
via Wave 2 Closure R2's active-session evidence (3 completed reconnect
cycles on `HK.00700`). The **only** remaining provider-fact gate in the
whole sequence is `DeliveryMode`/F04, which narrows to a single runtime
check inside Phase 6 (deny full LIVE promotion where REALTIME entitlement
is required and unproven) rather than blocking a whole phase. One
adjustment from the generic phase template still applies: Phase 4
(command executor) remains blocked on the isolation-mechanism design
question (architectural, not provider-fact-based, and untouched by this
documentation pass) — the harness's `bounded_probe.py` is explicitly
non-production.
