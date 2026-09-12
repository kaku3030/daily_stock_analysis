# Minimal Core E11-A — Cache Semantic Matrix

**Mode:** Research / Shadow  
**Production behavior change:** none

## Result

The current provider caches are **not one cache problem**. At least five different semantics are present or adjacent:

```text
market snapshot convenience cache
reference/static metadata cache
negative/failure memoization
connection cooldown/health state
credential/token persistence
```

Only the first two are ordinary cache candidates. Cooldown, health and credentials must not be collapsed into a generic TTL cache.

`net_complexity_result` for “replace everything with cachetools”: **LARGER / REJECT** at this stage.

---

## Inventory

| Surface | Key/value shape | TTL | Failure state? | Authoritative? | Initial decision |
| --- | --- | ---: | --- | --- | --- |
| Efinance realtime snapshot | global `{data,timestamp,ttl}` | 600s | no explicit failure TTL | no | compare with AkShare simple snapshot |
| Efinance ETF realtime snapshot | same global shape | 600s | no | no | duplicate local shape candidate |
| AkShare realtime snapshot | global `{data,timestamp,ttl}` | 1200s | no | no | compare with Efinance |
| AkShare ETF realtime snapshot | same | 1200s | no | no | duplicate local shape candidate |
| AkShare HK realtime | global cache + lock + `failure_ttl` + `last_result` | 1200s / failure 30s | **yes** | no | KEEP separate until negative-cache semantics proven |
| Longbridge static info | per-instance `symbol -> (StaticInfo,timestamp)` + lock | default 86400s | no | no | keyed reference cache; different shape |
| Longbridge connection cooldown | `_cooldown_until` | default 15s | **health state** | affects availability | **NOT A CACHE** |
| Longbridge OAuth token file | durable SDK credential material | provider-managed | auth state | security-sensitive | **NOT A DATA CACHE** |

---

## Important separation

### Convenience market-data cache

Purpose:

> avoid repeated expensive full-market/network requests inside a short analysis window.

These caches are disposable. Cache miss should lead to a normal provider fetch, not a change in canonical Portfolio/Currentness/Lifecycle state.

### Reference/static metadata cache

Longbridge static info is keyed by symbol and has a much longer lifetime. Its behavior is closer to a normal keyed TTL cache than the global all-market snapshot dictionaries.

### Negative/failure memoization

AkShare HK `failure_ttl` / `last_result` is not equivalent to a normal positive cache. It prevents repeated expensive/failing calls and therefore can affect retry pressure.

If generalized incorrectly it could become hidden provider admission state.

### Cooldown / health

Longbridge `_cooldown_until` changes whether reconnection/provider use is attempted. That is runtime health policy, not cache eviction.

**Hard rule:** E11 must never use a cache abstraction to hide cooldown or provider-health transitions.

### Credential/token cache

OAuth token persistence is security/authentication state. It is entirely out of scope for data-cache simplification.

---

## First real DELETE candidate

The strongest low-risk candidate is the repeated positive snapshot shape in Efinance/AkShare:

```text
{
  "data": ...,
  "timestamp": ...,
  "ttl": ...,
}
```

Before introducing any library, compare whether a tiny local primitive can replace only the repeated mechanics:

```text
get_if_fresh(now)
set(value, now)
clear()
```

Configuration such as 600s vs 1200s remains caller-owned.

If the helper becomes longer than the duplicated mechanics, **KEEP LOCAL**.

---

## Why no new dependency yet

`cachetools` is not currently a root dependency.

Adding it would incur:

```text
dependency surface
version/security maintenance
new API knowledge for agents
migration risk
```

For two or four tiny dictionaries, a 20–40 line local tested primitive may be smaller overall—or keeping the dictionaries may still be smallest.

Therefore E11 evaluates:

```text
KEEP LOCAL
vs tiny local primitive
vs external library
```

in that order.

---

## Shadow comparison dimensions

For every candidate cache record:

```text
owner
scope (global / instance / symbol / provider)
positive vs negative cache
TTL clock source
thread safety
cache-miss behavior
failure behavior
clear/invalidation triggers
restart semantics
whether stale value can affect Currentness
whether state changes provider admission/routing
```

Any cache that changes provider admission/routing belongs to Provider/Health governance, not generic E11 consolidation.

---

## Explicit forbidden targets

Never reinterpret these as ordinary cache state:

```text
Portfolio State
Currentness
Delivery / Entitlement / Subscription
Lifecycle
Continuity / RecoveryCandidate
Risk Budget
Gate result
provider cooldown / circuit health
```

These are governed state or evidence, not performance optimizations.

---

## Promotion gate

A cache simplification candidate requires:

1. identical freshness boundary behavior;
2. identical thread-safety behavior;
3. same failure/miss semantics;
4. no routing/currentness/provider-health behavior change;
5. no new source of truth;
6. smaller code/read-set after accounting for abstraction/dependency cost;
7. adversarial boundary tests at `ttl-ε`, `ttl`, `ttl+ε` where relevant;
8. restart behavior documented;
9. `net_complexity_result = SMALLER`.

## Current recommendation

- **SHADOW** a tiny positive snapshot-cache primitive for Efinance/AkShare only.
- **KEEP** AkShare HK negative/failure semantics separate initially.
- **KEEP** Longbridge static cache separate until keyed-cache repetition appears elsewhere.
- **REJECT** treating cooldown, credentials or authoritative runtime state as cache.

The Minimal Core win here is likely modest deletion of repeated timestamp-dictionary mechanics—not a cache subsystem.

Current result: `net_complexity_result = UNKNOWN`. The existing Shadow test
covers the strict TTL boundary and basic positive/miss behavior only; it does
not establish equivalent write, clear, locking, logging, restart, or total
read-set semantics. No helper or dependency is justified by this evidence.
