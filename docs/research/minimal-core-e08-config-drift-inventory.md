# Minimal Core E08 — Config Drift Inventory

**Mode:** Research / Shadow  
**Production behavior change:** none  
**Goal:** reduce duplicated configuration facts without collapsing useful responsibilities.

## Current configuration surfaces

Stock Razor currently spreads configuration concerns across several legitimate modules:

1. `src/config.py`
   - runtime parsing;
   - defaults;
   - normalization;
   - warnings/validation;
   - typed runtime access.

2. `src/core/config_registry.py`
   - Web/UI metadata;
   - field categories;
   - labels/descriptions;
   - validation hints;
   - examples/docs links.

3. `.env.example`
   - operator-facing discoverability;
   - examples;
   - comments explaining runtime behavior.

4. `src/core/config_manager.py`
   - `.env` read/write;
   - optimistic file versioning;
   - atomic replacement;
   - mounted-file rewrite fallback;
   - sensitive-value storage escaping.

These are not four copies of the same thing. E08 must distinguish duplicated **facts** from legitimately separate **responsibilities**.

## KEEP — ConfigManager is a deep module

`src/core/config_manager.py` has a narrow interface around non-trivial file semantics. Its atomic-write/fallback behavior should remain separate.

Minimal Core does **not** target fewer files. It targets fewer owners of the same semantic fact.

Decision for this responsibility: **KEEP**.

## Verified drift signal

`src/core/config_registry.py` currently contains documentation links to the historical upstream repository `ZhuLinsen/daily_stock_analysis` even though the canonical repository is now `kaku3030/stock-razor`.

This is a real example of a duplicated fact drifting because repository identity is embedded in individual metadata records.

The immediate lesson is not necessarily to generate every config file. It is:

> values that are globally invariant should have one owner or be derived from context.

Repository identity is one such fact.

## First bounded comparison set

Do not attempt to migrate the entire configuration system. Start with a small family that is represented across runtime config, registry and `.env.example`:

- `GENERATION_BACKEND`
- `GENERATION_FALLBACK_BACKEND`
- `GENERATION_BACKEND_TIMEOUT_SECONDS`
- `GENERATION_BACKEND_MAX_OUTPUT_BYTES`
- `GENERATION_BACKEND_MAX_CONCURRENCY`
- `LOCAL_CLI_BACKEND_MAX_CONCURRENCY`

For each field build a Shadow matrix:

```text
field
runtime default
runtime parser
runtime min/max/enum
registry default
registry validation
.env.example default/example
sensitive?
operator docs
```

No source is automatically declared authoritative until the comparison is complete.

## Candidate minimal model

Only if the bounded comparison proves repeated stable facts, test a small immutable `FieldSpec` concept with fields such as:

```text
id
value_kind
default
range/choices
sensitive
warning_codes
```

UI-only text and operator prose should not automatically be stuffed into the runtime schema. They can reference the stable field identity while retaining presentation ownership.

Avoid a mega-schema containing every UI sentence, runtime parser, migration rule and file-I/O concern.

## Anti-goals

E08 must not:

- replace `ConfigManager` atomic-write semantics;
- add Pydantic or another dependency merely to reduce lines;
- generate `.env.example` before proving generation lowers maintenance cost;
- silently change fallback/clamping behavior;
- centralize secrets into a more exposed representation;
- create a second runtime config object;
- turn warning behavior into hard errors without a separate contract change.

## Shadow measurements

Before and after any prototype measure:

- number of authoritative owners per field;
- number of repeated default literals;
- number of repeated enum/range definitions;
- number of stale documentation/repository references;
- files an Agent must inspect to safely change one field;
- tests needed to prove parity;
- whether UI/operator semantics become harder to understand.

## Promotion gate

A configuration simplification may advance only if:

1. runtime behavior is differential-equivalent for the bounded field set;
2. sensitive-value semantics are unchanged;
3. ConfigManager file-I/O responsibility remains singular;
4. one or more duplicated semantic owners are actually removed;
5. read-set decreases;
6. no new framework/dependency is required unless it replaces materially more complexity than it adds;
7. rollback is explicit;
8. `net_complexity_result = SMALLER`.

## Likely first deletion opportunity

Repository-specific documentation URLs should not be individually hard-coded across many field records when they can use repository-relative docs references or a single repository identity owner.

That is a better first E08 target than attempting a wholesale configuration rewrite.