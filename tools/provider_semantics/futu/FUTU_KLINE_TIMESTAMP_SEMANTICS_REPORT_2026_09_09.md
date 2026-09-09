<!-- Evidence-only report. No production semantics are inferred from Stock Razor code. -->
# FUTU KLINE TIMESTAMP SEMANTICS REPORT

Date: 2026-09-09  
Status: P0 PROVIDER-EVIDENCE REPORT  
Scope: Futu OpenAPI / Python SDK semantics required before realtime_monitor 15m/1h currentness rules may be frozen.

## CURRENT AUTHORITATIVE STATUS

**Provider evidence track:** required US K_15M/K_60M semantics remain `UNKNOWN` / `PARTIALLY_VERIFIED` by fact.  
**Evidence-tooling track:** bounded live capture, per-RPC snapshot/history capture, and offline mechanical analyzer are implemented; exact-head CI must be checked after every change.  
**Production Currentness track:** **BLOCKED**. No threshold or expected-bar completion rule is authorized.

Official Futu documentation and SDK schema describe `time_key` only as `Time` / `Candlestick time`; they do **not** define whether K_15M or K_60M timestamps are bar-start boundaries, bar-end boundaries, or another provider-defined identity. They also do not define the US K_60M 09:30-anchor vs clock-hour-anchor rule, forming-bar completion semantics, or half-day bucket truncation.

Existing Stock Razor controlled empirical evidence establishes interval-end-like identity only for tested **HK K_1M**. That scope must not be generalized to US K_15M/K_60M.

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
| K_15M `time_key` = bar start | UNKNOWN | Official docs do not say | No completion rule from `time_key` |
| K_15M `time_key` = bar end | UNKNOWN | Same | Same |
| K_60M `time_key` = bar start | UNKNOWN | Same | Same |
| K_60M `time_key` = bar end | UNKNOWN | Same | Same |
| US K_60M 09:30 anchor | UNKNOWN | No official bucket-alignment contract | No expected 60m sequence may be frozen |
| US K_60M clock-hour anchor | UNKNOWN | Same | Same |
| K_15M forming-row mutation | UNKNOWN pending US observation | K_1M/HK cannot be generalized | Latest K_15M row cannot be presumed complete |
| K_60M forming-row mutation | UNKNOWN pending US observation | Same | Latest K_60M row cannot be presumed complete |
| `request_history_kline` exposes currently forming intraday row | UNKNOWN | Docs do not specify | Same-day history cannot be treated as completed-bars-only |
| Documented KLine surface has explicit closed/completed flag | VERIFIED NEGATIVE OBSERVATION | No such documented field; K_1M controlled raw payload also had none | Completion cannot be read from a provider completion flag on this surface |
| Standard historical request is non-extended by default | VERIFIED | Futu official docs | RTH and extended-hours evidence stay separate |
| Extended-hours K-lines <=60m can be requested explicitly | VERIFIED | Futu official docs | Extended-hours currentness requires separate session modeling |
| Half-day existence / early close can be known externally | VERIFIED at exchange-calendar layer | exchange calendar | Does not define Futu final bar identity |
| Half-day K_15M/K_60M truncation/alignment | UNKNOWN | Requires Futu provider observation | Do not truncate normal-day cadence by assumption |
| Futu trading calendar fully captures temporary market closures | VERIFIED NEGATIVE | official docs say temporary closures are not removed | Calendar alone cannot prove progress expected |

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

## Governance result

> **BLOCK freeze of authoritative K_15M/K_60M currentness timing rules until controlled US K_15M/K_60M provider observation closes the required semantic unknowns.**

No production controller, adapter, Currentness, Continuity, RecoveryCandidate, strategy, AI, or trading code is changed by this evidence work.
