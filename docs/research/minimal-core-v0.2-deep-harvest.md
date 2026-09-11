# Minimal Core Initiative V0.2 — Deep Harvest and Repo Mapping

**Status:** RESEARCH / SHADOW ONLY  
**Date:** 2026-09-11  
**Canonical repo:** `kaku3030/stock-razor`  
**Initiative:** Minimum Semantic Code, not minimum LOC.

## 1. Purpose

V0.1 established the rule that Stock Razor should learn not only what to add, but what can be made smaller. V0.2 turns that into a repo-mapped research program.

The target is to reduce:

- semantic state owners;
- duplicated contracts and validators;
- ad-hoc branches and hidden fallbacks;
- mixed I/O + decision logic;
- agent read-set and context/token load;
- time-to-reproduce and time-to-review;
- regression surface.

The target is **not** to minimize files or line count. A mechanically split 7,000-line subsystem can still have the same semantic complexity. Conversely, explicit `UNKNOWN`, currentness, fail-loud findings, evidence retention, reconciliation and risk controls are valuable complexity and must not be deleted merely to make the code look small.

## 2. Governing invariant

The cross-project data path remains:

```text
Canonical Raw Evidence
        ↓
Governed Normalization
        ↓
Canonical State
        ↓
Optional Projection / Compression
        ↓
Model / Narrative
```

Never:

```text
Provider Payload → AI Compression → Canonical State
```

AI Monitor remains the only production owner of Provider Worker, LiveFeed, Portfolio runtime truth, Currentness enforcement, restart/reconciliation, notification runtime, AI invocation/runtime and Shadow/LIVE runtime.

Radar remains owner of Candidate Discovery, Relative Strength, Capital Persistence, Lifecycle research, Replay/OOS, Strategy Lab, Model Evaluation and Candidate/Research scoring.

`RADAR/PERCEPTION_DATA_INTELLIGENCE` supplies provider/timestamp/currentness/microstructure evidence and fixtures; it must not create a second production runtime.

## 3. Repo evidence already found

### 3.1 The right pattern already exists inside Razor

`realtime_monitor/server.py` contains `compare_analysis_states(previous_state, current_state)`, documented as a pure deterministic function that does not persist state, perform I/O, invoke AI, notify, or create trading instructions.

**Harvest implication:** do not invent a new architecture. Expand this existing **functional semantic core + imperative shell** pattern where it reduces read-set and state ownership.

### 3.2 Currentness is already deterministic enough to model explicitly

The current code contains deterministic status vocabulary including:

- `OK`
- `DATA_UNAVAILABLE`
- `STALE_OR_MISALIGNED`

and reason semantics such as:

- `LATEST_BAR_MATCHES_EXPECTED_SESSION`
- `LATEST_BAR_BEFORE_EXPECTED_SESSION`
- future/ahead-of-session mismatch

**Harvest implication:** Currentness is a strong candidate for a compact pure state/table model plus differential replay. It is **not** a candidate for LLM judgment or generic cache semantics.

### 3.3 Delivery retry is intentionally constrained

Current delivery transport comments explicitly define single-attempt/no-retry semantics and bounded timeouts. Therefore a generic `tenacity` migration must **not** rewrite Delivery merely because `tenacity` exists.

**Harvest implication:** retry consolidation is allowed only where retries are semantically transport-safe. Entitlement, subscription failure, stale evidence, invalid payloads, `UNKNOWN`, and governed single-attempt delivery policies are not transient-retry opportunities by default.

### 3.4 Dependency-fact correction

Root `requirements.txt` currently includes:

- `tenacity>=8.2.0`
- `schedule>=1.2.0`

The V0.1 ledger described `cachetools` as an existing dependency. That claim is **not supported by the current root requirements** and should be treated as corrected here. `cachetools` remains only an external design reference unless a separate dependency manifest proves otherwise.

This correction establishes a rule for all future Harvest work:

