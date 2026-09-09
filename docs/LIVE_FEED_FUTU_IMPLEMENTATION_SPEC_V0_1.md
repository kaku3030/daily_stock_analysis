# Live Feed / Futu Streaming Adapter — Implementation Spec (Draft R1)

Status: **PLANNING ONLY — no production code exists yet for this spec.**
Scope: maps the frozen Live Feed Reliability V0.1 principles (now
persisted at `docs/LIVE_FEED_RELIABILITY_CONTRACT_V0_1.md`) onto this
repository's actual module boundaries, for a future Futu/Moomoo
streaming `MarketDataAdapter`.

**Wave 2 status: CLOSED** (see `tools/provider_semantics/futu/FUTU_SEMANTIC_CONTRACT_V0_1.md`
§4). F17, F18, and AUTO_RESUBSCRIBE are VERIFIED within their tested
scope; F15 is PARTIALLY_VERIFIED (transport-vs-context identity and K_1M
cross-reconnect ordering VERIFIED, QUOTE cross-reconnect ProgressIdentity
remains UNRESOLVED). The sole remaining provider-semantic P0 is **F04
(DeliveryMode)**, which does not block scaffolding or implementation of
the machinery below — it blocks only full `LIVE` promotion where REALTIME
entitlement would be required (see §A4). Sections below have been updated
to reflect the R2 evidence; anything still marked
`IMPLEMENTATION_BLOCKED_BY_PROVIDER_FACT` is blocked specifically on F04
or on genuinely untested items (session-mode/adjustment-mode
SemanticStreamKey fields, QUOTE cross-reconnect identity), not on F17/F18/
F15/AUTO_RESUBSCRIBE, which are closed.

## 0. Existing repo boundaries (ground truth, inspected this task)

| Concept | File | Class/function |
|---|---|---|
| Adapter interface | `data_provider/market_data_adapter.py:153` | `MarketDataAdapter(ABC)` — `get_latest_quote`, `get_bars`, `subscribe`, `get_session_status`, `get_provider_health`, `reconnect`. **No `unsubscribe()`, no `connect()`/`close()` on the interface.** |
| Normalized models | `data_provider/market_data_adapter.py:41,71,33` | `Bar` (frozen dataclass), `Quote` (frozen dataclass), `MarketDataHealth` |
| Legacy quote model | `data_provider/realtime_types.py:110` | `UnifiedRealtimeQuote` — different lineage, used only by non-adapter fetchers; do not reuse for the streaming adapter |
| Ingest service | `src/services/realtime_market_data.py:49` | `RealtimeMarketDataService.ingest(bar)` — synchronous, `RLock`-guarded, requires `timeframe=="1m"` |
| Bar aggregation | `data_provider/market_bar_builder.py:54` | `aggregate_bars(...)` — trusts each source `Bar.is_complete`/`is_closed`, does not require closed input |
| Router | `data_provider/market_data_router.py:21,104` | `MarketDataRouter(MarketDataAdapter)` — `subscribe()` routes to primary only, **never falls back to polling** (enforced by `tests/test_market_data_router.py:133`) |
| Existing Futu code | `data_provider/futu_fetcher.py:59`, `data_provider/futu_fundamental_adapter.py:11` | `FutuFetcher(BaseFetcher)` — polling-only, `UnifiedRealtimeQuote`, no subscribe/unsubscribe. Not a `MarketDataAdapter`. **No production Futu streaming adapter exists today.** |
| Precedent: atomic multi-symbol subscribe w/ rollback | `data_provider/xtquant_market_data_adapter.py:214` | `XtquantMarketDataAdapter.subscribe()` — collects subscription ids, rolls back via `unsubscribe_quote` on partial failure |
| Precedent: honest refusal to fake streaming | `data_provider/pytdx_market_data_adapter.py:185`, `data_provider/existing_market_data_adapter.py:208` | both raise `NotImplementedError` rather than simulate streaming via polling |
| Provider semantics evidence | `tools/provider_semantics/futu/FUTU_SEMANTIC_CONTRACT_V0_1.md` | authoritative source for every Futu-specific fact cited below |

