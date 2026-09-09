<!-- Non-production evidence registry. Not an architecture document. -->
# Futu/Moomoo Provider Semantic Contract — V0.1 Draft

This is an **evidence registry**, not an implementation spec. It records
what has actually been observed (live, against real OpenD) or read
directly from installed SDK source, with explicit confidence labels and
pointers back to the raw evidence. Nothing here is production code, and
nothing here should be treated as final until reviewed against a design
that actually consumes it.

## 1. Environment / Provenance

- **SDK:** `futu` 10.08.6808
- **OpenD observed server version:** `server_ver = "1010"` (`get_global_state()`)
- **Evidence runs:**
  - Wave 1 smoke: `runs/2026-09-08T06-26-05-772214Z/`
  - Wave 1 main: `runs/2026-09-08T06-32-20-832577Z/` (+ `derived/r1_f02_f28_transition_analysis.json`)
  - Wave 1 Closure R1 (F04 fix + F06 clean test): `runs/2026-09-08T07-12-58-464339Z/`
  - Wave 2 R0 (Level 0, unsubscribe/barrier/boundary-B): `runs/2026-09-08T07-28-29-758854Z/` (+ `derived/wave2_r1_opportunistic_analysis.json`)
  - Wave 2 Closure R1 (Level 1 proxy, genuine transport loss): `runs/2026-09-08T08-35-00-200191Z/` (+ `derived/sdk_source_inspection.json`)
  - Wave 2 Closure R2 (active-session reconnect/catch-up, 3 completed cycles): `runs/2026-09-09T01-43-02-875121Z/` (+ `derived/r2_classification.json`, `derived/raw_hashes.json`)
  - SDK source inspection (offline, this pack): `derived/source_inspection_offline_v1.json`
  - Sync API risk inventory (offline, this pack): `derived/sync_api_risk_inventory.json`
  - Cross-run offline analysis (this pack): `derived/wave1_wave2_offline_analysis.json`

**Wave status:** Wave 1 CLOSED. Wave 2 CLOSED (F17/F18/AUTO_RESUBSCRIBE verified within tested scope below; F15 partially verified; F04 DeliveryMode remains the sole open P0 — see Section 4).

## 2. VERIFIED / ACCEPTED FACTS

### TEMPORAL

| Claim | Confidence | Evidence |
|---|---|---|
| QUOTE `data_time` is second-resolution | VERIFIED | `RAW_EMPIRICAL` — 154+ instances of price/volume change with unchanged `data_time` across 260+ samples; run `...T06-32-20.../lifecycle.jsonl` |
| Multiple material quote updates may share one `data_time` | VERIFIED | same as above |
| QUOTE `data_time` is not a unique ProgressIdentity | VERIFIED | same as above |
| Raw quote/kline timestamps are naive strings, no timezone offset | VERIFIED | `BOTH` — every sampled raw field lacks an offset/`Z` marker; SDK docstring for `get_stock_quote` explicitly documents `data_time` as "US Eastern for US stocks, Beijing time for HK/A-share stocks" with no explicit UTC offset in the value itself (`F-SDK-014`, `derived/source_inspection_offline_v1.json`) |
| K_1M repeatedly updates the same `time_key` while forming | VERIFIED | `RAW_EMPIRICAL` — up to 38 pushes observed for one `time_key` before the next appeared |
| K_1M payload has no explicit closed/completed flag | VERIFIED | `RAW_EMPIRICAL` — full raw K_1M key set (`code, name, time_key, open, close, high, low, volume, turnover, k_type, last_close, pe_ratio, turnover_rate`) contains no such field, confirmed across every run |
| Tested HK K_1M behavior strongly supports `time_key` as interval-**end** boundary identity | PARTIALLY_VERIFIED | `RAW_EMPIRICAL` — R1 transition-edge analysis: `first_callback(K+1) − boundary(K)` under the end-candidate clusters tightly in [−0.40s, −0.06s] (n=8 transitions); under the start-candidate the same real events shift by a mechanical −60s. See `derived/r1_f02_f28_transition_analysis.json` |
| Next interval key may appear slightly before the minute boundary | VERIFIED | `RAW_EMPIRICAL` — same artifact; `last_callback(K) − boundary(K)` was −0.65s to −7.25s (before, not after) |
| K_1M `time_key` must not automatically imply bar closure | VERIFIED | derived from the two facts above plus the missing-completeness-flag fact |
| Zero-volume K_1M push does not prove completed zero-trade minute | VERIFIED | `RAW_EMPIRICAL` — all 9 zero-volume pushes observed (7 in one run, 2 in another) occurred at the :59s mark of the *prior* minute, tagged with the *next* minute's boundary and flat OHLC=last_close — consistent with a placeholder push for a just-opening period, not a completed silent one |

