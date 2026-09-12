# Minimal Core External Harvest Ledger V0.2

**Status:** canonical external-reference ledger for the Minimal Core Initiative  
**Mode:** research only; no vendoring or production replacement from this ledger alone  
**Status:** durable harvest ledger; the earlier ledger was superseded and removed from the mainline read-set.

## Governing rule

Harvest **design leverage**, not popularity.

An external project is useful only when its transferable idea can reduce Stock Razor semantic complexity without weakening:

- runtime truth;
- `UNKNOWN` / `INDETERMINATE`;
- Currentness;
- entitlement/subscription evidence;
- risk/gate/reason semantics;
- replay/auditability;
- single production ownership.

A shorter implementation that adds hidden semantics is not Minimal Core.

---

## Repository-truth correction

The previous ledger incorrectly stated that `cachetools` was already a Stock Razor dependency.

Current root `requirements.txt` truth:

- `tenacity` — installed/declaratively required;
- `schedule` — installed/declaratively required;
- `cachetools` — **not declared**.

Therefore `cachetools` is an **external comparison candidate**, not an existing dependency to consolidate.

---

## Canonical decision matrix

| Source / pattern | Transferable lesson | Razor target | Decision |
| --- | --- | --- | --- |
| `mattpocock/skills` | phase separation, context pointers, fresh-context tickets, handoff | agent workflow | **ADAPT** |
| `headroomlabs-ai/headroom` | compress repetitive LLM-facing tool output | logs/JSON/tool results | **SHADOW** |
| `karpathy/micrograd` | tiny semantic object + composition | pure decision/replay cores | **ADAPT principles** |
| `karpathy/nanoGPT` | obvious end-to-end path, little indirection | orchestration/read-set | **ADAPT principles** |
| `karpathy/llama2.c` | explicit execution path, abstractions must earn cost | runtime hot paths | **ADAPT principles** |
| `tinygrad/tinygrad` | small composable primitives / transformations | normalization/research | **ADAPT / SHADOW** |
| `h11` / Sans-I/O | deterministic protocol/state logic without I/O | Currentness/trigger/delivery semantic cores | **ADAPT strongly** |
| `pytransitions/transitions` | declare legal state graph once | state-machine candidates | **SHADOW** |
| `jd/tenacity` | explicit retry/backoff policy vocabulary | transient provider/API failure | **ADOPT where semantics match** |
| `dbader/schedule` | tiny in-process scheduler | simple non-durable chores | **KEEP / ADOPT narrowly** |
| `cachetools/cachetools` | explicit bounded/TTL cache primitive | non-authoritative caches | **COMPARE; not installed** |
| `simonw/llm` | thin provider boundary, extensions at the edge | AI/model adapters | **ADAPT** |
| `kernc/backtesting.py` | compact deterministic research loop | Replay/OOS/Strategy Lab | **SHADOW only** |
| Trio structured concurrency | task lifetime/ownership is structural | worker lifecycle research | **STUDY / SHADOW** |
| HTTPX/httpcore exception hierarchy | typed transport failure taxonomy | provider failure normalization | **ADAPT pattern** |
| `cfgv` / pre-commit config validation | small declarative schema + deterministic errors | config metadata/validation | **ADAPT pattern** |

---

## Transfer rules

### Agent workflow — Matt Pocock

Keep the concepts already adapted into Razor:

```text
clarify/design → spec → tickets → fresh implementation context → tests → review → handoff
```

Use repo context pointers instead of repeating durable rules in every prompt.

Do not import another issue-tracker/process framework that competes with `AGENTS.md` or Razor governance.

### Tool-output compression — Headroom

Only LLM-facing projection is eligible:

```text
Canonical raw evidence
       ↓
Governed normalization / canonical state
       ↓
protected-field classifier
       ↓
optional compression
       ↓
LLM
```

Never:

```text
provider payload → lossy compression → canonical truth
```

Protected fields include timestamps, timezone/session evidence, `UNKNOWN`, entitlement/subscription, gate/candidate state, reason/risk fields, portfolio/lifecycle identifiers and retry/fallback/cooldown evidence.

### Small semantic core — Karpathy / tinygrad / h11

Use small, explicit deterministic cores where semantics are stable. Keep I/O, persistence, SDK quirks and runtime lifecycle at the edges.

