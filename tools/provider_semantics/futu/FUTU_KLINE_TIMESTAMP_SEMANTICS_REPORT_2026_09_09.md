<!-- Evidence-only report. No production semantics are inferred from Stock Razor code. -->
# FUTU KLINE TIMESTAMP SEMANTICS REPORT

Date: 2026-09-09  
Status: P0 PROVIDER-EVIDENCE REPORT  
Scope: Futu OpenAPI / Python SDK semantics required before realtime_monitor 15m/1h currentness rules may be frozen.

## CURRENT AUTHORITATIVE STATUS

**Provider evidence track:** US K_15M/K_60M provider timestamp identity is now `VERIFIED_IN_TESTED_US_RTH_HISTORY_SCOPE` (BAR_END) for the tested `request_history_kline` path only -- see "US RTH empirical closure (2026-09-09)" below. This does **not** extend to the 16:00 final bar, half-day construction, pre-market/after-hours alignment, `extended_time=True` behavior, streaming push forming-bar behavior, or any API surface other than `request_history_kline`; those remain `UNKNOWN` / `PARTIALLY_VERIFIED` exactly as before (see "Remaining unverified areas").
**Evidence-tooling track:** bounded live capture, per-RPC snapshot/history capture, and offline mechanical analyzer are implemented; exact-head CI must be checked after every change.
**Production Currentness track:** **BLOCKED**. No threshold or expected-bar completion rule is authorized. Closing the tested-RTH-history unknown does not by itself unblock production: the remaining gaps listed below are still open, and this report does not decide promotion -- Control Tower owns that decision.

> **Historical record (superseded by the empirical closure below, kept for audit trail, not deleted):** as of 2026-09-09 (pre-empirical-closure), this report stated: "required US K_15M/K_60M semantics remain `UNKNOWN` / `PARTIALLY_VERIFIED` by fact." That statement was accurate at the time it was written and remains true for every scope the new observation did not cover (see "Remaining unverified areas"). It is superseded, within the tested US RTH `request_history_kline` scope only, by the empirical closure recorded below.

Official Futu documentation and SDK schema describe `time_key` only as `Time` / `Candlestick time`; they do **not** define whether K_15M or K_60M timestamps are bar-start boundaries, bar-end boundaries, or another provider-defined identity. They also do not define the US K_60M 09:30-anchor vs clock-hour-anchor rule, forming-bar completion semantics, or half-day bucket truncation. **This remains true after the new empirical evidence below** -- the official-documentation gap and the empirical-observation conclusion are two separate evidence tracks and must not be conflated; the new BAR_END conclusion comes from controlled observation, not from official documentation newly discriminating the two candidates.

Existing Stock Razor controlled empirical evidence establishes interval-end-like identity only for tested **HK K_1M**, and (as of this update) BAR_END for tested **US K_15M/K_60M `request_history_kline`, RTH session, 2026-09-09**. Neither scope may be generalized beyond what was actually observed.

**Do not invent a currentness threshold.**

## Evidence sources

Official Futu OpenAPI v10.10 documentation:

1. Get Real-time Candlestick — https://openapi.futunn.com/futu-api-doc/en/quote/get-kl.html
2. Get Historical Candlesticks — https://openapi.futunn.com/futu-api-doc/en/quote/request-history-kline.html
3. Real-time Candlestick Callback — https://openapi.futunn.com/futu-api-doc/en/quote/update-kl.html
4. Quote definitions / `KLType`, `Session`, `TradeDateType` — https://openapi.futunn.com/futu-api-doc/quote/quote.html
5. Trading Calendar — https://openapi.futunn.com/futu-api-doc/en/quote/request-trading-days.html
6. Official Python SDK source — `FutunnOpen/py-futu-api`

Existing controlled Stock Razor evidence:

- `tools/provider_semantics/futu/FUTU_SEMANTIC_CONTRACT_V0_1.md`
- tested SDK: `futu 10.08.6808`; observed OpenD server version `1010`.
- HK K_1M controlled observations show repeated same-key updates, no explicit complete flag, and timing strongly supporting interval-end identity within that tested HK scope only.

Official exchange-calendar evidence may be used only to select a known early-close date for provider observation; it does **not** define Futu K-line construction. NYSE officially documented **2025-11-28** as a 1:00 p.m. Eastern early close (day after Thanksgiving), making it a suitable completed historical half-day for read-only Futu history inspection.

## Fact matrix