> External design value, installed dependency status, and actual runtime usage are three different claims and must be evidenced separately.

## 4. Deep Harvest Batch 2

| ID | Source | Core lesson | Razor target | Decision |
| --- | --- | --- | --- | --- |
| H13 | `python-hyper/h11` | Sans-I/O: protocol/state semantics contain no I/O; events cross a narrow boundary | Currentness, Trigger, Delivery semantic cores | **ADAPT strongly** |
| H14 | Hypothesis stateful testing | generate sequences of actions and assert invariants after steps | Currentness, lifecycle, restart/reconciliation adversarial testing | **ADAPT / TEST SHADOW** |
| H15 | SQLite architecture / VDBE | compile many surface cases into a small explicit execution model | repeated gate/mapping/normalization rules | **ADAPT principle; no generic VM yet** |
| H16 | John Ousterhout / deep modules | hide substantial complexity behind a small stable interface | provider adapters, currentness facade, runtime boundaries | **ADAPT** |
| H17 | Trio / structured concurrency | child task lifetime belongs to an explicit parent scope | worker/restart/background-task lifecycle | **SHADOW principle** |
| H18 | `pytest-dev/pluggy` | narrow hook specs can isolate extension points | provider/research extensions only if actual extension pressure exists | **SHADOW / likely reject premature pluginization** |

### H13 — `python-hyper/h11`: Sans-I/O

Reference: <https://github.com/python-hyper/h11>

h11 deliberately contains no network I/O. Bytes/events cross a small boundary while protocol state stays testable independently of sync/threaded/async transports. Its README also emphasizes minimizing special cases and ad-hoc state manipulation.

**Transfer to Razor:**

```text
I/O adapter
    ↓ normalized observation/event
Pure semantic state transition
    ↓ deterministic result + reason codes
I/O shell / persistence / notification
```

High-value candidates:

1. Currentness evaluation;
2. Trigger/Event transition logic;
3. Delivery decision semantics (not necessarily transport);
4. entitlement/subscription finding classification.

**Do not transfer:** one giant file, protocol-specific APIs, or a new framework dependency. The important idea is the I/O-free semantic seam.

### H14 — Hypothesis: generated state/action sequences

Reference: <https://hypothesis.readthedocs.io/en/latest/stateful.html>

Hypothesis stateful testing generates sequences of primitive actions rather than only individual values, and supports invariants checked after each step.

**Transfer to Razor:** use generated event sequences against pure/Shadow state machines, especially where hand-written examples miss temporal edge cases.

Candidate action vocabulary:

```text
PRE_OPEN
OPEN
BAR_ARRIVES
BAR_MISSING
TIMESTAMP_MISSING
LUNCH_BREAK
RESUME
SESSION_CLOSE
HOLIDAY
TIMEZONE_SHIFT
PROVIDER_DISCONNECT
PROVIDER_RECONNECT
ENTITLEMENT_LOST
ENTITLEMENT_RESTORED
PROCESS_RESTART
```

Example invariants:

- missing timestamp never becomes `OK` by inference;
- closed-market calendar gaps do not automatically imply stale data;
- `UNKNOWN` is not silently upgraded to known;
- provider reconnect cannot erase prior canonical evidence without reconciliation;
- notification transport cannot mutate decision/evidence semantics;
- no generated sequence creates a second authoritative Portfolio/Currentness owner.

**Decision:** TEST SHADOW first. Do not add Hypothesis as a dependency until one prototype demonstrates that it finds cases our existing adversarial fixtures do not.

### H15 — SQLite: compact intermediate execution model

Reference: <https://www.sqlite.org/arch.html>

SQLite compiles a rich SQL surface into bytecode and executes that through its VDBE. The transferable lesson is not "build a VM"; it is that many surface cases can share a compact, explicit intermediate semantic model.

**Potential Razor transfer:** repeated mapping/gate logic may sometimes become data rather than code:

