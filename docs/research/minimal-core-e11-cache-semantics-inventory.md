# Minimal Core E11 — Cache Semantics Inventory

**Mode:** Research / Inventory first  
**Production behavior change:** none  
**Rule:** cache simplification is allowed only for non-authoritative derived/reference data.

## Why E11 exists

Stock Razor contains several hand-written cache shapes. Some may share enough semantics to consolidate; others encode materially different behavior and must stay separate.

The experiment starts from semantics, not from a preferred cache library.

`cachetools` is **not currently declared in the root requirements**. It remains an external comparison candidate only.

## Confirmed cache examples

### Efinance full-market realtime caches

`data_provider/efinance_fetcher.py` maintains module-level timestamp dictionaries for:

- ordinary realtime quotes;
- ETF realtime quotes.

Current TTL shown in the provider module: 600 seconds.

These appear to be non-authoritative request-reduction caches around expensive/full-market provider calls.

### AkShare full-market realtime caches

`data_provider/akshare_fetcher.py` maintains similar module-level dictionaries for:

- ordinary realtime quotes;
- ETF realtime quotes;
- HK realtime quotes.

Current ordinary/ETF/HK success TTL shown in the provider module: 1200 seconds. HK additionally carries `failure_ttl`, `last_result`, and an explicit lock.

The HK cache therefore has richer failure/concurrency semantics than the simpler dictionaries.

### Longbridge static-info cache

`data_provider/longbridge_fetcher.py` documents a process-local `static_info` cache with a configurable default TTL of 86400 seconds.

This is reference/security metadata caching rather than market-currentness authority.

### Pipeline concept-ranking cache

`src/pipeline.py` owns an instance-local concept-ranking cache protected by a lock. Its lifetime and invalidation semantics differ from module-level provider caches.

## Not caches for Minimal Core purposes

Do **not** treat these as generic TTL caches merely because they contain time/state:

- provider circuit breakers;
- cooldown state;
- Currentness state;
- Portfolio State;
- Delivery/entitlement/subscription state;
- continuity/restart reconciliation state;
- lifecycle state;
- replay authority/provenance state.

Replacing any of these with a convenience cache would create a second or lossy state owner.

## Inventory schema

Every cache candidate must be classified with:

```text
owner
key/value shape
success TTL
failure TTL
thread-safety
stale-on-error behavior
negative caching?
max size / bounded?
eviction policy
source of truth
can be recomputed?
does cache content carry timestamps used for Currentness?
```

Only candidates whose answers materially match may share a primitive.

## First semantic groups

### Group A — full-market provider snapshots

Candidates:

- Efinance realtime;
- Efinance ETF realtime;
- AkShare realtime;
- AkShare ETF realtime.

Potentially shareable behavior:

```text
value + fetched_at + success_ttl
```

But compare lock behavior, stale-on-error behavior and provider-specific invalidation before proposing any helper.

### Group B — failure-aware expensive snapshots

Candidate:

- AkShare HK realtime.

Because this has `failure_ttl`/`last_result`/locking, do not force it into Group A unless differential evidence proves identical semantics can be expressed simply.

### Group C — static/reference metadata

Candidate:

- Longbridge `static_info`.

A generic TTL primitive may be useful here, but its security/credential/lifecycle context differs from market snapshots.

### Group D — per-run/per-instance memoization

Candidate:

- pipeline concept ranking cache.

This may not need TTL at all. A different lifetime can be simpler than a generic cache abstraction.

## Library comparison rule

Compare three options only after the inventory:

1. keep local dictionaries;
2. tiny repo-local helper;
3. external primitive such as `cachetools`.

Adding a dependency is justified only when it removes more semantic/code surface than it creates and does not obscure freshness behavior.

## Shadow metrics

Measure:

- duplicated timestamp/TTL branch count;
- duplicated locking/invalidation logic;
- failure semantics preserved;
- provider request count under replay;
- cache hit/miss equivalence;
- stale-on-error equivalence;
- Agent files/read-set required to understand cache behavior;
- dependency delta;
- resulting semantic owners.

## Promotion gate

A cache consolidation requires:

1. source-of-truth remains outside the cache;
2. Currentness cannot be inferred from cache TTL alone;
3. hit/miss/invalidation/failure behavior is differential-equivalent;
4. thread-safety is preserved;
5. no secret/credential persistence broadening;
6. code/read-set actually becomes smaller;
7. no new generic cache manager/service;
8. explicit rollback;
9. `net_complexity_result = SMALLER`.

## Likely outcome

E11 may legitimately conclude that two or three tiny cache primitives are simpler than one universal cache abstraction.

Minimal Core optimizes semantic complexity, not abstraction count.