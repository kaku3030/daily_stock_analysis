# MCI-E03 — Retry / Fallback Semantic Inventory

**Initiative:** Minimal Core V0.3  
**Owner for production promotion:** `AI_MONITOR/CONTROL_TOWER`  
**Mode:** research / Shadow only  
**Production behavior change:** none

## 1. Question

Where does Stock Razor currently retry, wait, fail over, cool down, or fail open — and which of those mechanisms can be simplified without changing semantic failure behavior?

The central rule is:

> Retry, provider failover, circuit breaking, cooldown, timeout, and fail-open are different semantics. Never merge them merely because they all happen after a failure.

## 2. First-pass evidence

### E03-F01 — Efinance Tenacity configuration is internally inconsistent

`data_provider/efinance_fetcher.py` imports Tenacity and decorates `_fetch_raw_data()` with:

```python
@retry(
    stop=stop_after_attempt(1),
    wait=wait_exponential(multiplier=1, min=4, max=60),
    retry=retry_if_exception_type(...),
    before_sleep=before_sleep_log(...),
)
```

Yet the module/class documentation still describes exponential-backoff retry and, in one place, “最多3次”.

**Finding:** `stop_after_attempt(1)` means there is no second provider attempt. The wait/backoff/before-sleep configuration is therefore operationally suspicious/dead for the normal retry path. However the decorator can still affect exception surface/wrapping, so deleting it without a differential test is unsafe.

**Decision:** `SHADOW → likely SIMPLIFY`, not immediate delete.

**Required test before promotion:** for each retryable exception class, compare current decorated behavior vs an undecorated single-attempt candidate:

- externally observed exception type;
- deepest/root exception;
- message/reason category;
- manager failover behavior;
- run diagnostics/circuit-breaker effects;
- elapsed-time bound.

### E03-F02 — AkShare has a real transport retry plus a separate source-failover loop

`AkshareFetcher._fetch_raw_data()` uses Tenacity with 3 attempts for `ConnectionError` / `TimeoutError` and exponential backoff. This is a genuine retry policy.

Separately, `_fetch_stock_data()` iterates Eastmoney → Sina → Tencent and catches a failed source before trying the next source.

These are not duplicates:

```text
same source transient retry
        !=
next source/provider fallback
```

**Decision:** `KEEP` the semantic distinction. Any refactor must make the distinction more explicit, not collapse the two loops into one generic “retry”.

**Audit question:** determine whether an inner source call can consume all retry/time budget before source failover, and whether rate-limit failures should retry the same source or fail over immediately.

### E03-F03 — DataFetcherManager has a bespoke budget-aware retry loop

`data_provider/base.py` implements `_run_with_retry()` for fundamental blocks. It obtains `fundamental_retry_max`, tracks `remaining_seconds`, calls `_run_with_timeout()`, subtracts consumed time, returns immediately on success, and otherwise retries until attempts or total budget are exhausted.

This mechanism is meaningfully different from a simple Tenacity decorator because **remaining stage budget is part of the contract**.

Current concern: the loop appears to retry any returned error uniformly; semantic classification is not visible in the retry loop itself.

**Decision:** `SHADOW`, not automatic Tenacity migration.

Two candidate implementations should be compared:

1. current hand-written loop;
2. a smaller policy implementation (Tenacity only if it can preserve total-budget behavior and error contract exactly).

Promotion requires lower semantic complexity, not merely fewer lines.

### E03-F04 — Delivery is intentionally single-attempt

The governed notification transport explicitly states single-attempt/no-retry semantics with bounded timeout.

**Decision:** `KEEP`. Do not route Delivery through a generic retry helper.

Reason: duplicate notifications and ambiguous delivery state are semantic risks, not merely transport inconvenience.

### E03-F05 — Futu mostly fails open instead of retrying

`FutuFetcher` initializes and caches an OpenQuoteContext, normalizes HK timestamps, and many read methods return `None`, `[]`, or empty DataFrames after provider failure. Context initialization failure can mark `_available = False`.

