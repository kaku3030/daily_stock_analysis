# Minimal Core E03-B — YFinance Retry Surface

**Mode:** Research / Shadow  
**Production behavior change:** none

## Finding

`YfinanceFetcher._fetch_raw_data()` is decorated with Tenacity for up to three attempts when a `ConnectionError` or `TimeoutError` escapes the function.

Inside the function, however, ordinary non-`DataFetchError` exceptions are caught and re-raised as `DataFetchError(... ) from e`.

The Shadow test `tests/test_minimal_core_e03_yfinance_retry_surface.py` injects a synthetic `ConnectionError` from `yf.download()` and records the current behavior:

```text
yf.download
  -> ConnectionError
  -> function body catches it
  -> DataFetchError(cause=ConnectionError)
  -> Tenacity sees DataFetchError
  -> no second download attempt
```

This means the presence of `stop_after_attempt(3)` does not, by itself, prove that the ordinary wrapped transport path actually retries.

The expanded Shadow matrix records one provider call for `ConnectionError`,
`TimeoutError`, provider-raised `DataFetchError`, parser `ValueError`, and an
empty dataframe. Transport/parser failures surface as `DataFetchError` with the
original exception as `__cause__`; an already-created `DataFetchError` remains
the same object. The undecorated `__wrapped__` body instead exposes the native
transport exception. This causal/surface difference is compatibility-visible.

## Why this matters for Minimal Core

This is a potential **DELETE/SIMPLIFY** candidate, but not yet a fix candidate.

Three possible future decisions exist:

1. **KEEP current one-call behavior**, then remove/de-document ineffective retry machinery if differential evidence shows no other governed path depends on it.
2. **Restore real retry behavior**, but that is a behavior change and must be designed under E03 with rate-limit/fallback budgets.
3. **Narrow the exception wrapper** so retryable transport exceptions escape to Tenacity, again a behavior change requiring separate governance.

E03-B does not choose among them.

`net_complexity_result = UNKNOWN`: the call-count evidence supports a dead/no-op
retry-controller hypothesis, but does not prove that deleting the decorator and
its policy imports preserves the decorated exception surface.

## Hard constraints

Any production change must preserve or explicitly govern:

- total request budget;
- fallback ordering;
- rate-limit/anti-bot risk;
- causal exception detail;
- unsupported/data-unavailable behavior;
- manager-level fallback semantics;
- observability of call count.

Do not infer that “three retries is better”. A deliberate single-attempt path may be safer for a fragile provider.

## Next differential

Before Promotion review, test at minimum:

```text
ConnectionError
TimeoutError
DataFetchError raised by provider body
empty dataframe / no-data
non-transport provider exception
```

For each, record:

```text
actual call count
final exception type
root cause
manager fallback result
elapsed/retry budget
```

## Current status

`SHADOW EVIDENCE ONLY`.

The key Minimal Core question is now precise:

> If retry machinery is not behaviorally active on the intended path, can it be deleted without changing externally observed semantics?
