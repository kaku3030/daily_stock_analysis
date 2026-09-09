# Futu/Moomoo Provider Semantics Harness

Isolated, read-only empirical test harness for Futu/Moomoo provider semantics. **Not production code.** Nothing under `src/` or `data_provider/` imports anything from this directory, and these tools talk to the `futu` SDK directly against a locally running OpenD gateway.

## Existing evidence waves

Wave 1 covers temporal/basic-stream semantics such as QUOTE timestamp behavior, HK K_1M timestamp behavior, entitlement exposure, subscribe semantics, zero-trade behavior and publication delay. Wave 2 covers reconnect/catch-up/provider lifecycle semantics. The current evidence registry is:

`FUTU_SEMANTIC_CONTRACT_V0_1.md`

Raw evidence and semantic adjudication remain separate. Mock/self-tests can validate recorder mechanics but are never provider-semantic evidence.

## P0 K_15M / K_60M timestamp-semantics closure pack

Radar currentness design requires direct US K_15M/K_60M evidence. Official Futu documentation does not define whether `time_key` is a bar-start or bar-end boundary and does not define the US K_60M bucket anchor. Therefore currentness timing remains blocked pending controlled observation.

Authoritative evidence report:

`FUTU_KLINE_TIMESTAMP_SEMANTICS_REPORT_2026_09_09.md`

### 1. Long live callback capture

`kline_timestamp_probe.py`

- subscribes directly to US K_15M + K_60M;
- explicit `Session.RTH`, `ETH`, or `ALL`;
- records raw callbacks and local receive timing;
- does **not** issue periodic synchronous K-line RPCs during the live capture;
- runs the entire provider session in a child process bounded by the parent deadline.

Example:

```bash
python kline_timestamp_probe.py \
  --host 127.0.0.1 --port 11111 \
  --symbol US.AAPL --session RTH --duration 4200
```

A timeout is incomplete evidence and must not be adjudicated.

### 2. Per-RPC current/history snapshots

`kline_snapshot_probe.py`

Every current/history observation uses its own bounded child process, so a hung synchronous SDK call invalidates only that observation.

```bash
python kline_snapshot_probe.py \
  --host 127.0.0.1 --port 11111 \
  --symbol US.AAPL --session RTH \
  --repeat 3 --repeat-delay 120 --rpc-timeout 30
```

Same-day historical dates are derived from `America/New_York`, never from the execution host's local timezone.

### 3. Offline mechanical analysis

`analyze_kline_timestamp_semantics.py`

The analyzer reports competing-hypothesis observations only:

- first callback vs provider `time_key`;
- first callback vs candidate interval start if key is interpreted as interval end;
- K60 `:30` vs `:00` grid compatibility;
- repeated same-key OHLCV/turnover mutation;
- repeated current/history same-key mutation.

It deliberately emits `MECHANICAL_OBSERVATION_ONLY` and cannot self-promote a provider fact to VERIFIED.

### 4. Mechanics tests

`tests/test_futu_kline_timestamp_semantics_tools.py`

Research Radar CI explicitly executes these tests. They validate evidence-tool logic and anti-false-promotion behavior only; they do not substitute for a live OpenD run.

## Evidence rules

1. Every live run gets a fresh output path; previous evidence is never rewritten.
2. Raw provider payload is preserved before interpretation.
3. Provider timestamp strings stay raw in evidence; timezone interpretation is recorded separately.
4. Failed, timed-out or partial runs do not become semantic truth.
5. A single scope does not generalize across market, K type, session or SDK/OpenD version.
6. No currentness threshold may be invented while K15/K60 timestamp semantics remain unresolved.
7. No order/account/trading-state calls are permitted in provider-semantics tools.
8. The closure pack may change evidence scripts, tests, CI wiring and governance docs only; it must not modify production provider routing, currentness logic or trading behavior.

## Prior Wave 1 layout and safety

Wave 1 uses `models.py`, `recorder.py`, `wave1_runner.py` and `harness_selftest.py`, with raw `events.jsonl`/`sdk_calls.jsonl` and write-once metadata/observations/results artifacts. See git history and the evidence contract for detailed Wave 1/Wave 2 provenance.