## 1. Event flow

```
Futu SDK callback (on_quote / on_cur_kline / on_disconnect / ...)
  → provider-specific normalization              [Futu adapter, LANE 1]
  → immutable ProviderEvent envelope              [Futu adapter, LANE 1]
  → controller ingress queue                      [boundary — see Blocking Execution Model doc]
  → single-writer LiveFeedController               [LANE 2]
  → RealtimeMarketDataService.ingest()             [existing, unchanged]
  → snapshot consumers                             [existing, unchanged]
```

The Futu adapter owns everything left of the ingress queue. The
controller (not yet designed beyond the frozen principles) owns
everything right of it. `RealtimeMarketDataService.ingest()` is reused
unmodified — it already accepts pre-normalized `Bar` objects synchronously
and is agnostic to how they arrived.

### Adapter owns

- `OpenQuoteContext` creation/closure
- Futu SDK handler registration (`on_quote`, `on_cur_kline`, `on_disconnect`, etc.)
- QUOTE push normalization → `Quote`/`ProviderEvent`
- K_1M push normalization → `Bar`/`ProviderEvent`
- provider timestamp interpretation (per `FUTU_SEMANTIC_CONTRACT_V0_1.md` §2 TEMPORAL — second-resolution, naive-string, Beijing/US-Eastern per F-SDK-014)
- provider disconnect callback normalization (`CloseReason` → normalized reason)
- provider error normalization (raw OpenD `ret`/error text → normalized error envelope)
- entitlement evidence normalization (whatever evidence exists — currently none confirms `DeliveryMode`, see §4 below)
- provider semantic comparator implementation (e.g. is this `time_key` the same interval as that one)
- provider-specific `subscribe`/`unsubscribe` calls

### Adapter does NOT own

