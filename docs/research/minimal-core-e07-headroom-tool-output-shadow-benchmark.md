# MCI-E07 — Headroom Tool-Output Compression Shadow Benchmark

**Initiative:** Minimal Core V0.3  
**Owner for any future production integration:** `AI_MONITOR/CONTROL_TOWER`  
**Mode:** offline / Shadow benchmark only  
**Production behavior change:** none

## 1. Question

After structural read-set reduction, can Headroom-style tool-output compression reduce LLM-facing context for Stock Razor without changing any governed fact, gate, currentness result, or downstream model/tool decision?

E07 measures **E06 Layer B only**: tool/search/log/JSON output presented to an agent/model.

It does not compress canonical runtime state.

## 2. Non-negotiable data path

```text
Canonical Raw Evidence
        ↓ persisted/retrievable unchanged
Protected-field classifier
        ↓
Shadow compression/projection
        ↓
LLM-facing context only
```

Never:

```text
Provider payload → compression → canonical state
Compression output → Portfolio truth
Compression output → Currentness authority
Compression output → Gate authority
```

## 3. Protected fields V0.1

The benchmark must treat the following as exact-preservation fields whenever present:

- `UNKNOWN`, `INDETERMINATE`, `DATA_UNAVAILABLE`, `STALE_OR_MISALIGNED`;
- timestamps and timezone/offset information;
- `expected_session`, `observed_session`, `provider_timestamp`;
- provider identity/status;
- entitlement/subscription/delivery status;
- `gate_result`, `candidate_status`;
- `reason_code`, `reason_codes`;
- `risk_flags`;
- portfolio quantity/cost/available/frozen state;
- lifecycle/thesis identifiers;
- attempt/retry/fallback/cooldown evidence when debugging reliability;
- error/exception/failure records;
- fixture IDs and replay expected results.

A compression configuration that cannot guarantee exact protection for a payload class is not eligible for that class.

## 4. Benchmark corpus

Build an offline corpus from sanitized/replayable artifacts, not live secrets.

### C1 — GitHub / CI output

Examples:

- PR metadata with large repeated fields;
- changed-file lists;
- CI job/step JSON;
- repetitive successful test logs;
- failure logs with one or more critical exceptions.

Protected: SHA, workflow/job status, conclusion, failed step, exception/error lines, test counts, governed check names.

### C2 — Provider capability JSON

Use `DataCapabilityService` fixtures and outputs.

Protected:

- provider name;
- configured/enabled/status;
- `unknown`;
- market/dataset coverage;
- priority order;
- fallback/cooldown warnings;
- last-error/reason fields.

### C3 — Currentness / replay payloads

Use E01 fixtures.

Protected:

- fixture ID;
- request/latest timestamps;
- market/session/timeframe;
- status;
- reason codes;
- `UNKNOWN` / missing values.

### C4 — Research radar candidate payloads

Protected:

- `claim_id` / evidence IDs where present;
- `gate_result`;
- `candidate_status`;
- confidence;
- risk flags;
- lifecycle state;
- source timestamps.

Narrative prose can be more compressible than governed fields.

### C5 — Provider/retry diagnostics

Use E03 deterministic fake failures and sanitized logs.

Protected:

- FailureClass;
- exception type/root cause;
- provider/source;
- attempt count;
- timeout budget;
- fallback sequence;
- cooldown/circuit state;
- final result/reason.

### C6 — Code/source excerpts

Control group. Code should normally pass through or receive conservative handling. E07 does not seek high compression here.

## 5. Test matrix

For every corpus item run:

```text
raw artifact
   ├─→ baseline model/task → BaselineResult
   └─→ compressed artifact → ShadowResult

raw vs compressed token count
BaselineResult vs ShadowResult
protected-field extractor before/after
```

Repeat with the same model/version/prompt/settings.

## 6. Tasks

### T1 — factual extraction

Ask for protected fields only. Expected exact match.

### T2 — diagnosis

Ask the model to identify root failure and next safe diagnostic step.

### T3 — governed classification

Ask for Currentness/gate/candidate state using only supplied deterministic evidence. Shadow must not change result.

### T4 — tool-selection / next-action

Ask which file/log/provider fixture should be inspected next. Compare tool/action choice.

### T5 — summary/narrative

Measure whether compressed context changes qualitative summary while governed facts remain exact.

## 7. Metrics

Record per item and corpus class:

- raw input tokens;
- compressed input tokens;
- token reduction %;
- compression latency;
- model latency;
- **Critical Field Recall**;
- exact status/gate/candidate equivalence;
- reason-code set equivalence;
- risk-flag set equivalence;
- timestamp/session equivalence;
- diagnostic root-cause equivalence;
- next-tool/action equivalence;
- hallucinated facts count;
- retrieval-to-raw fallback count.

## 8. Initial promotion thresholds

These are Stock Razor internal research thresholds, not Headroom vendor claims.

To move from `SHADOW` to a limited pilot, require on the approved corpus:

- **100% Critical Field Recall**;
- **100% exact equivalence** for deterministic status/gate/candidate outputs;
- **100% reason/risk protected-set retention**;
- zero invented timestamps/provider states;
- zero cases where `UNKNOWN` becomes known by inference;
- zero production/raw-evidence replacement;
- aggregate Layer-B token reduction of at least **20%** across the intended payload mix;
- no material diagnostic/tool-selection regression;
- local/controlled configuration with raw artifact retrievable;
- telemetry/beacon posture reviewed explicitly before any deployment.

Failure on any protected-field condition blocks promotion regardless of token savings.

## 9. Compression eligibility by payload

| Payload | Initial policy |
| --- | --- |
| repetitive CI success logs | **eligible Shadow** |
| GitHub list/search JSON | **eligible Shadow** |
| provider capability JSON | **eligible only with protected schema** |
| Currentness fixture/result | **conservative / protected** |
| Portfolio runtime truth | **passthrough** |
| Gate/reason/risk record | **passthrough or field-protected only** |
| code/source diff | **passthrough by default** |
| exception/failure slice | **preserve exact critical lines** |
| long narrative/docs | **eligible Shadow** |

## 10. Headroom-specific operational constraints

If Headroom itself is used in the benchmark:

- pin exact version/commit in the benchmark record;
- disable any non-required telemetry/beacon path for internal evaluation;
- record compression profile/settings;
- do not enable aggressive generic-text compression on governed payloads by default;
- store raw + compressed artifact hashes;
- ensure benchmark failures are inspectable without the compressed version becoming evidence authority.

## 11. Why E07 comes after E06

Compression can hide architecture debt. If an agent needs to read five duplicated provider registries, compressing those five files is less valuable than deleting four duplicated semantic owners.

Order of operations:

```text
reduce semantic duplication
        ↓
reduce repository read-set
        ↓
protect governed fields
        ↓
compress repetitive tool output
```

## 12. Decision

**HEADROOM REMAINS SHADOW.**

E07 converts “Headroom may save tokens” into a falsifiable Stock Razor benchmark. No production integration is proposed until protected-field and decision-equivalence gates pass.