```text
Rule(id, inputs, predicate, result, reason_code)
```

Then one small evaluator executes the rules.

Good targets:

- stable status/reason-code mappings;
- provider capability tables;
- delivery policy tables;
- simple Gate matrices where order/precedence are explicit.

Bad targets:

- highly dynamic strategy logic;
- anything where a table hides sequencing, mutation or side effects;
- a generic "Razor VM" without proven duplicated semantics.

**Decision:** ADAPT principle only. Table-drive repeated stable semantics before considering any richer IR.

### H16 — Ousterhout: deep modules / information hiding

Reference: <https://web.stanford.edu/~ouster/cgi-bin/book.php>

The useful design test is not "is every function tiny?" but whether an interface is small relative to the complexity hidden safely behind it.

**Transfer to Razor:** provider-specific SDK quirks should terminate at a narrow normalization boundary. Callers should not need Futu/Tushare/AkShare-specific timestamp, entitlement or error vocabulary if those details can be normalized without semantic loss.

Candidate metric:

```text
interface_surface / hidden_semantic_complexity
```

We want small stable interfaces that preserve evidence and reason codes, not thin pass-through wrappers that merely rename calls.

### H17 — Trio: structured concurrency

Reference: <https://github.com/python-trio/trio>

The transferable principle is explicit task lifetime: background work should have an owner, cancellation boundary and completion/error propagation path.

**Razor target:** AI Monitor worker/restart/reconciliation and background task topology.

Questions to audit:

- Which background tasks can outlive their intended owner?
- Where can an exception be silently detached?
- Is cancellation/restart propagation explicit?
- Can shutdown leave partially updated authoritative state?

**Decision:** SHADOW principle. No runtime migration to Trio/AnyIO is proposed by this research. First model the current topology and prove a lifecycle problem.

### H18 — pluggy: narrow extension contracts

Reference: <https://github.com/pytest-dev/pluggy>

pluggy demonstrates a small hookspec/hookimpl contract used by mature extensible projects.

**Potential Razor value:** provider/research extensions could sometimes depend on a narrow capability contract instead of central orchestration conditionals.

**Major risk:** plugin systems are easy to introduce before the domain is stable, increasing indirection and agent read-set.

Promotion condition:

- at least three real implementations share a stable contract;
- central branching is demonstrably duplicated;
- a plugin boundary reduces, rather than increases, the files required to understand a change;
- production ownership stays singular.

Until then: **SHADOW / likely REJECT**.

## 5. Semantic Complexity Score V0.1

LOC remains informational only. For each candidate change, measure before/after:

| Dimension | Better direction | Why |
| --- | --- | --- |
| authoritative state owners | down / unchanged at 1 | prevents split truth |
| decision branches | down | fewer special cases |
| duplicated contracts/schema definitions | down | one meaning, one definition |
| module fan-out | down | smaller blast radius |
| mixed I/O + decision sites | down | easier deterministic tests |
| files in safe-change read-set | down | faster humans/agents, fewer tokens |
| context tokens for representative task | down | direct AI cost/latency signal |
| UNKNOWN/currentness semantic preservation | exactly preserved | correctness gate |
| replay determinism | unchanged or improved | auditability |
| hidden fallback count | down | fail-loud reliability |
| bypass paths around governed gates | zero | governance |

A simplification is rejected if LOC falls but semantic owners, hidden fallbacks, ambiguity, or bypass paths increase.

## 6. Repo-mapped candidate queue V0.2

### MCI-C01 — Currentness semantic core

**Target:** extract/model deterministic currentness as pure input → output logic with explicit reason codes.

**Desired shape:**

```text
CurrentnessInput(
    market,
    request_time,
    session_calendar,
    latest_timestamp,
    provider_status,
    timestamp_quality,
)
    ↓
evaluate_currentness()
    ↓
CurrentnessResult(status, reason_codes, expected_session, evidence)
```

No network calls, no AI, no persistence, no notification.