Do not confuse “one readable execution path” with “put everything in one giant file”.

### State machines — transitions

A state machine is useful only when the domain is actually a state graph. Compare a local enum/table implementation with a library prototype. Do not add a dependency just to replace a few readable conditions.

### Retry — Tenacity

Tenacity is already installed, but only transient transport-like failures are candidates for consolidation.

Keep distinct:

```text
transient retry
provider/source fallback
cooldown/circuit breaker
budget-aware retry
intentional no-retry
```

Never retry semantic invalidity, stale/UNKNOWN evidence, entitlement/auth failure or contract failure by default.

### Scheduling — schedule

Already installed. Appropriate for simple in-process non-durable jobs only.

Reject it as a replacement for restart-aware continuity, market-session semantics or authoritative runtime reconciliation.

### Cache primitives — cachetools

`cachetools` is **not installed**. Before adding it, E11 must show that multiple real call sites share the same TTL, negative-cache, invalidation, locking and bounding semantics.

Compare:

1. keep local logic;
2. tiny repo-local primitive;
3. external cache library.

Never turn Portfolio, Currentness, Delivery, Lifecycle or continuity truth into an ordinary cache.

### Provider/AI boundaries — Simon Willison `llm`

Transfer the idea of a small central invocation contract with provider-specific quirks at the edge. Do not introduce a generic plugin framework unless a real extension problem proves it lowers total complexity.

### Replay research — backtesting.py

Useful only as a design reference for deterministic research loops. It must not become a second production trading runtime or bypass Strategy Lab/Lifecycle governance.

### Structured concurrency — Trio

Study ownership/lifetime concepts for workers and restart/reconciliation. Do not migrate async runtime merely because another concurrency model is elegant.

### Failure taxonomy — HTTPX/httpcore

Transfer the typed hierarchy/mapping concept, not necessarily the HTTP client. Stock Razor should preserve provider-native details while giving higher layers a small stable failure category vocabulary.

### Config schema — cfgv/pre-commit style

Transfer small declarative field definitions and deterministic errors. Do not replace `ConfigManager` atomic `.env` read/write semantics with a schema framework.

---

## Current experiment mapping

| Experiment | External ideas most relevant |
| --- | --- |
| E01 Currentness Differential Replay | h11/Sans-I/O, state tables |
| E03 Retry/Fallback Inventory | Tenacity, typed failure taxonomy |
| E05 Provider Escape Surface | thin adapter boundaries, deep modules |
| E06 Agent Read-set / Token | Matt workflow, explicit execution paths |
| E07 Tool-output Compression | Headroom |
| E08 Config Surface | cfgv/pre-commit-style declarative schemas |
| E09 Pipeline Stage Contract | h11, Karpathy explicit path, deep modules |
| E10 Provider Failure Taxonomy | HTTPX/httpcore typed hierarchy |
| E11 Cache Semantics | local primitive vs cachetools comparison |
| E12 Symbol Semantics | table-driven shared semantic owner + adapter-local wire formats |

---

## Promotion order

1. **Existing-dependency consolidation:** `tenacity` and `schedule` only where semantics already match.
2. **Pure semantic-core comparison:** Currentness/state/symbol/failure classification with differential fixtures.
3. **Read-set reduction:** stage contracts, config metadata ownership, provider boundaries.
4. **Cache consolidation:** only after E11 inventory; `cachetools` remains optional external candidate.
5. **Tool-output compression:** Headroom remains Shadow until protected-field and decision equivalence gates pass.
6. **Replay/backtest references:** research-only unless separately governed.

---

## Next questions

- Which repeated provider error classifiers can share one taxonomy without changing retry/fallback policy?
- Which manual TTL dictionaries genuinely share the same cache semantics, and should the common primitive be local or external?
- Can canonical symbol classification have one owner while provider wire-symbol conversion stays adapter-local?
- Can config default/validation/UI metadata be derived from one small schema for a pilot subset?
- What is the minimum file/read-set needed to understand one pipeline stage safely?
- Which abstractions can be deleted after the above semantic owners become explicit?

## Anti-pattern check

Before adopting any external idea ask:

> Does this remove more semantic owners, branches, duplicated definitions and read-set than the new abstraction/dependency adds?

If the answer is not demonstrably yes, keep it in research or reject it.
