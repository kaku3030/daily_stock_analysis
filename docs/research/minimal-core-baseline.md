# Minimal Core Baseline V0.1

**Date:** 2026-09-11  
**Scope:** repository-level research baseline; **no production behavior change**.  
**Confidence:** mixed. Items below are candidates until code/replay evidence closes them.

## Baseline rules

This document deliberately separates **observed evidence** from **simplification hypotheses**. Large files and many abstractions are not automatically defects. A candidate becomes actionable only after a red-capable test/replay seam and semantic-owner analysis exist.

Primary metric: **Minimum Semantic Code**.

Secondary metric: LOC/file size.

## Initial observations

### O1 — Realtime Monitor has a high agent read-set candidate

Inspection of `realtime_monitor/server.py` shows one module containing, at minimum, concerns from several semantic families:

- Anthropic/OpenAI client integration
- FastMCP exposure
- Futu quote/trade contexts
- environment/runtime configuration
- JSON sanitation
- pure indicator calculation
- timeframe state summarization
- state comparison / trigger-event logic
- runtime state constants/persistence paths

This does **not** prove the module should be mechanically split. It does prove that a change in this area can require an agent/reviewer to distinguish runtime I/O, market-data semantics, pure analysis, state-transition semantics, and AI integration inside the same read-set.

**Research question:** can the semantic core be made smaller by extracting pure contracts/state transitions while leaving runtime ownership singular?

### O2 — Existing dependencies may already solve generic glue

The repository already depends on established primitives including:

- `tenacity` for retry/backoff composition
- `schedule` for simple in-process scheduling
- `cachetools` for cache policy

The first simplification question is therefore **not** “which new library should we add?” but “where are we still maintaining local equivalents that can be deleted or converged?”

### O3 — Pure functions already exist inside runtime code

The inspected Realtime Monitor code already contains pure or near-pure functions such as indicator calculation, timeframe-state summarization, and snapshot comparison.

That is encouraging: the initiative should prefer **lifting and protecting existing pure seams** rather than redesigning everything around a new framework.

### O4 — `INDETERMINATE` / explicit unknown behavior is valuable complexity

The inspected state functions explicitly return states such as `INDETERMINATE` when required inputs are missing or inconsistent. This is complexity worth preserving. A simplification that turns these cases into neutral/default values is a semantic regression even if it removes code.

## Top 10 simplification candidates

| Rank | Current / observed pain | Candidate simplification | Expected gain | Main risk | Validation seam | Owner | Initial decision |
| ---: | --- | --- | --- | --- | --- | --- | --- |
| 1 | Realtime Monitor combines multiple semantic families in a high-read-set module | Identify a tiny pure semantic core and thin runtime edges; reduce pass-through/duplicate logic without creating another runtime | agent speed, review/debug speed, testability | cosmetic file splitting; duplicate ownership | current tests + differential replay of same inputs/outputs | AI Monitor | **SHADOW / SIMPLIFY** |
| 2 | Currentness logic has known false-positive/UNKNOWN edge cases | One explicit currentness state owner; consider local table-driven transition graph vs state-machine library | fewer branches, clearer illegal states, adversarial tests | collapsing market-session/timezone nuances | lunch/pre-open/post-close/missing-timestamp/Futu-time fixtures | AI Monitor | **SHADOW** |
| 3 | Delivery/entitlement/subscription semantics have known silent-drop risk | Typed explicit delivery state + fail-loud findings; one transition contract | reliability + smaller branch surface | hiding provider-specific entitlement semantics | entitlement/subscription/result adversarial fixtures | AI Monitor | **SHADOW / TABLE-DRIVE** |
| 4 | Retry policy can drift across provider/API call sites | Audit handwritten retry/backoff and consolidate on existing `tenacity` where failures are truly transient | delete glue, consistent telemetry | retrying semantic failure/stale/UNKNOWN conditions | injected transient vs semantic failure tests | AI Monitor | **SIMPLIFY / REPLACE local glue** |
| 5 | Simple scheduling and durable continuity can be accidentally conflated | Keep `schedule` only for simple non-authoritative jobs; separate durable/restart-aware semantics explicitly | clearer responsibility, less custom scheduler glue | using a simple scheduler for durable state | restart/reconciliation integration tests | AI Monitor | **KEEP / SIMPLIFY** |
| 6 | Timestamp/TTL caches are easy to reimplement ad hoc | Audit local TTL/LRU dictionaries; consolidate only non-authoritative caches on existing `cachetools` | delete repeated expiry code | cache becoming source of truth | expiry/eviction tests + runtime truth assertions | AI Monitor | **SIMPLIFY** |
| 7 | Provider-specific normalization/mapping can create repeated branches and fallbacks | One typed normalization contract + declarative provider mapping where semantics are actually shared | fewer `if provider` branches, smaller read-set | flattening meaningful provider differences | provider fixtures + differential normalized outputs | AI Monitor | **MERGE / TABLE-DRIVE** |
| 8 | Replay/research evaluation can accumulate mutable orchestration | Increase pure `input -> evidence -> gate/result` seams around deterministic fixtures | faster OOS/replay and agent reasoning | creating a second production decision path | historical fixtures + OOS/differential checks | Radar | **SIMPLIFY / SHADOW** |
| 9 | Gate/status/reason enums and mappings may be duplicated across research/reporting boundaries | Inventory first; merge only identical semantic contracts into one registry/schema | less drift and fan-out | one giant “god enum” erasing bounded contexts | schema/serialization compatibility tests | Radar | **EVIDENCE NEEDED / MERGE candidate** |
| 10 | Agent sessions and tool outputs carry repeated context | Progressive disclosure + fresh-context tickets + durable handoff; Headroom only for protected Shadow compression | token/latency reduction | compressed evidence changes decisions | Critical Field Recall + gate/decision equivalence benchmark | Collaboration layer / owner-specific runtime | **ADAPT + SHADOW** |