### SUBSCRIPTION / CONTROL PLANE

| Claim | Confidence | Evidence |
|---|---|---|
| `subscribe` `ret=0`/no payload is administrative evidence only | VERIFIED | `BOTH` — F-SDK-010/011 (no client-side confirmation-of-delivery logic) + repeated empirical confirmation that RET_OK precedes callback arrival by an unrelated interval |
| Request return surface is not per-symbol LIVE confirmation | VERIFIED | same |
| Tested mixed valid+invalid subscription produced no observed valid-symbol side effect | VERIFIED | `RAW_EMPIRICAL` — clean test with `HK.09988` (never previously subscribed this session): pre-state and post-state `query_subscription()` were byte-identical (`sub_list` unchanged), and 0 callbacks observed for `HK.09988` in a 15s window. `runs/2026-09-08T07-12-58-464339Z/sdk_calls.jsonl` |
| `query_subscription` visibility does not prove data-plane push | VERIFIED | `RAW_EMPIRICAL` — a brand-new `OpenQuoteContext` saw `HK.00700` in `sub_list` immediately, with zero callbacks arriving over a 10s window until `subscribe()` was explicitly called on that context |
| OpenD/shared subscription registry can be visible across `OpenQuoteContext` instances | VERIFIED (wording corrected per Wave 2 Closure R1 review) | `RAW_EMPIRICAL` — same evidence; `own_used=0` on the new context distinguished "visible" from "owned by this connection" |
| New context may see shared registry state while receiving zero callbacks | VERIFIED | same |
| Explicit `subscribe()` may still be required for that new context | VERIFIED | same |

### UNSUBSCRIBE

