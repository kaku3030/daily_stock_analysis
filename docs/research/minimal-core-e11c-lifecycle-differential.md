# Minimal Core E11-C — lifecycle/concurrency/read-set differential

**Mode:** Research / Shadow  
**Exact head under test:** `c3ef86225fa48b93907e1a6c7eaae6fa5ae79160`  
**Production-code diff:** NONE

## Evidence

The independent Shadow model covers initial miss, first write, hit before TTL,
strict TTL expiry, empty-but-non-`None` values, replacement, clear, negative
age, population exception with no write, HK-style lock/double-check behavior,
and failure-TTL versus positive-cache distinction. It records hit/miss/write/
clear events to keep observability part of the contract.

The provider inspection found:

| Provider/surface | Lifecycle and concurrency facts | Classification |
| --- | --- | --- |
| Efinance ordinary/ETF | global process-local snapshots; strict `< ttl`; provider-specific hit/miss/update logging; failed population is not committed by the ordinary path | `SHADOW_CANDIDATE` |
| AkShare ordinary/ETF | global process-local snapshots; failed ordinary fetches are converted to and cached as empty DataFrames; retry and circuit-breaker side effects are local | `KEEP_PROVIDER_LOCAL_BY_SEMANTICS` |
| AkShare HK | `failure_ttl`, `last_result`, fallback parsing, explicit lock, double-check, and failure logging | `KEEP_PROVIDER_LOCAL_BY_SEMANTICS` |
| Longbridge static info | per-instance, symbol-keyed cache and lock; configurable TTL; invalidation belongs to instance/session lifecycle | `KEEP_PROVIDER_LOCAL_BY_SEMANTICS` |
| Longbridge cooldown/token state | provider health/authentication state, not disposable data cache | `REJECT` |
| External `cachetools` | new dependency and owner with no deletion evidence | `REJECT` |
| Pure TTL predicate | matches only the already-proven boundary behavior | `DIRECT_USE_EXISTING_OWNER` |

## Protected counterexamples

- `None` is a miss, while empty/falsey non-`None` payloads can be hits.
- Exact TTL remains stale (`<`, not `<=`); negative age remains fresh.
- AkShare ordinary failure intentionally writes an empty DataFrame, while a
  generic positive-cache model would normally leave the entry absent.
- AkShare HK failure is a negative/failure memoization path, not a positive
  snapshot hit, and its lock controls race visibility and request count.
- Efinance/AkShare logs and circuit-breaker calls are provider-owned; moving
  them behind a helper would hide observability and retry policy.
- Longbridge cache scope, keys, restart/process-local lifetime, and credentials
  must not be widened into a shared owner.

## Measured outcome

- `semantic_owner_delta`: `0`; all provider lifecycle owners remain local.
- duplicated predicate/branch delta: `0` in production; Shadow adds one pure
  comparison model but deletes no provider branch.
- provider-local lifecycle branches removable: `0`.
- agent read-set delta: `NOT_MEASURED` (E06 protocol not reproducible in this
  projectless validation context).
- token delta: `NOT_MEASURED`.
- dependency delta: `0`.
- `net_complexity_result=UNKNOWN` for any production helper; promotion gate
  requiring `SMALLER` is not met.

## Terminal decision

`KEEP_PROVIDER_LOCAL_CACHE_SEMANTICS / SHADOW_EVIDENCE_ONLY`

Promotion flags: `PROMOTION_CANDIDATE=NO`,
`PRODUCTION_CACHE_REFACTOR_AUTHORIZED=NO`, `MERGE_AUTHORIZED=NO`.

Rollback is deletion of this test and document only; no runtime rollback is
needed. Sibling result: `SIBLING_CHECKED_NO_EQUIVALENT`. Revisit only if a
future exact-head experiment demonstrates deletion of provider lifecycle
branches and a smaller read-set while preserving these counterexamples.