| Required fact | Status | Evidence | Current implication |
|---|---|---|---|
| US `time_key` timezone = US Eastern by default | VERIFIED | Futu official K-line docs | Timezone normalization may use documented ET semantics while raw provider string remains preserved |
| K_15M `time_key` = bar start | REJECTED_IN_TESTED_US_RTH_HISTORY_SCOPE | 2026-09-09 US RTH `request_history_kline` observation (QQQ, NVDA) -- see empirical closure below | Bar-start completion rule is not supported by tested-scope evidence; still UNKNOWN outside that scope |
| K_15M `time_key` = bar end | VERIFIED_IN_TESTED_US_RTH_HISTORY_SCOPE | Same | Within tested scope only, a completed K_15M row's `time_key` marks interval end; does not by itself authorize a production threshold (see Governance result) |
| K_60M `time_key` = bar start | REJECTED_IN_TESTED_US_RTH_HISTORY_SCOPE | 2026-09-09 US RTH `request_history_kline` observation (QQQ, NVDA) -- see empirical closure below | Same caveat as K_15M bar-start row |
| K_60M `time_key` = bar end | VERIFIED_IN_TESTED_US_RTH_HISTORY_SCOPE | Same | Same caveat as K_15M bar-end row |
| US K_60M 09:30 anchor | VERIFIED_IN_TESTED_US_RTH_HISTORY_SCOPE (first completed bar labeled 10:30, OHLCV = aggregation of the four 15m bars over [09:30,10:30)) | Same 2026-09-09 observation | 09:30-anchored grid is supported for the tested first-hour RTH bucket only; clock-hour-anchor candidate is rejected for that same tested bucket; not yet observed across a full session or across half-days |
| US K_60M clock-hour anchor | REJECTED_IN_TESTED_US_RTH_HISTORY_SCOPE (for the tested first-hour bucket) | Same | See preceding row |
| K_15M forming-row mutation | UNKNOWN pending direct forming-row mutation observation | This closure observed completed bars only (forming/current bar was not returned by `request_history_kline`); it did not itself capture a same-key mutation | Latest K_15M row still cannot be presumed complete purely from this evidence; see "completed-bars-only" note below |
| K_60M forming-row mutation | UNKNOWN pending direct forming-row mutation observation | Same | Same |
| `request_history_kline` exposes currently forming intraday row | REJECTED_IN_TESTED_US_RTH_SCOPE for `request_history_kline` specifically (the forming/current bar was NOT returned in either K_15M or K_60M observation) | 2026-09-09 observation | Within tested scope, same-day `request_history_kline` history is completed-bars-only; other API surfaces (`get_cur_kline`, streaming push) are untested and remain UNKNOWN |
| Documented KLine surface has explicit closed/completed flag | VERIFIED NEGATIVE OBSERVATION | No such documented field; K_1M controlled raw payload also had none | Completion cannot be read from a provider completion flag on this surface |
| Standard historical request is non-extended by default | VERIFIED | Futu official docs | RTH and extended-hours evidence stay separate |
| Extended-hours K-lines <=60m can be requested explicitly | VERIFIED | Futu official docs | Extended-hours currentness requires separate session modeling |
| Half-day existence / early close can be known externally | VERIFIED at exchange-calendar layer | exchange calendar | Does not define Futu final bar identity |
| Half-day K_15M/K_60M truncation/alignment | UNKNOWN | Requires Futu provider observation | Do not truncate normal-day cadence by assumption |
| Futu trading calendar fully captures temporary market closures | VERIFIED NEGATIVE | official docs say temporary closures are not removed | Calendar alone cannot prove progress expected |

## US RTH empirical closure (2026-09-09)

**Observation date/session:** 2026-09-09, US regular trading hours (RTH).
**Symbols:** QQQ, NVDA.
**API path:** `request_history_kline` (read-only), OpenD `127.0.0.1:11111`.
**Method:** controlled observation via the executable closure pack below (bounded, read-only history requests; no synchronous call mixed into any live/blocking path).

**K_15M boundary observations:**

- the forming/current (in-progress) bar was NOT returned by `request_history_kline`.
- completed bars first appeared just after each 15-minute interval boundary.
- observed labels: `09:45`, `10:00`, `10:15`, `10:30`, `10:45`.
- the first bar labeled `09:45` contains the `09:30`-`09:45` session interval.
- bars remained unchanged after publication; no same-`time_key` mutation was observed across repeated observation.

**K_15M conclusion:** `BAR_END`. **Confidence: HIGH** (within tested scope only -- see below).

