# Minimal Core E10 — Failure Taxonomy Shadow Contract

**Mode:** Research / Shadow  
**Production behavior change:** none  
**Owner for any later production promotion:** AI Monitor  
**Evidence contributors:** AI_MONITOR/HARVEST + RADAR/PERCEPTION_DATA_INTELLIGENCE

## Why this experiment exists

Provider code currently contains repeated logic that classifies low-level failures such as disconnects, timeouts, rate limits and generic request errors. The duplication is a candidate for deletion, but only if the shared semantic core is real.

E10 is deliberately narrower than retry/fallback work:

```text
failure classification != retry policy != provider fallback != cooldown != routing
```

A shared taxonomy must never decide whether an operation is retried or whether another provider is selected.

## Current repository evidence

At least two provider-local classifiers expose nearly the same transport categories:

- `data_provider/efinance_fetcher.py::_classify_eastmoney_error`
- `data_provider/akshare_fetcher.py::_classify_realtime_http_error`

Both recognize the following shared surface today:

- `remote_disconnect`
- `timeout`
- `rate_limit_or_anti_bot`
- `request_error`
- `unknown_request_error`

The first executable evidence is `tests/test_minimal_core_e10_failure_taxonomy_evidence.py`. It compares both existing functions on the same exceptions and separately checks that provider-native error detail remains present.

This test is evidence only. Passing it does **not** authorize consolidation.

## What may be shared later

A future minimal primitive may classify only provider-neutral failure *kind*, for example:

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

The exact enum/string vocabulary is **not frozen** by this document.

The shared layer may return a tiny immutable value such as:

```text
kind
native_error_type
native_message
```

Provider-specific endpoint/context data remains with the provider adapter or diagnostic envelope.

## What must remain separate

The following are not allowed to become consequences of generic classification:

- whether Tenacity retries;
- number of attempts;
- retry delay/backoff;
- total time budget;
- source fallback order;
- circuit-breaker/cooldown mutation;
- entitlement/subscription handling;
- Currentness state;
- provider health/admission;
- Delivery retry semantics;
- `UNKNOWN` promotion to known state.

In particular, Efinance `stop_after_attempt(1)`, AkShare transient retry, Eastmoney → Sina → Tencent fallback, and Delivery no-retry remain distinct contracts unless their own governed experiments prove otherwise.

## Native evidence rule

Consolidation is rejected if a common classifier makes diagnostics less useful.

At minimum preserve:

- original exception type;
- original/native message or sanitized equivalent;
- provider/endpoint context from the caller;
- causal chain where currently available;
- unknown/unclassified failure as an explicit state.

Do not replace native evidence with only a generic category string.

## Shadow sequence

### E10-A — current-equivalence evidence

Use the same synthetic exceptions against existing provider-local classifiers.

Status at creation: **implemented as Shadow test**.

### E10-B — inventory

Search all provider/API surfaces for repeated keyword ladders and exception-to-category functions. For each site record:

```text
location
input exception classes
string heuristics
output category
does it mutate retry/fallback/cooldown?
native detail preserved?
```

### E10-C — pure prototype

Only after E10-B shows a true repeated semantic core, build a local pure prototype. No production callers.

### E10-D — differential

For every inventoried call site compare:

```text
existing category
shadow category
native error type
native detail retention
UNKNOWN/unclassified behavior
```

## Promotion gate

A production consolidation candidate requires all of:

1. category equivalence for existing governed behavior unless a defect is explicitly accepted;
2. native diagnostic evidence preserved;
3. retry/fallback/cooldown/routing behavior unchanged;
4. auth/entitlement/contract/unsupported failures cannot be accidentally treated as transient;
5. unknown failures remain explicit/fail-loud;
6. fewer duplicated classifier branches and smaller Agent read-set;
7. negative/adversarial tests;
8. explicit rollback;
9. `net_complexity_result = SMALLER`.

If the abstraction needs provider hooks, plugin registration, callback graphs or a second runtime error state owner, default decision is **REJECT / KEEP LOCAL**.

## Expected Minimal Core payoff

The desired end state is not a grand error framework. It is simply:

```text
provider native failure
        ↓
small pure classification helper
        ↓
provider-owned policy / diagnostics
```

If that shape cannot remain small, the duplicated local classifiers are cheaper and should stay.