**Decision:** do not add generic retries. First classify:

- connection/transient failure;
- endpoint/config unavailable;
- entitlement/subscription failure;
- provider response empty;
- semantic invalidity;
- process/restart recovery.

Only the first category is a retry candidate by default.

### E03-F06 — Longbridge uses connection cooldown and headless-auth fail-loud behavior

Longbridge contains connection cooldown/config sanitization and explicit headless OAuth cache validation. Missing/invalid OAuth cache intentionally fails with a recovery message instead of attempting interactive authorization.

**Decision:** `KEEP` auth fail-loud semantics and treat reconnect/cooldown separately from request retry.

## 3. Taxonomy to enforce

| Failure/action | Meaning | Generic retry allowed? |
| --- | --- | --- |
| socket/connect timeout | transient transport | maybe, bounded |
| remote disconnect | transient transport | maybe, bounded |
| HTTP 429 / anti-bot | rate limit | policy-specific; often cooldown/failover |
| entitlement/subscription denied | semantic capability | **no** |
| auth invalid/missing | configuration/auth | **no** by default |
| stale/misaligned timestamp | data semantics | **no** |
| missing timestamp / UNKNOWN | evidence quality | **no** |
| provider returns empty valid result | domain-specific | not automatically |
| malformed schema | contract failure | **no** until classified |
| provider unavailable | capability/runtime state | failover/reconcile, not blind retry |
| notification send failure | governed delivery result | obey Delivery policy; currently single-attempt |

## 4. Minimal target model

Do **not** introduce a global retry framework. Prefer one small vocabulary at transport boundaries:

```text
FailureClass =
  TRANSIENT_TRANSPORT
  RATE_LIMIT
  AUTH
  ENTITLEMENT
  CAPABILITY
  DATA_QUALITY
  CONTRACT
  UNKNOWN
```

A retry policy may consume `TRANSIENT_TRANSPORT` only unless an explicit provider policy says otherwise.

This classification must not convert `UNKNOWN` into a retryable transient failure.

## 5. Differential experiment E03-A

For Efinance `_fetch_raw_data`:

1. inject `ConnectionError`;
2. inject `TimeoutError`;
3. inject `requests.RequestException`;
4. inject `RateLimitError`;
5. inject `DataFetchError` unsupported-market case;
6. compare current decorator vs Shadow single-attempt function;
7. assert manager fallback path and diagnostics are identical.

**Promotion condition:** only remove/simplify the decorator if every externally relevant field/exception/fallback path is equivalent and elapsed time is not worse.

## 6. Differential experiment E03-B

For `_run_with_retry`:

Use a deterministic fake task with outcomes:

```text
TIMEOUT → SUCCESS
CONNECTION_ERROR → SUCCESS
AUTH_ERROR → AUTH_ERROR
ENTITLEMENT_ERROR → ENTITLEMENT_ERROR
CONTRACT_ERROR → CONTRACT_ERROR
```

Measure:

- invocation count;
- total budget respected;
- final error/result;
- error category retained;
- no semantic error promoted to success by fallback;
- implementation/read-set complexity.

The experiment may conclude **KEEP current code**. Simplification is falsifiable.

## 7. Current decisions

| Surface | Current decision |
| --- | --- |
| Efinance `@retry(stop_after_attempt(1))` | **SHADOW / likely simplify after exception differential** |
| AkShare Tenacity transient retry | **KEEP pending budget audit** |
| AkShare Eastmoney/Sina/Tencent fallback | **KEEP as provider/source failover** |
| fundamental `_run_with_retry` | **SHADOW; classify errors before considering consolidation** |
| Delivery retry | **KEEP single-attempt** |
| Futu generic retry | **REJECT for now** |
| Longbridge auth retry | **REJECT; preserve fail-loud headless auth** |

## 8. Exit criteria

