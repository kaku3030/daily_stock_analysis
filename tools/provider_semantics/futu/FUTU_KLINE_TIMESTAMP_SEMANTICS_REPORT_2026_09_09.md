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
6. Official Python SDK source (`FutunnOpen/py-futu-api`)
   - current `Session` enum includes RTH / ETH / ALL;
   - no start/end semantic tag is exposed for `time_key`.

No Stock Razor production adapter behavior was used as provider-semantic evidence.

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
| Standard historical request excludes US pre/after-hours by default | VERIFIED | `extended_time=False` default and explicit session controls. | Default request must not be assumed to contain ETH data. |
| US pre/after/overnight K-lines supported at <=60m when requested | VERIFIED | Official historical K-line restrictions and Session support. | Extended-hours currentness must be session-aware. |
| Real-time K-line push may update a forming bar for K_1M | VERIFIED, TESTED SCOPE | Controlled HK K_1M evidence: repeated updates to same `time_key`, up to 38 pushes. | Current bar can be mutable for tested K_1M. |
| Real-time K-line push may update a forming bar for K_15M | UNKNOWN | No official complete flag and no controlled K_15M observation. | Do not generalize K_1M behavior without evidence. |
| Real-time K-line push may update a forming bar for K_60M | UNKNOWN | No controlled K_60M observation. | Do not generalize. |
| K-line payload contains explicit closed/completed flag | VERIFIED NEGATIVE for documented/common KLine surface; K_1M empirically VERIFIED NEGATIVE | Official KLine schema has no documented closed/completed field; controlled K_1M raw payload also had none. | Completion cannot be taken from a provider completion flag on this surface. |
| `get_cur_kline` includes the currently forming K_15M/K_60M bar | UNKNOWN | Docs do not explicitly specify whether newest returned row is forming or completed. | Must observe directly before relying on newest row as complete. |
| `request_history_kline` includes today's currently forming K_15M/K_60M bar | UNKNOWN | Historical API docs do not define forming-bar inclusion/exclusion for current trading day. | Historical API cannot be treated as completed-bars-only without observation. |
| first incomplete K_15M/K_60M bar behavior | UNKNOWN | No official statement / controlled evidence. | Do not derive currentness from first returned bar. |
| market-close K_15M/K_60M final-bar behavior | UNKNOWN | Official market states document close time, not K-line finalization/bucket timestamp. | Final-bar closure semantics unresolved. |
| half-day existence can be identified | VERIFIED | `TradeDateType.MORNING` / `AFTERNOON` / `WHOLE`. | Calendar can signal session shape. |
| half-day K_15M/K_60M alignment/truncation | UNKNOWN | Trading-calendar docs do not specify candle construction on half days. | Must not manufacture expected sequence from normal-day cadence. |
| temporary market close is fully represented by trading calendar | VERIFIED NEGATIVE | Futu explicitly says temporary market-closed data is not excluded by trading calendar. | Calendar alone is insufficient currentness authority. |

## Currentness implications

Until direct US K15/K60 evidence closes the required semantics:

1. **Do not interpret K_15M/K_60M `time_key` as bar start or bar end yet.**
2. **Do not freeze a US K_60M expected sequence yet.** In particular, do not assume either 09:30 anchoring or clock-hour anchoring.
3. **Do not treat the newest historical intraday row as necessarily completed.**
4. **Do not treat `time_key` change as a universal completion signal.** Existing K_1M evidence explicitly shows mutable forming-bar behavior and no completion flag.
5. **Currentness must be session-aware.** RTH vs ETH/ALL changes the set of legitimate progress intervals.
6. **Half days must be calendar/session-shape aware.** Normal-day expected cadence cannot simply be truncated by assumption.
7. **Trading calendar alone cannot prove `PROGRESS_EXPECTED`**, because Futu documents that temporary closures are not removed from that calendar.
8. Until the missing provider semantics are observed, the correct authority state is `CURRENTNESS_UNVERIFIED` / equivalent fail-closed evidence state — not an invented wall-clock threshold.

## Executable controlled empirical closure pack

This branch now contains three evidence-only tools. None is production code.

### A. `kline_timestamp_probe.py` — long live callback capture

Purpose: observe raw US `K_15M` + `K_60M` transitions without mixing in blocking synchronous snapshot calls.