## Three first differential plans

These are the first candidates that should receive measurable before/after evidence. They are **plans**, not implementation approval.

### D1 — Retry consolidation

**Hypothesis:** provider/API transport retry code can be shortened and made more consistent by using the existing `tenacity` dependency, without changing semantic-failure behavior.

**Before metrics:**

- number of retry implementations/call sites
- exception classes retried
- retry/backoff branches
- logging/telemetry behavior
- files an agent must inspect to change retry policy

**Differential harness:**

1. Freeze representative provider calls behind a deterministic fake.
2. Inject timeout/connection/transient status failures.
3. Separately inject entitlement, invalid payload, stale timestamp, and `UNKNOWN` semantic cases.
4. Old/new paths must produce identical externally observable success/failure semantics.
5. Semantic failures must not gain extra retries unless explicitly governed.

**Promotion gate:** fewer policy owners/branches with no semantic broadening of retry.

### D2 — Currentness transition model

**Hypothesis:** Currentness can be represented by one explicit transition/evaluation contract instead of distributed conditionals while preserving all market-session nuance.

**Compare:**

- existing logic
- a small local table-driven model
- optionally a `transitions`-based Shadow prototype

**Required fixture matrix:**

- before open
- open session
- lunch/session break
- after close
- timezone boundaries
- prior trading day
- missing timestamp
- malformed timestamp
- Futu `time_key` start/end unknown
- delayed 15m / 1h data

**Promotion gate:** 100% differential equivalence on accepted cases plus explicit, testable behavior for currently ambiguous cases. No false conversion of `UNKNOWN` into current.

### D3 — Realtime Monitor semantic-core extraction

**Hypothesis:** pure analytics/state/trigger semantics can become a smaller, explicitly testable read-set without changing the single AI Monitor runtime owner.

**Before metrics:**

- file/module read-set for a representative Currentness/trigger bug
- imports/dependencies needed by pure tests
- number of side-effectful dependencies crossed by tests
- semantic states/branches touched

**Candidate shape:**

`runtime adapters -> normalized immutable evidence -> pure state/trigger functions -> runtime delivery/persistence`

This is **not** permission to split the file by arbitrary technical layers. The cut must follow semantic/test seams and reduce the code an agent must understand for one class of change.

**Promotion gate:** differential outputs on captured fixtures, smaller read-set, no second runtime state owner, no change to persistence/restart semantics.

## Candidate metrics dashboard

Record these before and after any promoted simplification:

| Metric | Why it matters |
| --- | --- |
| production LOC touched | secondary size signal |
| distinct semantic state owners | duplicate truth is expensive |
| state values / transitions | catches hidden state-machine complexity |
| decision branches | approximates reasoning surface |
| files touched for one contract change | fan-out / shotgun-surgery signal |
| agent read-set (files + approximate lines/tokens) | direct development-speed signal |
| time to red-capable repro | debugging speed |
| deterministic replay coverage | confidence against semantic loss |
| UNKNOWN/fail-loud assertions | protects reliability |
| regression count after change | verifies simplification is real, not cosmetic |

## What we explicitly will not do

- Rewrite code merely because an external project is shorter.
- Introduce a generic framework before repeated semantics are proven.
- Move code into more files and call that simplification.
- Replace explicit `UNKNOWN` / `INDETERMINATE` with neutral defaults.
- Replace durable continuity/restart semantics with a tiny in-process scheduler.
- Let a research/backtesting library become a second production runtime.
- Compress raw evidence before critical-field retention and decision equivalence are measured.

## Control Tower first-wave sync

### AI_MONITOR/CONTROL_TOWER

**High-priority research queue:**

1. retry-policy ownership audit
2. Currentness transition inventory + adversarial fixture matrix
3. Delivery/entitlement/subscription state inventory
4. Realtime Monitor semantic read-set map
5. non-authoritative cache audit
6. provider normalization branch/mapping inventory

**Rule:** all resulting simplifications remain Shadow until differential evidence closes.

### RADAR/CONTROL_TOWER

**High-priority research queue:**

1. Replay/OOS mutable-state inventory
2. Candidate/Gate/status/reason schema duplication inventory
3. pure-function seams for research evaluation
4. backtesting/replay external pattern comparison

**Rule:** simplify research machinery without creating a second production decision owner.

### Cross-project status

- `initiative`: Minimal Core Initiative
- `status`: `ACTIVE / RESEARCH_ONLY`
- `production_change`: `NONE`
- `first_wave_decision`: `HARVEST + BASELINE + DIFFERENTIAL_PLANS`
- `next_gate`: quantified repository audit and evidence-backed owner-specific candidates