**K_60M boundary observations:**

- the forming/current 60m bar was NOT returned by `request_history_kline`.
- the first completed US RTH bar appeared at approximately 10:30 ET, labeled `10:30:00`.
- its `open` equals the `09:30` session open.
- its OHLCV matches the aggregation of the four K_15M bars over `[09:30, 10:30)`.
- no same-`time_key` mutation was observed after publication.

**K_60M conclusion:** `BAR_END`, with the tested first-hour RTH bucket consistent with a `09:30`-anchored grid (label minute `:30`) and inconsistent with a clock-hour-anchored grid (which the report's own discriminating criteria, above, associate with label minute `:00`). **Confidence: HIGH** for the tested bucket; the 09:30-anchor conclusion has so far been observed for **only the first RTH 60m bucket** -- full-session grid stability (later buckets, and the session's final bucket) has not yet been separately confirmed and is listed below as a remaining gap.

**Completed-bars-only behavior:** confirmed for `request_history_kline`, US RTH, K_15M and K_60M, on the tested date/symbols: the forming/current bar is never returned; every bar returned by this call, for this scope, was already complete at observation time.

**Provider timestamp observation:** `time_key` aligns to US Eastern wall-clock session boundaries. The payload itself is timezone-naive (no explicit offset/zone marker in the raw value); this observation does not upgrade that to a stronger official timezone guarantee than the evidence supports -- it is a controlled empirical reading, not a documented provider contract.

**Evidence separation (kept explicit, not conflated):**

- *Official documentation* remains insufficient to prove bar-start/bar-end semantics for K_15M/K_60M -- unchanged by this update, see "CURRENT AUTHORITATIVE STATUS" and the fact-matrix rows citing "Official docs do not say" / "No official bucket-alignment contract" elsewhere in this report.
- *Empirical observation* (this section) supports `BAR_END` for the tested US RTH `request_history_kline` K_15M/K_60M path specifically. This report does not claim the official docs say `BAR_END`, and does not generalize this conclusion beyond the scope actually observed.

## Executable controlled empirical closure pack

All tools below are evidence-only and are not imported by production code.

### A. `kline_timestamp_probe.py` — bounded live callback capture

Purpose: capture raw US K_15M/K_60M transitions without mixing blocking synchronous snapshot RPCs into the live path.

- direct Futu SDK / local OpenD only;
- explicit `Session.RTH`, `ETH`, or `ALL`;
- raw callback payload + UTC receive time + monotonic receive time;
- parent-owned hard deadline;
- timeout => incomplete evidence, not semantic promotion.

Example:

```bash
cd tools/provider_semantics/futu
python kline_timestamp_probe.py \
  --host 127.0.0.1 --port 11111 \
  --symbol US.AAPL --session RTH --duration 4200
```

### B. `kline_snapshot_probe.py` — independently bounded synchronous observations

Each `get_cur_kline` or `request_history_kline` observation executes in its **own child process** with an independent hard timeout. One blocked Futu call therefore invalidates one observation rather than destroying the entire evidence run.

The probe now deliberately separates historical-date evidence from current/live evidence:

- `--operations history|current|both`
- `--history-trade-date YYYY-MM-DD`

This prevents an old half-day history sample from being silently mixed with today's current K-line sample under one implied trading-date assumption.

Normal active-session forming-bar comparison:

```bash
python kline_snapshot_probe.py \
  --host 127.0.0.1 --port 11111 \
  --symbol US.AAPL --session RTH \
  --operations both \
  --repeat 3 --repeat-delay 120 --rpc-timeout 30
```

Historical half-day-only capture:

```bash
python kline_snapshot_probe.py \
  --host 127.0.0.1 --port 11111 \
  --symbol US.AAPL --session RTH \
  --operations history \
  --history-trade-date 2025-11-28 \
  --repeat 1 --rpc-timeout 30
```

### C. `analyze_kline_timestamp_semantics.py` — offline mechanical analyzer

The analyzer performs **no automatic VERIFIED promotion**. It reports observations that allow competing hypotheses to be adjudicated later:

- first callback minus provider `time_key`;
- first callback minus candidate interval start if key is interpreted as interval end;
- K_60M minute residue compatible with `:30` vs `:00` candidate grids;
- repeated material mutation under one `time_key`;
- repeated same-key mutation across history/current snapshots;
- full per-sample historical time-key sequence;
- first/last time key;
- consecutive key gaps;
- nominal vs non-nominal gaps, including a potentially shortened half-day final interval.