- direct Futu SDK / local OpenD only;
- explicit `Session.RTH`, `ETH`, or `ALL`;
- captures raw callback payload, UTC receive time and monotonic receive time;
- no periodic `get_cur_kline` or historical RPC during the live capture;
- the whole provider child is bounded by a parent hard deadline;
- timeout => incomplete evidence, never semantic promotion.

Recommended normal-session capture:

```bash
cd tools/provider_semantics/futu
python kline_timestamp_probe.py \
  --host 127.0.0.1 --port 11111 \
  --symbol US.AAPL --session RTH --duration 4200
```

Run separate captures spanning:
- 09:30 ET open;
- multiple midday transitions;
- 16:00 ET close;
- a known US half-day close;
- `Session.ALL` for explicit extended-hours comparison.

### B. `kline_snapshot_probe.py` — per-RPC bounded current/history observations

Each synchronous observation runs in its own child process with its own timeout:

- `request_history_kline(K_15M)`;
- `request_history_kline(K_60M)`;
- subscribe + `get_cur_kline(K_15M)`;
- subscribe + `get_cur_kline(K_60M)`.

One hung SDK RPC therefore invalidates only that observation, not the entire evidence run.

Same-day historical requests use `America/New_York` explicitly, preventing a Japan/Asia-local execution host from accidentally requesting the wrong trading date.

Example:

```bash
python kline_snapshot_probe.py \
  --host 127.0.0.1 --port 11111 \
  --symbol US.AAPL --session RTH \
  --repeat 3 --repeat-delay 120 --rpc-timeout 30
```

Run `Session.ALL` separately. Repeated same-key value mutation is evidence candidate for a forming row; unchanged or absent rows do not by themselves prove completion semantics.

### C. `analyze_kline_timestamp_semantics.py` — offline mechanical analyzer

Consumes raw live and snapshot evidence and reports only mechanical observations:

- first callback minus provider `time_key`;
- first callback minus candidate interval start if the key is interpreted as interval end;
- K_60M minute residue compatible with 09:30-anchor (`:30`) vs clock-hour (`:00`);
- repeated material mutations under the same `time_key`;
- same-key mutation across repeated historical/current snapshots.

It deliberately emits `MECHANICAL_OBSERVATION_ONLY` and performs **no automatic VERIFIED promotion**.

## Minimum discriminating evidence required

### K_15M start vs end

Across multiple transitions:
- START candidate predicts first callback for a key near that same key wall-clock;
- END candidate predicts first callback near `time_key - 15 minutes`.

A run that does not discriminate those competing hypotheses remains UNKNOWN/PARTIALLY_VERIFIED.

### K_60M start vs end + RTH anchor

Observe multiple transitions and preferably the first RTH bucket:
- all key minutes at `:30` are compatible with a 09:30-anchored grid;
- all key minutes at `:00` are compatible with a clock-hour grid;
- first-callback timing against the key distinguishes start-like vs end-like behavior.

Do not manufacture the final expected sequence until first and last RTH buckets are directly observed.

### Forming-bar behavior

Same `time_key`, repeated callbacks, materially changing OHLCV/turnover before the next key => direct forming-bar evidence for that tested ktype/session scope.

### Historical API forming-row behavior

Repeated same-day historical snapshots while a live bar is visibly forming:
- if the latest historical row retains the same key while material values change, that is discriminating evidence that the historical API exposes the forming row in the tested scope.

### Market close / half day / extended hours

These require their own scoped observations. A normal midday run cannot close them by analogy.

## Mechanics validation

`tests/test_futu_kline_timestamp_semantics_tools.py` covers:

- 09:30-anchor vs clock-hour K60 mechanical classification;
- end-boundary candidate timing math;
- repeated same-key forming mutation detection;
- repeated historical same-key mutation detection;
- timeout exclusion from semantic comparison;
- evidence tools parsing without importing the Futu SDK;
- permanent separation of long live capture from synchronous periodic snapshot RPCs.

Research Radar CI is explicitly wired to execute this test file so an evidence-tool PR cannot appear green while skipping its own mechanics tests.

## Promotion / governance result

This evidence task does **not** authorize a currentness implementation or threshold.

Current recommendation to Radar main engineering / Architecture & Promotion Control Tower:

> **BLOCK freeze of authoritative K_15M/K_60M currentness timing rules on provider-semantic grounds until controlled US K_15M/K_60M observation closes the unknowns above.**

No production code changes are included in this report or closure pack.
