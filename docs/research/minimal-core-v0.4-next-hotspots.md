# STOCK RAZOR Minimal Core V0.4 — Next Hotspots

**Mode:** Research / Shadow only  
**Production behavior change:** none  
**Purpose:** expand Minimal Core beyond E01/E03/E05/E06/E07 without duplicating work already delegated to existing lanes.

## 0. Evidence correction — repository truth wins

An earlier Harvest Ledger note described `cachetools` as an existing Stock Razor dependency. That is incorrect.

The root `requirements.txt` currently declares `tenacity` and `schedule`, but does **not** declare `cachetools`.

Therefore:

- `tenacity` → existing dependency, eligible for consolidation where semantics match;
- `schedule` → existing dependency, eligible only for simple/non-durable schedules;
- `cachetools` → **external comparison candidate**, not an installed dependency;
- no dependency should be introduced merely because it makes a prototype shorter.

This correction is a concrete example of the Minimal Core rule:

> Repo/runtime evidence is authoritative. Research notes and chat memory are not.

---

## 1. V0.4 scope

V0.4 opens five new research experiments:

| ID | Surface | Primary question | Initial decision |
| --- | --- | --- | --- |
| E08 | Config surface | can repeated config metadata become one governed schema without replacing good file-I/O semantics? | SHADOW |
| E09 | Pipeline/read-set | can the end-to-end analysis path expose explicit stage contracts without creating a workflow framework? | SHADOW |
| E10 | Failure taxonomy | can repeated provider error classification become a stable typed taxonomy while preserving native evidence? | SHADOW |
| E11 | Cache semantics | which manual TTL/cooldown caches share enough semantics to justify one primitive? | INVENTORY FIRST |
| E12 | Symbol semantics | can market classification/identity have one semantic owner while provider wire formats stay adapter-local? | SHADOW |

These experiments are deliberately orthogonal to the already delegated E01/E03/E05/E06/E07 work.

---

# E08 — Config Surface / Single-Source Metadata

## Current evidence

Stock Razor currently has several distinct configuration surfaces:

- `src/config.py` — runtime configuration parsing/defaults/validation;
- `src/core/config_registry.py` — UI metadata, validation hints, categories and docs links;
- `.env.example` — operator-facing examples/default documentation;
- `src/core/config_manager.py` — `.env` read/write, optimistic versioning and atomic replacement.

`src/core/config_registry.py` describes itself as the single source of truth for **UI metadata**, which is valid within that scope, but the same fields can still have defaults/options/validation/docs represented in other surfaces.

A concrete drift signal already exists: `config_registry.py` still contains documentation links pointing to the old upstream `ZhuLinsen/daily_stock_analysis` repository.

## Important KEEP

`src/core/config_manager.py` is comparatively narrow and has explicit atomic read/write semantics. Minimal Core must not collapse it into a giant schema object just to reduce file count.

**Decision:** `KEEP` the file-I/O/atomic-update responsibility as a separate deep module.

## Shadow hypothesis

For a small subset of config fields, test a declarative `FieldSpec`/schema that can become the authoritative owner of facts such as:

```text
field id
value type
runtime default
allowed values/range
sensitive flag
UI metadata
warning/error codes
operator example metadata
```

Do **not** generate production config yet. First compare the schema against current runtime parsing + config registry + `.env.example`.

## External lesson

Small config-schema projects such as `cfgv` / pre-commit demonstrate a useful pattern: declarative field definitions plus deterministic, human-readable validation. The transferable idea is the narrow schema vocabulary, not the dependency itself.

## E08 acceptance gate

Promote only if a pilot proves:

1. runtime defaults remain identical;
2. sensitive-field behavior remains identical;
3. UI options/validation remain identical;
4. warning/error codes remain stable;
5. `.env` atomic read/write stays owned by `ConfigManager`;
6. at least one duplicated field-definition surface is removed or generated rather than hand-maintained;
7. agent read-set for “add/change one config field” materially decreases.

---

# E09 — Pipeline Stage Contract / Read-Set

## Current evidence

`src/core/pipeline.py` is a broad orchestration surface. It coordinates data/provider access, storage, search, analysis, market context, guardrails, diagnostics, notification and persistence. `src/analyzer.py` is another large semantic surface covering model invocation, fallback, parsing, report integrity and related behavior.

Large files are **not** automatically a defect. Splitting one 200 KB file into twenty 10 KB files can make the read-set worse.