**Status:** PROMOTE TO SHADOW DESIGN.

### MCI-C02 — Trigger/Event pure-core expansion

`compare_analysis_states()` already demonstrates the desired pattern.

**Action:** identify adjacent trigger/event branches that can reuse a similarly deterministic event algebra rather than growing orchestration conditionals.

**Status:** PROMOTE TO AUDIT.

### MCI-C03 — Retry inventory, not retry refactor

Because Delivery is intentionally no-retry, first classify every retry-like site:

- TRANSIENT_TRANSPORT
- RATE_LIMIT
- SERVER_RETRYABLE
- AUTH_OR_ENTITLEMENT
- SEMANTIC_INVALIDITY
- CURRENTNESS_FAILURE
- GOVERNED_SINGLE_ATTEMPT

Only the first three can even be candidates for centralized retry policy, and only with bounded attempts + observability.

**Status:** AUDIT FIRST.

### MCI-C04 — Stable table-driven mappings

Locate repeated stable enums/reason-code/capability maps. Convert only repeated deterministic branches into declarative tables where precedence is explicit and tests can enumerate the whole table.

**Status:** SHADOW.

### MCI-C05 — Provider normalization deep boundary

Measure how many provider-specific fields escape their adapters. A successful deep boundary should reduce downstream provider conditionals without erasing raw evidence.

**Status:** AUDIT.

### MCI-C06 — Worker lifecycle topology

Document owner → child-task → cancellation → restart → reconciliation edges before considering structured-concurrency changes.

**Status:** RESEARCH ONLY.

### MCI-C07 — Agent read-set budget

For representative tasks (Currentness fix, provider mapping fix, Delivery finding fix), record:

- files opened;
- relevant lines read;
- approximate input tokens;
- time/steps to locate authority;
- number of ambiguous owners encountered.

This becomes a first-class architectural metric.

**Status:** ADOPT FOR BENCHMARKING.

## 7. Experiments

### MCI-E01 — Currentness Differential Replay

**Goal:** prove a smaller pure/table model is behaviorally equivalent or safer.

Dataset must include:

- pre-open;
- normal session;
- lunch break where applicable;
- post-close;
- weekend/holiday;
- daylight/timezone boundaries;
- missing timestamp;
- future timestamp;
- delayed provider;
- disconnect/reconnect;
- partial timeframe availability.

**Gate:** 100% match on governed status/reason semantics for accepted cases; any intentional difference requires an explicit bug finding and approved expected-result change.

### MCI-E02 — Trigger Pure-Core Read-Set Benchmark

Compare a representative Trigger change before/after semantic extraction.

Measure:

- files required to understand safely;
- lines/context tokens read;
- branch count;
- test setup size;
- event-output equivalence.

**Gate:** deterministic output preserved and read-set materially reduced.

### MCI-E03 — Retry Semantic Inventory

No code change initially. Produce a machine-readable or documented inventory of retry-capable call sites and classify each by the taxonomy in MCI-C03.

**Gate:** zero governed single-attempt or semantic failures accidentally reclassified as transient.

### MCI-E04 — Generated Currentness State Sequences

Prototype Hypothesis (or equivalent generated sequence harness) outside production dependencies first.

**Gate for adding dependency:** it must discover at least one meaningful edge case not covered by the existing deterministic/adversarial fixture suite, or materially reduce test code while preserving coverage and reproducibility.

### MCI-E05 — Provider Escape-Surface Audit

For each provider, count provider-specific names/types/status codes visible outside the adapter/normalization boundary.

**Gate:** proposed simplification must reduce escape surface while preserving canonical raw evidence and traceability.

## 8. Promotion protocol

No candidate moves from research to implementation unless it has:

1. explicit production owner;
2. before/after semantic-complexity metrics;
3. protected-field inventory;
4. deterministic unit tests;
5. differential/replay evidence where behavior exists today;
6. adversarial cases for `UNKNOWN`, timestamp/currentness and bypass paths;
7. rollback path;
8. proof that no second source of truth is created.

