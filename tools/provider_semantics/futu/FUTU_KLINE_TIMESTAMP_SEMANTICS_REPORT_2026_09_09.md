<!-- Evidence-only report. No production semantics are inferred from Stock Razor code. -->
# FUTU KLINE TIMESTAMP SEMANTICS REPORT

Date: 2026-09-09
Status: P0 PROVIDER-EVIDENCE REPORT
Scope: Futu OpenAPI / Python SDK semantics relevant to realtime_monitor 15m/1h currentness.

## Executive conclusion

The official Futu documentation and SDK schema **do not define whether intraday `time_key` is a bar-start timestamp or a bar-end timestamp**. They describe it only as `Time` / `Candlestick time` / a timestamp string.

Existing Stock Razor controlled empirical evidence establishes interval-end-like identity only for **HK K_1M in the tested environment**. That evidence must not be generalized to K_15M, K_60M, or US session alignment.

Therefore the following facts remain insufficient to freeze authoritative 15m/1h currentness rules:

- K_15M start-vs-end timestamp semantics;
- K_60M start-vs-end timestamp semantics;
- US RTH K_60M bucket anchoring and expected sequence;
- K_15M/K_60M forming-bar behavior;
- historical K_15M/K_60M inclusion/exclusion of the currently forming bar;
- half-day K_15M/K_60M truncation/alignment behavior.

**Do not invent a currentness threshold or infer expected-bar completion from `time_key` alone.**

## Evidence sources

Official Futu OpenAPI v10.10 documentation:

1. Get Real-time Candlestick
   - https://openapi.futunn.com/futu-api-doc/en/quote/get-kl.html
   - `time_key`: `Time`, format `yyyy-MM-dd HH:mm:ss`; US market default timezone is US Eastern time.
2. Get Historical Candlesticks
   - https://openapi.futunn.com/futu-api-doc/en/quote/request-history-kline.html
   - `time_key`: `Candlestick time`; `extended_time=False` by default; `session` may select US quote sessions; pre/after/overnight historical K-line support is limited to 60 minutes and below.
3. Real-time Candlestick Callback
   - https://openapi.futunn.com/futu-api-doc/en/quote/update-kl.html
   - push payload carries `Qot_Common.KLine`; no documented bar-complete flag.
4. Quote definitions / `KLType`, `Session`, `TradeDateType`
   - https://openapi.futunn.com/futu-api-doc/quote/quote.html
   - K_15M and K_60M are defined as 15-minute and 60-minute candlestick types.
   - `Session`: RTH / ETH / ALL semantics for US quotes.
   - `TradeDateType`: WHOLE / MORNING / AFTERNOON.
5. Get Trading Calendar
   - https://openapi.futunn.com/futu-api-doc/en/quote/request-trading-days.html
   - exposes `trade_date_type`; temporary market closures are explicitly not removed from the returned trading-day calendar.
6. Quote FAQ market-state periods
   - https://openapi.futunn.com/futu-api-doc/en/qa/quote.html
   - documents market-state time periods, but does not document intraday candlestick bucket anchoring.
7. Official Python SDK protobuf schema (`Qot_Common.KLine`)
   - official Futu API documentation/Python SDK schema describes `KLine.time` only as a timestamp string; no start/end semantic tag and no explicit completed/closed flag.

Existing controlled Stock Razor evidence:

- `tools/provider_semantics/futu/FUTU_SEMANTIC_CONTRACT_V0_1.md`
- tested SDK: futu 10.08.6808; observed OpenD server version 1010.
- controlled observations cover HK QUOTE/K_1M, including repeated updates to the same K_1M `time_key`, no explicit complete flag, and transition timing strongly supporting K_1M interval-end identity within that tested HK scope.
- that contract explicitly forbids generalizing beyond the tested scope.

## Fact matrix