## Shadow hypothesis

Document the real common path as explicit stage contracts:

```text
Target/Input
   ↓
Fetch
   ↓
Normalize / Enrich
   ↓
Build Context
   ↓
Analyze / Generate
   ↓
Guardrail / Gate
   ↓
Persist Evidence / Result
   ↓
Notify / Present
```

For each stage record:

- canonical inputs;
- canonical outputs;
- state owner(s);
- I/O side effects;
- fail-open/fail-loud semantics;
- dependencies/read-set;
- retry/fallback responsibility;
- whether the semantic core can be pure.

The target is **not** a new workflow engine. The target is to make the existing execution path legible and identify pass-through layers or duplicated transforms.

## External lesson

Adapt the same principles seen in Sans-I/O/h11 and intentionally small explicit execution paths: put deterministic semantics in small testable functions, keep imperative I/O at the edge, and avoid abstractions that do not delete more complexity than they introduce.

## E09 acceptance gate

A proposed extraction must show one of:

- fewer semantic owners;
- fewer files required to modify/test one stage;
- removal of pass-through glue;
- deterministic replay for the extracted core;
- reduced fan-out without hiding side effects.

LOC reduction alone is not evidence.

---

# E10 — Stable Provider Failure Taxonomy

## Current evidence

Provider code already contains multiple exception/error classification layers:

- Efinance `_classify_eastmoney_error()` classifies disconnect, timeout, rate-limit/anti-bot, request error and unknown request error;
- AkShare `_classify_realtime_http_error()` contains a very similar keyword/type ladder;
- `data_provider/base.py` defines `DataFetchError`, `RateLimitError`, `DataSourceUnavailableError`, exception unwrapping and stable summary helpers;
- E03 separately distinguishes retry, fallback, cooldown and no-retry semantics.

The repeated keyword ladders are a candidate for semantic consolidation, but provider-native evidence must remain visible.

## Shadow taxonomy

Research a small stable value taxonomy, for example:

```text
TRANSIENT_TIMEOUT
REMOTE_DISCONNECT
RATE_LIMIT
AUTH
ENTITLEMENT
PROTOCOL
CONTRACT
UNSUPPORTED
DATA_UNAVAILABLE
UNKNOWN
```

A normalized failure record should retain:

```text
category
provider
operation/capability
retryable?        (derived by governed policy, not guessed by callers)
native_exception_type
native_detail / sanitized evidence
elapsed
```

Do not make `retryable` equivalent to category name by accident; E03 remains authoritative for retry/fallback policy.

## External lesson

HTTPX/httpcore use a typed exception hierarchy and explicit mapping rather than forcing every caller to maintain its own substring ladder. The transferable idea is the hierarchy/mapping boundary. Stock Razor does **not** need to switch provider networking stacks just to copy it.

## E10 acceptance gate

- same retry/fallback/circuit-breaker outcomes under differential fixtures;
- same or better provider-native diagnostic detail;
- no `UNKNOWN` upgraded to a known category without evidence;
- fewer duplicate keyword ladders;
- one stable taxonomy owner;
- no generic exception wrapper that destroys root causes.

---

# E11 — Cache Semantics Inventory

## Current evidence

Manual process-local cache/cooldown patterns already exist, including:

- Efinance realtime cache + ETF realtime cache with timestamp/TTL dictionaries;
- AkShare realtime cache + ETF cache + HK cache with success TTL, failure TTL, `last_result` and locking;
- Longbridge static-info TTL plus connection cooldown;
- additional caches in pipeline/services with domain-specific semantics.

These structures are superficially similar but **not automatically equivalent**.

## Inventory first

For every candidate cache record:

| Field | Meaning |
| --- | --- |
| owner | module/component that owns it |
| key | cache key semantics |
| value | cached object/evidence |
| success_ttl | successful result TTL |
| negative_ttl | failure/not-found TTL |
| cooldown | provider-health behavior, if any |
| timer | wall clock vs monotonic |
| lock | concurrency semantics |
| bound | max entries / unbounded |
| invalidation | explicit invalidation behavior |
| authoritative | whether it can influence runtime truth |
| currentness_risk | whether stale cache can create false currentness |

## Candidate comparison

Only after inventory compare three alternatives:

1. KEEP current local implementation;
2. a tiny repo-local reusable TTL primitive;
3. external `cachetools` or another proven primitive.