A non-nominal final gap is **reported, not normalized away**. The analyzer must not decide that it is valid, invalid, complete, or incomplete without provider evidence and review.

## Minimum discriminating evidence required

### K_15M start vs end

Across multiple transitions:

- START candidate: first callback for a key clusters near the key wall-clock itself.
- END candidate: first callback clusters near `time_key - 15 minutes`.

Evidence that does not discriminate the candidates remains UNKNOWN/PARTIALLY_VERIFIED.

### K_60M start vs end + RTH grid

Observe multiple transitions, preferably including first and last RTH buckets:

- all key minutes `:30` are mechanically compatible with a 09:30-anchored candidate grid;
- all key minutes `:00` are mechanically compatible with a clock-hour candidate grid;
- callback timing relative to key distinguishes start-like vs end-like behavior.

These remain empirical candidates, not provider contracts, until reviewed.

### Forming-bar behavior

Same `time_key` + repeated callbacks/snapshots + materially changing OHLCV/turnover before next key = direct forming-row evidence for that tested ktype/session scope.

A static row alone never proves completion.

### Historical API forming-row behavior

Repeated same-day history snapshots during an active, visibly forming interval are required. If the same latest history key mutates materially, that is discriminating evidence that history exposes the forming row in that tested scope.

### Half-day

Use a confirmed exchange early-close date and run **history-only** provider observation. Record the actual K_15M/K_60M sequence and final key. Possible outcomes must all remain open until observed: shortened final bucket, full nominal bucket identity, omitted partial bucket, or another provider convention.

### Extended hours

RTH and extended-session packs must be captured and classified separately. Do not combine them into one universal currentness rule.

## Mechanics validation

`tests/test_futu_kline_timestamp_semantics_tools.py` now covers, among other cases:

- 09:30-anchor vs clock-hour mechanical classification;
- start/end-candidate timing math;
- repeated same-key forming mutation candidates;
- historical same-key mutation candidates;
- timeout exclusion;
- SDK-free parsing of evidence tools;
- child-result recovery despite incidental SDK stdout noise;
- live capture separation from synchronous periodic snapshot calls;
- explicit history-only trade-date parsing;
- malformed trade-date rejection;
- preservation of full historical key sequence;
- non-nominal final-gap reporting without semantic normalization.

CI validates **tool mechanics only**. CI PASS does not upgrade provider semantics.

## Remaining unverified areas

These gaps are unaffected by the 2026-09-09 closure above and must remain explicit -- the closure narrows scope, it does not erase these, and they must not be silently declared solved:

- US `16:00` final-bar behavior (session close bucket construction, whether it is a full or truncated interval).
- Early-close / half-day K_15M construction.
- Early-close / half-day K_60M construction.
- Pre-market / after-hours alignment (RTH-only was tested; extended sessions are untested).
- `extended_time=True` behavior.
- Streaming push (`update_kl` / live callback) forming-bar behavior -- this closure tested `request_history_kline` only; the live/streaming surface is a separate, untested API path.
- Alternate API surfaces (e.g. `get_cur_kline`) beyond `request_history_kline`.
- K_60M grid stability beyond the tested first RTH bucket (later intraday 60m buckets and the session's final 60m bucket were not separately confirmed in this closure).
- Direct forming-row *mutation* evidence for US K_15M/K_60M (this closure establishes that `request_history_kline` does not return the forming bar at all for the tested scope, which is a different, narrower fact than observing a forming row change value across repeated snapshots -- the latter remains UNKNOWN for US K_15M/K_60M specifically, per the fact-matrix rows above).

## Governance result

> **The US RTH `request_history_kline` K_15M/K_60M bar-start-vs-bar-end unknown is now CLOSED (BAR_END, HIGH confidence, tested-scope-qualified) as of 2026-09-09. This report does NOT itself authorize freezing an authoritative K_15M/K_60M currentness timing rule: the remaining gaps listed above (16:00 final bar, half-day construction, extended hours, streaming forming-bar behavior, alternate API surfaces, full 60m grid stability) are still open, and any production Currentness threshold or completion rule remains unauthorized until those are separately closed or explicitly accepted as out of scope by whoever owns that decision.**

This report does not declare the Currentness timing contract frozen. That promotion decision belongs to Control Tower, not to this evidence track.

No production controller, adapter, Currentness, Continuity, RecoveryCandidate, strategy, AI, or trading code is changed by this evidence work.