A third-party library is not automatically preferred over a tiny local implementation. Dependency count itself is part of complexity.

## 9. Cross-project sync delta

### AI_MONITOR/HARVEST

Research and benchmark:

- Sans-I/O / functional-core extraction;
- retry semantic inventory;
- structured task-lifecycle topology;
- Headroom only after canonical state and only as LLM-facing projection;
- agent read-set/token measurements.

### AI_MONITOR/CONTROL_TOWER

Own promotion decisions for all production-runtime simplification. No provider/currentness/delivery/restart change can be promoted from this research lane without AI Monitor replay/test evidence.

### RADAR/HARVEST

Apply the same Minimum Semantic Code tests to Replay/OOS, Gate evaluation, model evaluation and research orchestration. Prefer pure fixture-driven evaluators over model-owned state.

### RADAR/CONTROL_TOWER

Reject simplifications that introduce compensatory scoring, narrative authority, duplicated Gate logic or new state owners.

### RADAR/PERCEPTION_DATA_INTELLIGENCE

Supply adversarial timestamp/session/provider-semantic fixtures for MCI-E01/E04/E05. Remain observation/research-only; do not implement Currentness runtime.

### Trading intelligence four-lane system

`Main Control & Trading Desk`, `A-Share Radar`, `US Stock Radar`, and `Global Policy Intelligence` consume the architectural result only indirectly. Their analysis contracts must remain stable while engineering internals simplify. No market conclusion, holding decision, risk budget or trading action is changed by this research PR.

## 10. MAIN_SYNC_PACKET

```yaml
timestamp: 2026-09-11
source_lane: MINIMAL_CORE_INITIATIVE
status: EXPANDED_V0_2_RESEARCH
production_behavior_change: false
new_hard_findings:
  - compare_analysis_states is already a pure deterministic internal precedent
  - currentness has explicit deterministic status/reason semantics suitable for differential replay
  - delivery transport intentionally uses single-attempt/no-retry semantics
  - root requirements confirm tenacity and schedule; cachetools existing-dependency claim is not supported
new_harvest_sources:
  - python-hyper/h11
  - Hypothesis stateful testing
  - SQLite architecture/VDBE
  - John Ousterhout deep-module design
  - Trio structured concurrency
  - pytest-dev/pluggy
priority_experiments:
  - MCI-E01 Currentness Differential Replay
  - MCI-E02 Trigger Pure-Core Read-Set Benchmark
  - MCI-E03 Retry Semantic Inventory
  - MCI-E04 Generated Currentness State Sequences
  - MCI-E05 Provider Escape-Surface Audit
risk_budget_implication: NONE
portfolio_relevant_impacts: NONE
urgent_main_attention: NONE
conflicts_with_other_lanes:
  - no second Provider Worker/Currentness/runtime is permitted
  - Delivery no-retry policy must not be overwritten by generic retry consolidation
  - compression remains downstream of canonical state
next_validation_conditions:
  - quantify read-set and branch/owner baselines
  - complete differential replay design for Currentness
  - complete retry-site semantic inventory
  - prove whether generated stateful tests add edge-case value before adding dependency
data_confidence:
  repo_dependency_facts: HIGH
  currentness_delivery_semantics: HIGH
  simplification_savings: UNKNOWN_UNTIL_BENCHMARKED
```

**Sync to:** `AI_MONITOR/HARVEST`, `AI_MONITOR/CONTROL_TOWER`, `RADAR/HARVEST`, `RADAR/CONTROL_TOWER`, `RADAR/PERCEPTION_DATA_INTELLIGENCE`, `STOCK RAZOR｜Main Control & Trading Desk`, `STOCK RAZOR｜A-Share Radar`, `STOCK RAZOR｜US Stock Radar`, `STOCK RAZOR｜Global Policy Intelligence`.