- business decision eligibility (`SignalPermission` scoring stays in `evaluate_health`)
- AI calls
- signal generation
- portfolio logic
- global retry policy (frozen principle 15 — no blocking SDK call on the controller thread; retry policy for the *controller's* recovery state machine belongs to the controller, not the adapter)
- final LiveFeed `LIVE` qualification (frozen principles 1, 3, 4, 13 — only the controller may declare `LIVE`)
- strategy decisions

## A1. Provider Event Envelope (candidate)

| Field | Classification | Note |
|---|---|---|
| `runtime_instance_id` | REQUIRED_NOW | process-local identity, no provider dependency |
| `provider_id` | REQUIRED_NOW | constant `"futu"` |
| `adapter_context_id` | REQUIRED_NOW | identifies which `OpenQuoteContext` instance produced this event — needed because the SDK's own reconnect creates no new context, but the adapter may recreate one on `close()`/recreate cycles |
| `connection_generation` | REQUIRED_NOW, **controller-issued, not provider-issued** | Futu SDK exposes no connection/session id (`FUTU_SEMANTIC_CONTRACT_V0_1.md` — no such field observed in any payload); this must be a locally-minted counter the adapter stamps from a value the controller hands it |
| `observed_at_utc` | REQUIRED_NOW | adapter's own receipt wall-clock, UTC-aware |
| `observed_at_monotonic` | REQUIRED_NOW | for latency/duration math, immune to clock jumps (frozen principle 17) |
| `local_enqueue_seq` | REQUIRED_NOW | monotonic local counter, adapter-assigned, analogous to `LifecycleRecorder.event_seq` already used in the harness |
| `thread_id` | REQUIRED_NOW | SDK callback delivery is confirmed multi-threaded (`FUTU_SEMANTIC_CONTRACT_V0_1.md` §2 THREADING) |
| `symbol` | REQUIRED_NOW | canonical form only (`HK.00700`, not `HK.700` — confirmed rejection of non-canonical form) |
| `market` | REQUIRED_NOW | |
| `stream_type` | REQUIRED_NOW | `QUOTE` / `K_1M` / etc. |
| `raw_provider_timestamp` | REQUIRED_NOW | verbatim string as received, never discarded |
| `normalized_timestamp_candidate` | OPTIONAL_PROVIDER_EVIDENCE | second-resolution only (§2 TEMPORAL); do not present as sub-second precision |
| `semantic_stream_key` | REQUIRED_NOW | see §A2 |
| `delivery_mode_evidence` | UNRESOLVED_PENDING_WAVE2 | no authoritative REALTIME/DELAYED evidence exists yet — field must carry `UNKNOWN` by default (see §A4) |
| `provenance` | REQUIRED_NOW | `"PUSH"` vs `"PULL"` vs whatever the adapter itself directly knows (e.g. distinguish a genuine SDK push callback from a diagnostic pull query) |
| `progress_identity_candidate` | REQUIRED_NOW, but semantics differ per stream — see §A3 | |
| `progress_comparator_id` | REQUIRED_NOW | identifies *which* comparator produced the candidate, since QUOTE and K_1M need different comparators |
| `raw_payload_reference` | OPTIONAL_PROVIDER_EVIDENCE | diagnostic only; must not be required for correctness |
| `event_kind` | REQUIRED_NOW | `DATA` / `DISCONNECT` / `ERROR` / `SUBSCRIPTION_RESULT` / `ENTITLEMENT` / `HEARTBEAT` |

`NOT_PROVIDER_AVAILABLE`: no field in this envelope should be labeled this
yet — everything above is either directly observable from the SDK/OpenD or
locally synthesizable. If a future field (e.g. a genuine provider sequence
number) turns out not to exist, it must be omitted from the envelope
entirely rather than included and always-empty.

## A2. SemanticStreamKey (candidate, Futu scope)

Minimum required components based on current evidence:

- `provider` = `"futu"`
- `market` (e.g. `"HK"`)
- `symbol` (canonical form, e.g. `"HK.00700"`)
- `stream_type` (`"QUOTE"` / `"K_1M"`)
- `timeframe` (only meaningful for K-line streams; `"1m"` for K_1M)

Explicitly unresolved / not yet confirmed to matter for Futu specifically,
so must NOT be silently folded into `symbol + stream_type`:

- **session mode** (regular vs. pre/post-market) — Futu HK entitlement and
  push behavior in non-regular sessions was never tested (all Wave 1/2
  evidence is regular-session or closed-market). `IMPLEMENTATION_BLOCKED_BY_PROVIDER_FACT`.
- **adjustment mode** (e.g. split/dividend adjustment for K-line) — not
  probed at all in Wave 1/2. `IMPLEMENTATION_BLOCKED_BY_PROVIDER_FACT`.
- **feed/access path** — entitlement was shown to differ between pull
  (`get_stock_quote`, denied) and push (`subscribe`, delivered) for the
  same symbol in the same session (§2 ENTITLEMENT). If Futu ever exposes
  more than one push access path for the same symbol+stream_type, this
  would need to enter the key. No evidence either way yet.

## A3. ProgressIdentity strategy (candidate, per stream)

**QUOTE:**
- `data_time` is second-resolution and NOT a unique progress identity
  (multiple material updates can share one `data_time` — verified).
- No provider sequence/cursor observed anywhere in the QUOTE payload.
- Candidate: treat `(data_time, full_payload_hash)` as the progress
  identity tuple so identical-payload duplicates are recognizable, but do
  NOT treat `data_time` alone as sufficient to prove a *new* progress
  event occurred (frozen principle 11 — key equality is necessary, not
  sufficient).

**K_1M:**
- `time_key` behaves like interval-end boundary identity (PARTIALLY_VERIFIED,
  n=8 transitions, single symbol/session — see contract §3).
- Forming updates repeat under the same `time_key`; this is expected, not
  an anomaly.
- `time_key` is explicitly NOT bar-completeness evidence (no completeness
  flag exists in the payload) — this remains true across reconnect
  boundaries too; a new/changed `time_key` after reconnect still says
  nothing about whether the prior bar closed cleanly.
- No sequence/cursor observed, before or after reconnect.
- For tested HK semantics, `time_key` **is acceptable as a semantic
  interval progress candidate across SDK reconnect boundaries**
  (Wave 2 Closure R2, VERIFIED — TESTED SCOPE: 3/3 cycles, calendar-anchored
  ordering held with no reset/reuse — `FUTU_SEMANTIC_CONTRACT_V0_1.md`
  F15 subsection). This is scope-limited to HK/`HK.00700`-class semantics
  as tested; provider-specific normalization is still required per
  market, and this must not be read as a universal Futu claim.
- Candidate: adapter emits every K_1M push as its own `ProviderEvent`
  (never collapses repeats itself); completeness/closedness determination
  stays where it already lives — `RealtimeMarketDataService`/
  `aggregate_bars` — via the adapter setting `Bar.is_complete`/`is_closed`
  from its own boundary-crossing logic, not from any provider-supplied flag.

**Cross-reconnect behavior:**
- **K_1M — VERIFIED, TESTED SCOPE** (see above). Normalized semantic
  interval identity (`time_key`) may serve as the cross-reconnect progress
  comparator for K_1M without relying on the SDK's internal `conn_id`.
- **QUOTE — UNRESOLVED / INSUFFICIENT.** `data_time` remained
  second-resolution with no new sequence/cursor field appearing
  post-reconnect in the 3 tested cycles, but this was not independently
  stress-tested. QUOTE `data_time` alone MUST NOT become a manufactured
  unique ProgressIdentity — if no stronger semantic identity becomes
  available, QUOTE strict progress qualification across reconnects may
  remain UNPROVABLE/LIMITED. That is an acceptable provider-contract
  result, not a gap to paper over with synthetic ordering.
- Replay provenance: no authoritative replay marker was observed in the
  inspected payload surface for either stream (Wave 2 Closure R2,
  `NO_AUTHORITATIVE_REPLAY_MARKER_OBSERVED`, 274 QUOTE + 253 K_1M
  callbacks scanned). The adapter/controller MUST NOT classify
  REALTIME vs. REPLAY vs. BACKFILL from burst timing, arrival clustering,
  old source timestamps, or callback-ordering heuristics — where
  provenance cannot be proven from an authoritative field, it stays
  UNKNOWN/UNVERIFIED.

## A4. DeliveryMode integration

Per `FUTU_SEMANTIC_CONTRACT_V0_1.md` §4, `DeliveryMode` (REALTIME vs
DELAYED) has **no authoritative evidence source** identified anywhere in
the SDK payloads inspected. Therefore:

> `DeliveryMode.UNKNOWN` is the default for every Futu event unless and
> until authoritative entitlement evidence is found and independently
> confirmed (not inferred from timestamp freshness or push continuity).

Explicitly forbidden inference paths (frozen principles 3, 7):
- successful `subscribe()` → REALTIME — forbidden
- fresh-looking `data_time` → REALTIME — forbidden
- continuous push activity → REALTIME — forbidden
- "it's HK, HK pushes are always realtime for this account" — forbidden
  without a per-symbol/per-session entitlement check, since entitlement
  was empirically shown to differ by access path for the same symbol.

Where entitlement evidence *would* enter later, if Futu ever exposes it
(e.g. a documented entitlement query endpoint, or an explicit field in a
push payload): it would enter as its own `event_kind=ENTITLEMENT`
`ProviderEvent`, evaluated by the controller, never inferred client-side
inside the adapter from unrelated fields.

**F04 does not block scaffolding.** With Wave 2 closed, F04 (DeliveryMode)
is the sole remaining provider-semantic P0. It does NOT block building:
adapter callback normalization, the ingress queue, controller lifecycle,
subscription registry, generation handling, reconnect/recovery machinery,
the K_1M comparator, or health data structures — all of those can be
implemented with `DeliveryMode.UNKNOWN` flowing through them correctly.
F04 DOES block one specific thing: promotion to full `LIVE` wherever
REALTIME entitlement would be required for that qualification. This is
fail-closed by design, not a blanket implementation freeze.

## A5. Auto-reconnect provider constraint

Verified (`FUTU_SEMANTIC_CONTRACT_V0_1.md` §2 RECONNECT/TRANSPORT,
SOURCE_VERIFIED facts F-SDK-002/004/005/008/009):

- `_auto_reconnect` defaults `True`, hardcoded, no public disable control.
- Retry interval ≈ 6s, no backoff, no cap, no public policy control.
- On every successful (re)connect, the SDK unconditionally re-issues
  `subscribe()` for whatever is in its own local `_sub_record` — a
  **fresh subscribe**, not a backfill/replay. It carries zero information
  about what was missed while disconnected.

Implementation adaptation rule (frozen principles 4, 13):

> **SDK transport reconnect ≠ LiveFeed recovery ≠ LIVE qualification.**

- The adapter MAY be forced to simply tolerate the SDK's autonomous
  transport reconnect — there is no public API to prevent it.
- When the SDK reconnects and auto-resubscribes, the adapter must emit
  ONLY transport/reconnect evidence (`event_kind=DISCONNECT` was already
  fired earlier; the reconnect itself becomes a distinct low-level
  transport event, not a `SUBSCRIPTION_RESULT` or `DATA` event implying
  restored trust).
- The SDK's autonomous resubscribe must NOT be treated by the adapter (or
  anything downstream) as: marking the feed LIVE, restoring stream trust,
  confirming subscription success in the sense the controller cares about,
  or bypassing Currentness/Continuity qualification. The controller alone
  decides those things, from its own evidence, not from the SDK's silent
  internal resubscribe. **This is now behaviorally confirmed, not just a
  source-level precaution**: Wave 2 Closure R2 observed auto-resubscribe
  restore push flow 3/3 times, with zero missed-interval information
  carried across — the rule above still applies to that confirmed
  behavior exactly as written.

