# Minimal Core E11-B — TTL Boundary Differential

**Mode:** Research / Shadow  
**Exact head under test:** `6b1ad363c1c65fc075e3ac7f3df1fd5c77902d23`  
**Production behavior change:** none

## Scope

This probe covers only ordinary positive snapshot caches using the observed
predicate `data is not None and now - timestamp < ttl`. It compares a direct
translation of the existing predicate with the smallest proposed pure form.
It does not model AkShare HK `failure_ttl`, `last_result`, locking, cooldown,
provider admission, Currentness, or authoritative state.

## Evidence

The independent Shadow test covers:

| Boundary | Expected result |
| --- | --- |
| `ttl - epsilon` | fresh / hit |
| `ttl` | expired / miss |
| `ttl + epsilon` | expired / miss |
| `data is None` at age zero | miss |
| empty but non-`None` payload | hit |
| negative age | fresh, preserving current behavior |

The test passes only if the legacy and Shadow predicates agree at every point.

## Decision

`E11-B = SHADOW PASS` for the predicate boundary only. This is not enough to
authorize a production helper: thread ownership, refresh/write paths, clear
behavior, logging, and caller-specific TTL ownership still need differential
evidence. External `cachetools` remains rejected; a helper is justified only
if total owner/read-set complexity is smaller.

`net_complexity_result = UNKNOWN` pending the remaining dimensions.