`cachetools` is currently **not installed**. Adding it must demonstrate lower total semantic cost than a tiny local helper.

## Hard exclusions

Never treat these as ordinary cache-cleanup targets:

- Portfolio runtime truth;
- Currentness authoritative state;
- Delivery/entitlement/subscription state;
- Trade Lifecycle authoritative state;
- restart/continuity reconciliation state.

## E11 acceptance gate

A common cache primitive is justified only if at least two real call sites share the same TTL/invalidation/concurrency semantics and the common primitive reduces tests + code + read-set without weakening observability/currentness.

---

# E12 — Symbol Semantics Consolidation

## Current evidence

Symbol/market semantics are distributed across multiple layers:

- `data_provider/base.py`: `normalize_stock_code`, market classification, ETF/BSE detection;
- `AkshareFetcher`: `_is_hk_code`, `_is_etf_code` and provider symbol conversion;
- pipeline `_symbol_scope_lookup_values`: persisted-intelligence alias expansion;
- individual providers: wire-format converters such as Futu HK symbol mapping;
- `src/services/market_symbol_utils.py`: already provides a good dependency-light table-driven semantic owner for suffix-only JP/KR/TW markets.

Comments that two implementations “must stay aligned” are a strong signal that an executable shared contract may be missing.

## Target separation

Do **not** put all symbol behavior into one giant utility.

Use three explicit layers:

```text
1. Canonical identity + market classification
   → one shared semantic owner

2. Storage/search alias expansion
   → one explicit alias contract

3. Provider wire symbol conversion
   → remains provider-adapter local
```

Provider-native wire quirks must stay at the edge. Futu, AkShare, Tencent, Yahoo, etc. do not have to share the same API symbol format.

## Golden fixture family

At minimum cover:

- A-share stock;
- A-share ETF;
- BSE forms;
- registered A-share indices and collision-prone forms;
- HK: `00700`, `HK00700`, `1810.HK`, padded/unpadded forms;
- US equity and US index identities;
- JP `.T`;
- KR `.KS/.KQ`;
- TW `.TW/.TWO`;
- invalid/ambiguous numeric symbols.

## E12 acceptance gate

- all existing canonicalization/routing fixtures pass;
- provider wire conversions remain adapter-local;
- fewer duplicated classification functions/comments;
- persisted lookup aliases remain backward-compatible;
- no index→stock identity degradation;
- read-set for adding one market/symbol form decreases.

---

# 2. Ownership / delegation

V0.4 does not create a new lane.

### AI_MONITOR/HARVEST

- E10 failure taxonomy research;
- E11 provider/runtime cache inventory;
- contribute E08 runtime-config evidence where AI/runtime settings are involved.

### AI_MONITOR/CONTROL_TOWER

- production-owner review for E08/E10/E11 where runtime/provider semantics are affected;
- no production promotion until differential evidence is complete.

### RADAR/HARVEST

- E09 read-set/stage-contract research;
- external small-core references;
- E12 generic symbol-contract/read-set study where useful.

### RADAR/PERCEPTION_DATA_INTELLIGENCE

- E12 market/symbol semantic fixtures;
- E10 provider-native error/availability evidence;
- E11 timestamp/currentness risk evidence;
- no second runtime owner.

### RADAR/CONTROL_TOWER

- verify E09/E12 changes do not alter Candidate/Gate/Replay/Lifecycle semantics;
- review cross-lane conflicts.

---

# 3. Priority

Do not start all five implementation prototypes at once.

Recommended research order:

```text
E12 Symbol Contract audit
        +
E10 Failure Taxonomy audit
        ↓
E11 Cache Inventory
        ↓
E08 Config Pilot
        ↓
E09 Pipeline Stage Map
```

Why:

- E10/E12 have clear duplicated semantic surfaces and strong fixture opportunities;
- E11 must inventory before abstracting;
- E08 has high leverage but config compatibility has a wide blast radius;
- E09 is potentially the biggest read-set win, but should start as mapping rather than refactoring.

---

# 4. V0.4 invariant

> A new abstraction is a failure unless it removes more semantic complexity than it adds.

For every V0.4 candidate report both sides:

```text
Removed:
- branches
- duplicate definitions
- private reach-throughs
- files/semantic owners in read-set
- bespoke tests/glue

Added:
- new types/interfaces
- new dependencies
- indirection
- migration burden
- new failure modes
```

Promotion requires the net result to be meaningfully smaller **and** at least as reliable.