**Generation semantics (resolved this pass — do not implement beyond this
boundary yet):**

Controller `connection_generation` represents a **controller-observed**
recovery/transport incarnation — not every provider-private reconnect
attempt. Conceptually:

```
stable connected state
  → first authoritative transport loss observed
  → controller enters recovery
  → allocate/advance controller recovery generation
```

The SDK may internally perform retry #1, retry #2, retry #3, ... — Wave 2
Closure R2 observed exactly this (a monotonically incrementing internal
`conn_id`, 2→89 across 3 cycles, and repeated `RemoteClose`/`ReadFail`
retries every ~6s). All of those private attempts belong to the *same*
controller recovery generation; the controller does not mint a new
generation per SDK-internal retry.

Do NOT define controller generation as any of:
- Python `OpenQuoteContext` object lifetime — confirmed (R2) to survive
  multiple genuinely distinct transport incarnations; using it would hide
  real generation changes.
- every SDK `conn_id` increment — confirmed (R2) to be a diagnostic-only,
  publicly-unverified internal counter; may be logged for diagnostics,
  never used as business identity (`controller_generation = futu_conn_id`
  is explicitly forbidden).
- every private SDK retry attempt — would create far more generations
  than the controller's own recovery state machine needs or should expose.

This boundary is intentionally not specified further here (no exact
generation-allocation algorithm) beyond what the frozen contract already
requires: `connection_generation != sdk connection attempt counter !=
OpenQuoteContext object identity != stream_subscription_epoch !=
desired_registry_revision` (Live Feed Reliability V0.1 §4) — these five
identities must remain distinct, and none may substitute for another.