| Claim | Confidence | Evidence |
|---|---|---|
| Successful unsubscribe return is NOT a callback-drain barrier | **VERIFIED** (strong negative observation from one clean instance, per the task's own standing rule that a positive disproof needs no repetition) | `RAW_EMPIRICAL` — `runs/.../7-28-29.../lifecycle.jsonl` seq 129 (`ret=0`) through seq 138–139 |
| Callbacks observed after successful unsubscribe return and after `query_subscription` removed the symbol | VERIFIED | same — `query_subscription` at seq 131 already showed `QUOTE` removed from `sub_list`; callbacks for `HK.00700` QUOTE still arrived at seq 138 (+6.36s) and 139 (+7.81s) |

### RECONNECT / TRANSPORT

| Claim | Confidence | Evidence |
|---|---|---|
| Involuntary transport failure triggers observable `on_disconnect` callback | VERIFIED | `BOTH` — F-SDK-007 + `runs/.../8-35-00.../lifecycle.jsonl` (196 real firings) |
| `CloseReason.ReadFail` and `CloseReason.RemoteClose` observed | VERIFIED | `RAW_EMPIRICAL` — 3× ReadFail (one spontaneous, unprompted; two during the induced outage), 193× RemoteClose (induced) |
| SDK automatically retries transport connection | VERIFIED | `BOTH` — F-SDK-004/005 + 196 real retry attempts observed |
| Observed retry cadence approximately 6 seconds | VERIFIED | `RAW_EMPIRICAL` — 196 attempts over 1,171s = 6.005s average; matches source's `_reconnect_interval=6` |
| No backoff/cap observed across 193 consecutive failures | VERIFIED | `BOTH` — source shows a constant interval with no attempt counter (F-SDK-005); behaviorally confirmed over ~19.5 minutes with zero cadence change |
| Current SDK source contains unbounded reconnect behavior | SOURCE_VERIFIED | F-SDK-002/004/005 |
| Public auto-reconnect disable control: NONE OBSERVED | SOURCE_VERIFIED | F-SDK-001/002 — no constructor parameter or public setter |
| Public reconnect-policy control: NONE OBSERVED | SOURCE_VERIFIED | F-SDK-001/004/005 |
| Public synchronous connect timeout: NONE OBSERVED | SOURCE_VERIFIED | F-SDK-001/002 |
| Reconnect cadence ~6s reconfirmed on a fresh, independent active-session run | VERIFIED | `RAW_EMPIRICAL` — Wave 2 Closure R2, 3 cut windows, `RemoteClose` retries spaced ~6.0–6.1s apart, `runs/2026-09-09T01-43-02-875121Z/lifecycle.jsonl` |
| Disconnect-reason pattern: first disconnect of a cut window is `CloseReason.ReadFail`, subsequent retry failures during the same window are `CloseReason.RemoteClose` | PARTIAL / OBSERVATIONAL | `RAW_EMPIRICAL` — reproduced identically across all 3 R2 cycles; recorded as a diagnostic observation, not asserted as a provider-guaranteed lifecycle rule |
| SDK-internal `on_disconnect` `conn_id` is a monotonically incrementing counter across the process lifetime, not reused/reset per attempt | DIAGNOSTIC_ONLY | `RAW_EMPIRICAL` — R2: values 2→89 across baseline + 3 cycles, incrementing on every internal reconnect attempt including refused ones. Public stability UNVERIFIED — not documented as a public/stable identifier; do not use for business identity (e.g. `controller_generation = futu_conn_id` is explicitly forbidden) |

#### F17 — Reconnect catch-up behavior (Wave 2 Closure R2)

**STATUS: VERIFIED — TESTED SCOPE.**

In the tested `HK.00700` K_1M/QUOTE reconnect scenario, SDK autonomous reconnect/resubscribe resumed at current/future provider progress rather than replaying the missed interval sequence, across 3 consecutive, independent cycles:

| Cycle | Pre-loss K_1M | First post-recovery K_1M | Missed interval | Future progression observed |
|---|---|---|---|---|
| 1 | 09:45 | 09:47 | 09:46 — never appeared anywhere in the run | 09:47 → 09:48 → 09:49 |
| 2 | 09:49 | 09:51 | 09:50 — never appeared anywhere in the run | 09:51 → 09:52 → 09:53 |
| 3 | 09:53 | 09:55 | 09:54 — never appeared anywhere in the run | 09:55 → 09:56 → 09:57 |

Evidence: `runs/2026-09-09T01-43-02-875121Z/lifecycle.jsonl` + `derived/r2_classification.json`. Classification per cycle: `DIRECT_CURRENT_ONLY`. Post-recovery K_1M payloads were confirmed non-duplicate of the pre-fault payload (distinct hashes) in every cycle.

**Scope limits — do not generalize beyond:** one symbol (`HK.00700`), one HK active morning session, one SDK version (10.08.6808), one OpenD version (`1010`), ~170s outages only, 3 cycles. This does **not** establish "Futu never replays missed bars" — it establishes that this specific tested scenario did not replay, 3/3 times.

#### F18 — Replay/backfill distinguishability (Wave 2 Closure R2)

**STATUS: VERIFIED_NEGATIVE_OBSERVATION — within the inspected SDK/payload surface.**

Conclusion: `NO_AUTHORITATIVE_REPLAY_MARKER_OBSERVED`. The R2 run inspected 274 QUOTE callbacks and 253 K_1M callbacks; no field anywhere in either raw payload schema is shaped like a replay flag, historical marker, sequence/cursor, push subtype, delivery-type marker, or backfill/catch-up marker.

Wording discipline: this means *no authoritative replay marker was observed in the inspected SDK/payload surface for the tested QUOTE/K_1M stream behavior* — it does **not** mean "Futu has no replay marker" as a universal claim about the provider or SDK.

**Implementation consequence:** a future controller/adapter MUST NOT classify REALTIME vs. REPLAY vs. BACKFILL purely from burst timing, arrival clustering, old source timestamps, or callback-ordering heuristics. Where provenance cannot be proven from an authoritative field, classification must remain UNKNOWN/UNVERIFIED, not inferred from timing.

#### AUTO_RESUBSCRIBE — behavioral confirmation (Wave 2 Closure R2)

**STATUS: VERIFIED — TESTED SCOPE.**

Source evidence already showed `on_api_socket_reconnected()` → `_reconnect_subscribe()` (F-SDK-008/009). Wave 2 Closure R2 now confirms this **behaviorally**: across 3/3 reconnect cycles, with NO manual `subscribe()` call issued after `restore()`, both QUOTE and K_1M push flow resumed on their own.

Wording: "Futu SDK autonomous reconnect/resubscribe behaviorally restored the tested push subscriptions after transport recovery."

**Permanent caveat, not to be collapsed:** SDK auto-resubscribe success != LiveFeed recovery != LIVE qualification. This evidence confirms the SDK-level mechanism works; it says nothing about whether a future controller should treat that as sufficient for its own Currentness/Continuity/LIVE qualification (per the frozen Live Feed Reliability V0.1 contract, it explicitly should not, on its own).

#### F15 — Cross-reconnect ProgressIdentity (Wave 2 Closure R2)

**STATUS: PARTIALLY_VERIFIED**, split into three separately-scoped findings:

1. **Transport-vs-context identity — VERIFIED.** One Python `OpenQuoteContext` object persisted, unchanged, across the baseline and all 3 cut/restore cycles (constant `id()`), while the proxy recorded 4 distinct TCP-level connections and the SDK's internal `conn_id` counter incremented throughout. Conclusion: `OpenQuoteContext` object identity != underlying transport incarnation. Implementation consequence: Python object identity MUST NOT be used to define LiveFeed connection generation.
2. **K_1M cross-reconnect ordering — VERIFIED, TESTED SCOPE.** `time_key` remained calendar/minute-anchored and strictly increasing across every reconnect boundary observed (44,45 → 47,48,49; 49 → 51,52,53; 53 → 55,56,57), with no reset, reuse, or connection-local-sequence behavior. Wording discipline: "`K_1M time_key` remained cross-reconnect comparable under the tested HK semantics" — not "inherently globally comparable." Implementation consequence: for tested HK K_1M semantics, normalized semantic interval identity may serve as a cross-reconnect progress comparator without relying on SDK `conn_id`.
3. **QUOTE cross-reconnect ProgressIdentity — UNRESOLVED / INSUFFICIENT.** `data_time` remained second-resolution with no new sequence/cursor field appearing post-reconnect in any of the 3 cycles, but this was not independently stress-tested beyond confirming that absence. The existing facts stand: `data_time` second-resolution, multiple material updates may share `data_time`, no provider sequence/cursor observed. QUOTE `data_time` alone MUST NOT become a manufactured unique ProgressIdentity.

Evidence: `runs/2026-09-09T01-43-02-875121Z/lifecycle.jsonl` + `derived/r2_classification.json` (`f15_connection_identity_evidence`).

### BLOCKING

| Claim | Confidence | Evidence |
|---|---|---|
| Synchronous unreachable `OpenQuoteContext` construction failed to return within bounded test timeout | VERIFIED | `RAW_EMPIRICAL` — original ~39-minute in-process hang, then a clean, isolated, reproducible 15s-timeout confirmation (`runs/.../8-35-00.../` F34 formal capture) |
| Source shows unbounded reconnect loop for this path | SOURCE_VERIFIED | F-SDK-002 |
| `query_subscription` during transport recovery demonstrated unbounded caller blocking in the observed usage pattern | VERIFIED | `RAW_EMPIRICAL` — the Wave 2 R1 incident (~19-minute self-inflicted block); root-caused to calling a synchronous RPC while `TRANSPORT_CUT` and before `restore()` |
| Do NOT generalize this automatically to every SDK method | (methodological note, not a claim) | — |
| Treat untested synchronous methods as blocking-risk until tested | (methodological note) | see `derived/sync_api_risk_inventory.json`: 123 public methods share the exact same synchronous dispatch mechanism as `query_subscription` (`LIKELY_BLOCKING_RISK`); 8 do not match that pattern in a static scan (`UNRESOLVED`) |

### ENTITLEMENT

| Claim | Confidence | Evidence |
|---|---|---|
| Entitlement differs by access path | VERIFIED | `RAW_EMPIRICAL` — `get_stock_quote` (pull) denied for both `US.AAPL` and `HK.00700` ("upgrade to Basic package") while `subscribe()`+push delivered continuous live HK data in the same session. `runs/2026-09-08T07-12-58-464339Z/sdk_calls.jsonl` |
| Pull entitlement cannot be generalized to push entitlement | VERIFIED | same |
| `get_delay_statistics` is latency instrumentation, not `DeliveryMode` evidence | VERIFIED | `BOTH` — corrected call returns real `REQ_REPLY` latency records (`proto_id, count, total_cost_avg, open_d_cost_avg, net_delay_avg, is_local_reply`), none entitlement-shaped; `QOT_PUSH` type structurally empty even with live traffic |
| Successful push does NOT prove REALTIME `DeliveryMode` | VERIFIED (methodological) | no field anywhere in any captured payload names or implies delivery mode |
| `DeliveryMode` remains UNKNOWN until authoritative evidence exists | UNRESOLVED (explicitly, by design) | — |

### IDENTITY / ORDERING

| Claim | Confidence | Evidence |
|---|---|---|
| One exact-duplicate QUOTE payload was observed (within a single run) | VERIFIED | `RAW_EMPIRICAL` — `HK.00700` QUOTE, `data_time=16:01:06`, identical full-payload hash, count=2 |
| A second exact-duplicate payload appears **across two separate runs** | VERIFIED, and explained | `RAW_EMPIRICAL` — `data_time=16:08:30`, identical hash, appearing once in each of two runs; consistent with querying an already-closed, unchanging market twice, not a harness artifact. `derived/wave1_wave2_offline_analysis.json` |
| Zero out-of-order source-time inversions observed in the tested sample | VERIFIED (sample-scoped) | `RAW_EMPIRICAL` — 1,722 QUOTE + 1,460 K_1M callbacks, 0 inversions |
| This is NOT an ordering guarantee | (methodological note) | single symbol, single session |
| No provider sequence/cursor field observed in tested QUOTE/K_1M payloads | VERIFIED | `RAW_EMPIRICAL` — full raw key inventory (69 keys) contains nothing sequence/serial/cursor/packet/request/update/version-shaped, reconfirmed across all runs including post-outage |

### THREADING

| Claim | Confidence | Evidence |
|---|---|---|
| Multi-threaded callback delivery observed | VERIFIED | `RAW_EMPIRICAL` — `derived/wave1_wave2_offline_analysis.json` callback thread map: 5 distinct thread IDs deliver `DATA_CALLBACK` across all runs, but QUOTE and K_1M always share the *same* thread within any one run |
| Disconnect callback uses a distinct SDK thread | VERIFIED | `RAW_EMPIRICAL` — `on_disconnect` thread differs from the data-callback thread(s) in the same run |
| REENTRANCY not observed | VERIFIED (absence, weaker claim) | no overlapping/reentrant invocation of the same callback was demonstrated anywhere |
| Multi-threaded != reentrant | (methodological note) | — |

### SYMBOL IDENTITY

| Claim | Confidence | Evidence |
|---|---|---|
| Tested HK non-canonical `HK.700` rejected | VERIFIED | `RAW_EMPIRICAL` — `get_market_snapshot(["HK.700"])` → `ret=-1`, "未知股票 700" |
| Canonical `HK.00700` accepted/echoed | VERIFIED | `RAW_EMPIRICAL` — every successful call echoes `code="HK.00700"` exactly as requested |

## 3. PARTIALLY VERIFIED FACTS

- **`time_key` = interval-end** (temporal table above): tight, internally consistent, but n=8 transitions, one symbol, one session. A second HK session and at least one non-HK market would raise this toward VERIFIED.
- **QUOTE `data_time` timezone semantics**: SDK docstring explicitly documents Beijing time (HK/A-share) / US Eastern (US) — SOURCE_VERIFIED as *documentation*, but not independently cross-checked against an external authoritative clock/exchange feed in this pack.
- **`query_subscription`'s blocking-during-outage behavior generalizing to the other 123 `LIKELY_BLOCKING_RISK` methods**: source-pattern-verified for the *mechanism* they share, but each individual method's actual blocking behavior was only directly tested for `query_subscription` itself and the constructor.
- **Unsubscribe minimum-hold semantic**: see dedicated section below — PARTIALLY_VERIFIED at best.

## 4. UNRESOLVED (P0)

- **F04** — authoritative `DeliveryMode` evidence (realtime vs. delayed). No field found anywhere that names or implies this. Remains the sole open provider-semantic P0 after Wave 2 closure. Default: `DeliveryMode.UNKNOWN`. No successful subscribe, no continuous callbacks, no fresh timestamps, and no source-time behavior may establish REALTIME.
- **Provider/cloud-side subscription persistence** (surviving something stronger than a client context swap, e.g. an OpenD restart). Never tested — OpenD restart was never authorized in any round.
- **QUOTE cross-reconnect ProgressIdentity** (carried forward from F15, see the F15 subsection above) — the K_1M half of F15 closed VERIFIED (tested scope); the QUOTE half remains UNRESOLVED/INSUFFICIENT.

**Resolved this closure pass (Wave 2 Closure R2, active-session, 3 completed reconnect cycles on `HK.00700`):**
- **F17** — reconnect catch-up behavior: VERIFIED — TESTED SCOPE (see RECONNECT/TRANSPORT subsection above).
- **F18** — replay/backfill distinguishability: VERIFIED_NEGATIVE_OBSERVATION — within inspected payload surface (see RECONNECT/TRANSPORT subsection above).
- **Auto-resubscribe behavioral confirmation**: VERIFIED — TESTED SCOPE (see RECONNECT/TRANSPORT subsection above).
- **F15 (transport-vs-context identity, K_1M half)**: VERIFIED. (QUOTE half remains open, listed above.)

## 5. CARRIED-FORWARD NON-BLOCKING ITEMS

- **F09** — completed zero-trade-minute semantics. Every zero-volume push observed so far is explained as a pre-boundary placeholder, not a completed silent minute; a genuinely completed zero-trade minute has never been captured.
- **F10** — low-liquidity silence semantics. No low-liquidity symbol was ever configured for a live run (by design — the harness refuses to guess one).
- **F12** — true post-period correction semantics. Every same-`time_key` OHLCV change observed is consistent with an ordinary forming-bar update; no case of an already-superseded/completed interval changing afterward has been seen.
- **Unsubscribe minimum-hold semantics** — see below; remains PARTIALLY_VERIFIED/UNRESOLVED.

### Unsubscribe minimum-hold semantic (dedicated)

**Empirical evidence:** In one 5-repetition test, 4/5 `unsubscribe()` calls issued ~3 seconds after `subscribe()` returned `ret=-1` with raw error text (as captured, with a known encoding artifact from the original terminal capture):
`'HK.00700并Basic实时时长限制，至少需要保持1分钟'` (best-effort reconstruction — approximately "HK.00700's Basic real-time duration restriction requires holding for at least 1 minute"). The one repetition where enough wall-clock time had actually elapsed succeeded (`ret=0`).

**Source evidence:** `OpenQuoteContext.unsubscribe()`'s client-side implementation (F-SDK-010) contains **no timing, cooldown, or rate-limit logic of any kind** — it validates parameters locally, updates a local subscription record, and sends the request to OpenD via the same synchronous dispatch machinery as every other request-style call. `_check_subscribe_param` (F-SDK-011) is likewise pure syntactic validation. No docstring, comment, or constant anywhere in the installed `futu` 10.08.6808 source mentions a one-minute (or any) unsubscribe cooldown, minimum hold time, or rate limit.

**Adjudication:**
- **SOURCE_VERIFIED**: the rule, if real, is **not implemented client-side** in this SDK version — the error text is necessarily server-generated (OpenD-side), passed through verbatim by the client.
- **PARTIALLY_VERIFIED**: that a minimum-hold rule of approximately one minute exists at all (based on one observed error string and consistent-with-one-minute timing across 4 failing + 1 succeeding repetition) — this is **not VERIFIED** merely because the observed timing looked like a minute; OpenD's actual server-side logic was never independently inspected (it is closed-source from this vantage point).
- **UNRESOLVED**: exact scope (per-symbol? per-subtype? whole-request? account/connection quota?) and exact timing value. The one observed error string names the specific symbol (`HK.00700`) and mentions "Basic" (a package/entitlement tier name), suggesting the rule may be tied to the Basic real-time package specifically rather than being a blanket API rate limit — but this is inference from one string, not confirmed.

**Conclusion:** Treat as an OpenD/server-side restriction of approximately one minute, scoped at least to symbol+package-tier, until a controlled multi-symbol/multi-timing experiment (out of scope for this offline pack) narrows it further.

## 6. PRODUCTION CONSEQUENCES (documentation only — no implementation here)

- `query_subscription` cannot be authoritative LIVE truth (control-plane visibility ≠ data-plane push, demonstrated directly).
- `unsubscribe` ACK cannot establish a clean subscription-incarnation barrier (a successful return does not guarantee no further callbacks for that stream).
- Data-plane liveness must remain a separate signal from control-plane state (both facts above force this).
- A provider transport reconnect must not self-promote a system to "LIVE" — this is no longer merely a source-level inference: Wave 2 Closure R2 behaviorally confirmed (3/3 tested cycles) that auto-resubscribe issues a *fresh* subscribe and resumes at current/future progress, carrying no missed-interval information (`DIRECT_CURRENT_ONLY`, no replay observed).
- A future controller's connection-generation identity must not be derived from Python `OpenQuoteContext` object identity (confirmed to survive multiple distinct transport incarnations) or from the SDK's internal `conn_id` counter (diagnostic-only, public stability unverified).
- For tested HK K_1M semantics, `time_key` may serve as a cross-reconnect progress comparator (calendar-anchored, not connection-local) — this does not extend to QUOTE `data_time`, whose cross-reconnect ProgressIdentity remains unresolved.
- Futu SDK's autonomous, unconditional, uncapped, no-backoff reconnect is a provider-specific constraint any consuming design must account for explicitly, not assume away.
- An authoritative writer/controller path must not execute potentially-unbounded blocking Futu SDK operations on its own thread — 2 of ~132 public methods are *known* to block unboundedly under realistic failure conditions, and 123 more share the identical synchronous mechanism untested.
- K_1M `time_key` may be a ProgressIdentity *candidate* but is not bar-completeness evidence (no completeness flag exists in the payload at all).
- QUOTE `data_time` alone is insufficient ProgressIdentity (second-resolution, many-to-one with real price changes).
- `DeliveryMode` must remain UNKNOWN without further entitlement evidence — do not default to REALTIME or DELAYED.
- Single-writer ingress is required because SDK callback delivery is demonstrably multi-threaded (5 distinct callback threads observed across runs).

## 7. TRUST BOUNDARIES

Every fact above is scoped strictly to:
- **SDK version** `futu` 10.08.6808
- **OpenD version** `server_ver="1010"`
- **Market** HK regular session (all live evidence)
- **Symbol** `HK.00700` primarily (`HK.09988`, `US.AAPL` used only for narrow negative/entitlement probes)
- **Session** the specific calendar dates/times this pack's runs occurred
- **Account entitlement** whatever this specific account currently holds (Basic-tier restrictions observed; no other tier tested)

**Do not extrapolate** any of the above to: future SDK versions, other markets (US/CN/others were only probed for entitlement denial, never for live push behavior), other entitlement tiers, or other stream types (order book, tickers, RT data were never tested).

## 8. EVIDENCE INDEX

| Claim area | Run directory | Raw file | Event range/marker | Derived artifact | Evidence class |
|---|---|---|---|---|---|
| F01 QUOTE resolution | `...T06-32-20...` | `events.jsonl` | all QUOTE push events | `derived/r1_f02_f28_transition_analysis.json` | RAW_EMPIRICAL |
| F02/F28 transition edge | `...T06-32-20...` | `events.jsonl` | K_1M pushes | `derived/r1_f02_f28_transition_analysis.json` | RAW_EMPIRICAL |
| F04 entitlement | `...T07-12-58...` | `sdk_calls.jsonl` | `get_stock_quote`, `get_delay_statistics` calls | — | RAW_EMPIRICAL |
| F06 clean mixed-batch | `...T07-12-58...` | `sdk_calls.jsonl` | pre/post `query_subscription` | — | RAW_EMPIRICAL |
| F22/F23 unsubscribe/barrier | `...T07-28-29...` | `lifecycle.jsonl` | seq 6–140 | `derived/wave2_r1_opportunistic_analysis.json` | RAW_EMPIRICAL |
| F21 boundary B | `...T07-28-29...` | `lifecycle.jsonl` | seq 141–150 | — | RAW_EMPIRICAL |
| F19 genuine transport loss | `...T08-35-00...` | `lifecycle.jsonl` | seq 11, 16–214 | — | RAW_EMPIRICAL |
| SDK reconnect ownership | `...T08-35-00...` | — | — | `derived/sdk_source_inspection.json`, `derived/source_inspection_offline_v1.json` | SOURCE_INSPECTION |
| F34 formal capture | `...T08-35-00...` | `lifecycle.jsonl` | `PROVIDER_EVENT` w/ `f34_formal_capture` | — | RAW_EMPIRICAL |
| Unsubscribe min-hold | `...T07-28-29...` | `lifecycle.jsonl` | `UNSUBSCRIBE_CALL_RETURN` reps 0–4 | — | BOTH (see section 5) |
| Sync API risk inventory | — | — | — | `derived/sync_api_risk_inventory.json` | SOURCE_INSPECTION |
| Callback threading / duplicates (cross-run) | all runs | `events.jsonl`/`lifecycle.jsonl` | — | `derived/wave1_wave2_offline_analysis.json` | RAW_EMPIRICAL |
| F17 reconnect catch-up (3 cycles) | `...T01-43-02...` | `lifecycle.jsonl` | `BASELINE_CHECKPOINT` phase=cycle_summary, all 3 cycles | `derived/r2_classification.json` | RAW_EMPIRICAL |
| F18 replay marker payload-surface scan | `...T01-43-02...` | `lifecycle.jsonl` | all `DATA_CALLBACK` events (274 QUOTE + 253 K_1M) | `derived/r2_classification.json` (`f18_payload_schema_inspection`) | RAW_EMPIRICAL |
| AUTO_RESUBSCRIBE behavioral confirmation | `...T01-43-02...` | `lifecycle.jsonl` | `PROVIDER_EVENT` `on_api_socket_reconnected`, all 3 cycles | — | RAW_EMPIRICAL |
| F15 transport-vs-context identity + K_1M ordering | `...T01-43-02...` | `lifecycle.jsonl` | `CONNECTION_ERROR` conn_id sequence, `CONTEXT_CREATE_OK` python_ctx_object_id | `derived/r2_classification.json` (`f15_connection_identity_evidence`) | RAW_EMPIRICAL |
| R2 raw hash verification | `...T01-43-02...` | `lifecycle.jsonl`, `metadata.json`, `observations.json` | — | `derived/raw_hashes.json` | RAW_EMPIRICAL |

Raw evidence is never copied into this document — every claim above points back to a specific run/file/artifact. Consult the referenced files for full, unmodified raw records.