E03 can promote a code simplification only when:

- retry vs fallback vs cooldown vs fail-open semantics are explicit;
- exception/reason surface is preserved;
- total timeout budget is preserved;
- no `UNKNOWN`, entitlement, stale-data, or auth condition is retried as a transient success path;
- provider fallback sequence is unchanged unless separately governed;
- diagnostics remain auditable;
- targeted tests include success-after-transient and semantic-no-retry negative cases.

## 9. E03 completion packet — baseline `b8e50a1cfcd3aa6339d260997518349af672c52b`

The current exact head was re-fetched before the evidence run and did not move.
Sibling scan result: `SIBLING_CHECKED_NO_EQUIVALENT`. The five-lane delegation,
current-state, and open research assets were checked; E05, #85, and #89 were
not changed or reopened.

### Efinance differential matrix

The tests call `EfinanceFetcher._fetch_raw_data()` directly, with only its
actual `_fetch_stock_data` production dependency patched. `sleep_min=0` makes
elapsed behavior deterministic without waiting.

| injected failure | production attempts | surface | root/diagnostics | action |
| --- | ---: | --- | --- | --- |
| `ConnectionError` | 1 | `RetryError` | original exception retained by `unwrap_exception` | wrapper only; no second call |
| `TimeoutError` | 1 | `RetryError` | original timeout retained | wrapper only; no second call |
| `requests.RequestException` | 1 | `RetryError` | original request exception retained | wrapper only; no second call |
| `RateLimitError` | 1 | native `RateLimitError` | provider message retained | no generic retry |

Unsupported-market `DataFetchError` is also one call and remains a semantic
no-retry failure. The differential elapsed bound is under one second with no
sleep; the configured exponential wait is unreachable because
`stop_after_attempt(1)` prevents a before-sleep retry.

### AkShare, manager, and Delivery boundaries

`test_e03_akshare_transport_retry_is_distinct_from_provider_fallback` uses
the real `_fetch_stock_data` loop: an Eastmoney transient failure is followed
by Sina, proving provider failover is a separate outer action. The existing
AkShare `_fetch_raw_data` decorator remains the same-source retry owner; no
provider chain is folded into that decorator.

`DataFetcherManager._run_with_retry` was exercised directly through the real
method with a deterministic `_run_with_timeout` seam. With a 1.0-second
budget, costs of 400 ms then 700 ms produce exactly two attempts, return the
second error, and stop before a third attempt. An `AUTH_ERROR` is retained as
an error across the configured attempt count and is never converted to
success. This preserves total-budget-aware retry rather than replacing it with
a generic decorator.

Delivery remains single-attempt: `NotificationService.send_with_results`
iterates each selected static channel once and has no retry loop. A failed
channel is reported as one `ChannelAttemptResult`; its `retryable` diagnostic
does not cause an in-call resend. This is distinct from notification cooldown
and from provider retry/fallback.

The negative matrix is closed by native-path behavior and existing contract
owners: auth and entitlement failures remain semantic/configuration results;
stale/currentness `UNKNOWN` remains evidence-quality state; malformed or
validation/schema failures remain contract failures. None is added to the
Efinance/AkShare transport retry predicates or manager success path.

### Adjudication

`semantic_owner_delta=0`; `private_reach_through_delta=0`; `agent_read_set_delta`
was not measured in this run. `net_complexity_result=UNKNOWN`: the Efinance
decorator’s wrapper surface differs from the undecorated native surface, and
the manager’s budget semantics are not safely replaceable by a smaller generic
policy. No production refactor is authorized by this evidence packet.

Harvest decision: `KEEP_CURRENT_PRODUCTION`.

AI_MONITOR/CONTROL_TOWER adjudication: **KEEP CURRENT PRODUCTION**.

This closes the E03 evidence matrix without promoting a simplification. The
research tests are intentionally unmerged artifacts until the governed
promotion path authorizes a separately reviewed production change.