| Required fact | Status | Evidence | Conclusion |
|---|---|---|---|
| K_15M `time_key` means bar start | UNKNOWN | Official docs only say `Time` / `Candlestick time`. No start/end declaration. No controlled K_15M run in current evidence registry. | Cannot assert. |
| K_15M `time_key` means bar end | UNKNOWN | Same. Existing K_1M empirical end-boundary evidence is K_1M/HK-only. | Cannot assert. |
| K_60M `time_key` means bar start | UNKNOWN | Official docs only say `Time` / `Candlestick time`. No controlled K_60M run in current evidence registry. | Cannot assert. |
| K_60M `time_key` means bar end | UNKNOWN | Same. | Cannot assert. |
| US K_15M RTH bucket anchoring | UNKNOWN | Official docs define K_15M and US session selection but not bucket boundaries. | 09:30 vs clock-anchor cannot be inferred. |
| US K_60M RTH bucket anchoring | UNKNOWN | Official docs define K_60M and RTH but do not state 09:30-anchor or clock-hour anchor. | Expected 60m sequence remains unknown. |
| US regular trading session can be selected explicitly | VERIFIED | Official `Session.RTH` definition and historical/subscription session parameters. | Session scope can be explicit, but this does not define candle boundaries. |
| Standard historical request excludes US pre/after-hours by default | VERIFIED | `request_history_kline(... extended_time=False, session=Session.NONE)`; official docs state `extended_time` controls inclusion of pre/after-hours, and session can request non-regular data. | Default request must not be assumed to contain ETH data. |
| US pre/after/overnight K-lines supported at <=60m when requested | VERIFIED | Official historical K-line restrictions and Session support. | Extended-hours currentness must be session-aware. |
| Real-time K-line push may update a forming bar for K_1M | VERIFIED, TESTED SCOPE | Controlled HK K_1M evidence: repeated updates to same `time_key`, up to 38 pushes. | Current bar can be mutable for tested K_1M. |
| Real-time K-line push may update a forming bar for K_15M | UNKNOWN | No official complete flag and no controlled K_15M observation. | Do not generalize K_1M behavior without evidence. |
| Real-time K-line push may update a forming bar for K_60M | UNKNOWN | No controlled K_60M observation. | Do not generalize. |
| K-line payload contains explicit closed/completed flag | VERIFIED NEGATIVE for documented/common KLine surface; K_1M empirically VERIFIED NEGATIVE | Official KLine schema has no documented closed/completed field; controlled K_1M raw payload also had none. | Completion cannot be taken from a provider completion flag on this surface. |
| `get_cur_kline` includes the currently forming K_15M/K_60M bar | UNKNOWN | API is named/described as real-time candlestick retrieval but docs do not explicitly specify whether the newest returned row is forming or completed. | Must observe directly before relying on newest row as complete. |
| `request_history_kline` includes today's currently forming K_15M/K_60M bar | UNKNOWN | Historical API docs do not define forming-bar inclusion/exclusion for current trading day. | Historical API cannot be treated as completed-bars-only without observation. |
| first incomplete K_15M/K_60M bar behavior | UNKNOWN | No official statement / controlled evidence. | Do not derive currentness from first returned bar. |
| market-close K_15M/K_60M final-bar behavior | UNKNOWN | Official market states document close time, not K-line finalization/bucket timestamp. | Final-bar closure semantics unresolved. |
| half-day existence can be identified | VERIFIED | `TradeDateType.MORNING` / `AFTERNOON` / `WHOLE`. | Calendar can signal session shape. |
| half-day K_15M/K_60M alignment/truncation | UNKNOWN | Trading-calendar docs do not specify candle construction on half days. | Must not manufacture expected sequence from normal-day cadence. |
| temporary market close is fully represented by trading calendar | VERIFIED NEGATIVE | Futu explicitly says temporary market-closed data is not excluded by the trading calendar. | Calendar alone is insufficient currentness authority. |

## K_15M timestamp semantic

**Status: UNKNOWN.**

Futu defines K_15M as a 15-minute candlestick and exposes `time_key` as its timestamp/time. No official evidence located in the current documentation states whether that timestamp labels the opening boundary, closing boundary, or another provider-defined point.

The existing K_1M empirical result must not be promoted to K_15M by analogy.

## K_60M timestamp semantic

**Status: UNKNOWN.**

Futu defines K_60M as a 60-minute candlestick and exposes `time_key` as the candlestick time, but does not document start-vs-end semantics.

No controlled K_60M evidence exists in the current Stock Razor Futu evidence registry.

## Interval alignment — US regular trading hours

**Status: UNKNOWN for bucket anchoring.**

Official evidence verifies that US quote sessions are distinguishable (`RTH`, `ETH`, `ALL`) and that US timestamp strings use US Eastern time by default. It does **not** define whether K_60M regular-session bars are:

- 09:30–10:30, 10:30–11:30, ...;
- clock-hour anchored such as 10:00/11:00/...;
- or another provider-specific construction.

Therefore no authoritative expected K_60M sequence can be frozen yet.

The same caution applies to K_15M anchoring, although 15-minute boundaries may appear obvious mathematically. Provider construction must still be evidenced rather than inferred.

## Forming-bar behavior

### K_1M

**VERIFIED within existing HK controlled scope:** repeated push updates occur under one `time_key`; the payload has no explicit completed flag. `time_key` must not imply closure.

