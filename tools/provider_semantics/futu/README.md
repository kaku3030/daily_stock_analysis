# Futu/Moomoo Provider Semantics Harness -- Wave 1

Isolated, read-only empirical test harness for Futu/Moomoo provider
semantics. **Not production code.** Nothing under `src/` or
`data_provider/` imports anything from this directory, and this harness
imports nothing from production adapters -- it talks to the `futu` SDK
directly against a locally running OpenD gateway.

## Scope (Wave 1 only)

F01 (quote timestamp semantics), F02 (1m bar timestamp semantics), F03
(timezone/UTC normalization of raw fields), F04 (realtime-vs-delayed
entitlement exposure), F05 (entitlement scope), F06 (subscribe result/ACK
semantics), F07 (ACK granularity), F09 (zero-trade minute behavior), F10
(low-liquidity silence behavior), F28 (normal publication delay), F37
(symbol normalization).

Wave 2 (reconnect/catch-up experiments) is explicitly out of scope here.

## Safety

Market-data only. Never places, cancels, or modifies an order; never
changes account or trading state; never subscribes a paid package or
changes permissions. Only quote/market-data SDK calls are used.

## Layout

```
tools/provider_semantics/futu/
    README.md
    models.py              # RawEvent shape + SemanticTestResult/TestStatus
    recorder.py            # append-only JSONL recorder, run-dir management
    wave1_runner.py         # CLI harness: connects, probes, subscribes, analyzes
    harness_selftest.py     # pytest: recorder/model MECHANICS only (mocked callback)
    runs/                  # one timestamped subdirectory per execution
        2026-.../
            metadata.json      # environment provenance (written once)
            events.jsonl       # raw push events, append-only
            sdk_calls.jsonl    # raw SDK call/response records, append-only
            observations.json # post-hoc structured analysis (written once)
            results.json       # SemanticTestResult per Wave-1 test id (written once)
```

Every run gets a fresh, uniquely-named directory. Raw evidence files
(`events.jsonl`, `sdk_calls.jsonl`) are opened in append mode for the
lifetime of one run and are never rewritten; `metadata.json`,
`observations.json`, and `results.json` are written exactly once per run
and raise `FileExistsError` on a second write attempt. Re-running the
harness always creates a new run directory -- prior evidence is never
overwritten.

## Two-layer evidence model

1. **Raw evidence** (`events.jsonl`, `sdk_calls.jsonl`): unmodified provider
   data plus local capture metadata (UTC wall-clock time, monotonic
   receive time, thread id, local sequence number). No field is dropped
   for looking irrelevant. No interpretation is applied here.
2. **Semantic results** (`results.json`): one `SemanticTestResult` per
   Wave-1 test id, referencing the raw evidence files by path -- never
   inlining raw SDK objects. Status is restricted to `VERIFIED`,
   `PARTIALLY_VERIFIED`, `UNRESOLVED`, `CONFLICTING`. The harness
   deliberately biases toward `PARTIALLY_VERIFIED`/`UNRESOLVED` rather than
   self-declaring `VERIFIED` from a single short run -- final semantic
   adjudication is external to this tool.

## Running

Prereqs: OpenD gateway running and reachable, `futu` SDK installed in the
active Python environment (`.venv312` in this repo).

Smoke run (2-5 minutes, verify mechanics before a longer run):

```bash
cd tools/provider_semantics/futu
python wave1_runner.py --host 127.0.0.1 --port 11111 \
    --market HK --symbols HK.00700 --duration 150 \
    --stream-types QUOTE,K_1M --output-dir runs
```

Full Wave 1 run (longer duration, add a configured low-liquidity symbol for
F10 -- the harness will NOT guess one on its own):

```bash
python wave1_runner.py --host 127.0.0.1 --port 11111 \
    --market HK --symbols HK.00700 --duration 900 \
    --stream-types QUOTE,K_1M --output-dir runs \
    --low-liquidity-symbol HK.XXXXX
```

If `--low-liquidity-symbol` is omitted, F10's result is
`NEEDS_MANUAL_SYMBOL` rather than the harness silently picking an obscure
instrument.

CLI flags: `--host`, `--port`, `--market`, `--symbols`, `--duration`,
`--stream-types`, `--output-dir`, plus harness-specific
`--entitlement-markets`, `--entitlement-symbols`, `--invalid-symbol`,
`--low-liquidity-symbol`. No credentials/tokens are ever printed or written
to evidence files -- `models.scrub_secrets()` redacts anything shaped like
a secret before it reaches disk, enforced by `harness_selftest.py`.

## Self-tests

```bash
cd tools/provider_semantics/futu
python -m pytest harness_selftest.py -v
```

These test recorder/model **mechanics only** (JSONL append-only behavior,
run-directory immutability, UTC timestamp shape, monotonic sequencing under
concurrency, secret redaction, result-status validation) using one fake
mocked callback shape solely to prove the recorder ingests provider-shaped
payloads without dropping fields. **The mock is never cited as evidence
about real Futu behavior** -- only a live run against a reachable OpenD
produces evidence usable for semantic adjudication.

## What this harness does NOT do

- It does not declare architectural truth from one observation. A short
  run producing 20 consistent samples is `PARTIALLY_VERIFIED`, not
  `VERIFIED`, unless the evidence is discriminating enough to rule out
  competing interpretations.
- It does not attach a timezone to a naive provider timestamp string. Any
  parsed candidate is labeled `interpretation_candidate` and stored
  alongside -- never in place of -- the raw text.
- It does not map an observed SDK field to `DeliveryMode.REALTIME` (or any
  other production enum) unless the SDK response directly and
  unambiguously evidences that mapping.
- It does not run Wave 2 (reconnect/catch-up) experiments.