### K_15M / K_60M

**UNKNOWN.**

Official real-time K-line APIs and callback APIs are explicitly real-time, but the docs do not specify whether the newest K_15M/K_60M row is emitted immediately at interval start, only after first trade, continuously mutated while forming, or only published when complete.

No scope-safe empirical observation currently closes this question.

## Historical API and forming bar

**Status: UNKNOWN for K_15M/K_60M on the current trading day.**

`request_history_kline` is named a historical candlestick API, but the official docs do not state that a request ending on today's date excludes the currently forming intraday candle. Conversely, they do not state that it includes it.

Thus `request_history_kline` must **not** be treated as a completed-bars-only authority for currentness until this is empirically verified.

## Market close behavior

**Status: UNKNOWN for K_15M/K_60M finalization semantics.**

Futu documents market-state close times. It does not document whether the final intraday candle is shortened, what `time_key` it receives, exactly when it becomes immutable, or whether a final update is guaranteed at close.

## Half-day behavior

Two distinct facts must remain separate:

1. **VERIFIED:** Futu trading calendar can mark a trading date as `WHOLE`, `MORNING`, or `AFTERNOON`.
2. **UNKNOWN:** K_15M/K_60M construction and timestamping on those shortened sessions.

Additionally, Futu warns that temporary market closures are not removed from the trading calendar. Therefore `trade_date_type` is useful session-shape evidence but not sufficient proof that progress should currently be expected.

## Extended-hours behavior

**VERIFIED at session-selection level.**

- Standard historical call defaults to `extended_time=False`.
- US historical K-lines at 60 minutes and below can include pre-market, after-hours, and overnight data when the appropriate session is requested.
- Real-time subscription also exposes extended/session controls.

**UNKNOWN at bucket-alignment level.**

The official evidence located here does not establish the exact timestamp/bucket anchoring of pre-market, after-hours, or overnight K_15M/K_60M candles.

## Implications for currentness authority

The evidence supports the following hard constraints for realtime_monitor design:

1. **Do not interpret K_15M/K_60M `time_key` as bar start or bar end yet.**
2. **Do not freeze a US K_60M expected sequence yet.** In particular, do not assume either 09:30 anchoring or clock-hour anchoring.
3. **Do not treat the newest historical intraday row as necessarily completed.**
4. **Do not treat `time_key` change as a universal completion signal.** Existing K_1M evidence explicitly shows mutable forming-bar behavior and no completion flag.
5. **Currentness must be session-aware.** RTH vs ETH/ALL changes the set of legitimate progress intervals.
6. **Half days must be calendar/session-shape aware.** Normal-day expected cadence cannot simply be truncated by assumption.
7. **Trading calendar alone cannot prove `PROGRESS_EXPECTED`**, because Futu documents that temporary closures are not removed from that calendar.
8. Until the missing provider semantics are observed, the correct authority state is `CURRENTNESS_UNVERIFIED` / equivalent fail-closed evidence state — not an invented wall-clock threshold.

## Required controlled empirical closure pack

Before freezing 15m/1h currentness, run a bounded, read-only Futu/OpenD observation covering at minimum:

### US liquid symbol, normal full trading day
- subscribe/read K_15M and K_60M under `Session.RTH`;
- record raw `time_key`, raw provider timestamp field, receive wall/monotonic time, OHLCV, and payload hash;
- sample before open, across 09:30 open, multiple transitions, and close;
- compare same-key mutations vs next-key transitions;
- independently call `get_cur_kline` during an actively forming 15m and 60m interval;
- independently call `request_history_kline` during an actively forming interval and compare the newest row to the realtime stream.

### US half trading day
- obtain the actual `TradeDateType` / known shortened-session date;
- repeat K_15M/K_60M collection through close;
- record whether the final bucket is shortened and how it is timestamped.

### Extended-hours control
- compare RTH with explicitly requested ETH/ALL behavior;
- do not infer bucket identity from arrival timing alone.

### Required adjudication
For each tested K type, explicitly discriminate:
- start-boundary hypothesis;
- end-boundary hypothesis;
- provider-defined/other hypothesis.

A fact remains `PARTIALLY_VERIFIED` or `UNKNOWN` unless the observation discriminates competing hypotheses.

## Promotion / governance result

This evidence task does **not** authorize a currentness implementation or threshold.

Current recommendation to Radar main engineering / Architecture & Promotion Control Tower:

> **BLOCK freeze of authoritative K_15M/K_60M currentness timing rules on provider-semantic grounds until controlled US K_15M/K_60M observation closes the unknowns above.**

No production code changes are included in this report.
