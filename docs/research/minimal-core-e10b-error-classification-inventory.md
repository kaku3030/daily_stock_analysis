# Minimal Core E10-B — Provider Failure-Surface Inventory

**Mode:** Research / Shadow  
**Production behavior change:** none  
**Goal:** identify which failure-classification branches are truly duplicated and therefore deletion candidates, without changing provider-owned retry/fallback/cooldown behavior.

## 1. Executive result

The repository does **not** currently have one uniform provider failure model. It has at least three materially different surfaces:

1. **Explicit classifier + preserved detail** — Efinance / AkShare.
2. **Broad exception wrapping into `DataFetchError`** — YFinance / Finnhub / AlphaVantage-style daily paths.
3. **Fail-soft return values** — several Futu methods return `None`, `[]`, or empty `DataFrame` after logging provider-native failures.

Therefore the first Minimal Core deletion candidate is **not** “replace every provider error path with one framework”.

The narrower candidate is:

> share only a tiny pure transport-failure classifier where the existing semantics are already demonstrably identical; leave control-flow policy and provider-native result semantics where they are.

`net_complexity_result` for a broad common error framework: **LARGER / REJECT**.  
`net_complexity_result` for a tiny shared Efinance/AkShare classifier: **UNKNOWN pending differential**.

---

## 2. Existing shared application error surface

`data_provider/base.py` already defines:

- `DataFetchError`
- `RateLimitError`
- `DataSourceUnavailableError`
- `unwrap_exception()`
- `summarize_exception()`

This is important: a future Minimal Core change should not introduce a second exception hierarchy just to obtain typed diagnostics.

Any shared failure-kind representation should either remain a pure diagnostic value or reuse the existing application error surface.

---

## 3. Inventory matrix

| Surface | Current behavior | Classification shape | Native detail | Policy coupling | Initial decision |
| --- | --- | --- | --- | --- | --- |
| Efinance Eastmoney | `_classify_eastmoney_error()` returns stable category + detail | keyword/type ladder | yes | caller owns retry/fallback | **MERGE CANDIDATE** with AkShare only |
| AkShare Sina/Tencent realtime | `_classify_realtime_http_error()` returns same narrow categories | keyword/type ladder | yes | separate transient retry/source fallback exists elsewhere | **MERGE CANDIDATE** with Efinance only |
| YFinance daily | catches broad `Exception`, rethrows `DataFetchError(... ) from e` | wrapper, no category enum | cause preserved | Tenacity decorator exists outside body | **KEEP / E03 AUDIT** |
| Finnhub daily | catches broad HTTP exception and wraps `DataFetchError`; no-data also `DataFetchError` | message-level distinction | cause preserved for HTTP | no shared retry classifier | **KEEP LOCAL** until need proven |
| AlphaVantage daily | wraps HTTP failure; separately encodes rate-limit/API/no-data in `DataFetchError` messages | provider payload semantics | partly | provider-specific API body | **KEEP LOCAL** |
| Tencent direct daily | `requests.raise_for_status()` propagates; empty/incomplete history becomes empty frame | no local taxonomy | native exception | manager fallback decides later | **KEEP LOCAL** |
| Futu HK paths | many calls log exception or non-RET_OK and return `None`/`[]`/empty frame | result-state / fail-soft | log only | availability/context semantics provider-specific | **KEEP / SEPARATE GOVERNANCE** |

This matrix is intentionally about **failure surface**, not whether a provider is “good” or “bad”.

---

## 4. Confirmed duplication seam: Efinance ↔ AkShare

The current E10-A Shadow test proves a narrow common category set for representative errors:

```text
remote_disconnect
timeout
rate_limit_or_anti_bot
request_error
unknown_request_error
```

Both existing classifiers also preserve native detail text.

### Candidate deletion

If broader differential evidence stays green, the following duplicated material is a legitimate DELETE candidate:

```text
remote_disconnect_keywords
timeout_keywords
rate_limit_keywords
same type/keyword branch ladder
```

The desired replacement is a **small pure helper**, not an error subsystem.

### Hard boundary

The helper must not know:

```text
attempt count
backoff
provider fallback order
circuit breaker
cooldown
provider admission
entitlement
currentness
delivery
```

If those concepts enter the helper, the simplification has failed.

---

## 5. Important non-duplication: provider API semantics

### AlphaVantage

The API can return HTTP success while the JSON body communicates:

- rate-limit (`Note`)
- API error (`Error Message`)
- no time-series data

These are not equivalent to generic transport keyword classification. A generic HTTP classifier cannot replace these branches without losing provider semantics.

### Finnhub

The daily path distinguishes request failure from a response whose `s != ok` or whose candle array is empty. Again, transport and data-unavailable semantics are separate.

### Futu

Futu uses SDK return codes/data emptiness and provider context state rather than normal HTTP exceptions. Entitlement/subscription semantics may also arrive through provider-specific channels. Mapping every Futu failure to a generic transport taxonomy would be semantic loss.

**Decision:** keep provider-native semantic interpretation adapter-local.

---

## 6. YFinance retry-surface finding

`YfinanceFetcher._fetch_raw_data()` is decorated to retry `ConnectionError` / `TimeoutError`, but the function body catches generic `Exception` and wraps non-`DataFetchError` failures in `DataFetchError` before they leave the body.

This creates a structural question for E03:

> does the Tenacity retry predicate ever observe the original transport exception on the ordinary wrapped path?

Do **not** “fix” this under E10. It belongs in Retry/Fallback semantics because changing the exception surface may change call count and provider fallback behavior.

Recommended next evidence:

```text
synthetic ConnectionError from yf.download
-> count calls
-> observe exception type at decorator boundary
-> compare decorated vs undecorated behavior
```

Until that test exists: **KEEP / UNKNOWN**.

---

## 7. Candidate failure-kind vocabulary

The broader vocabulary below remains research-only:

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

E10-B does **not** prove that all providers should emit all of these.

A provider-neutral classifier is justified only for the subset whose inputs and outputs are actually shared.

---

## 8. Promotion test plan

Before deleting the Efinance/AkShare duplicate ladder:

1. run current classifiers and a Shadow pure classifier against a larger corpus;
2. include exception subclasses plus keyword-only errors;
3. preserve native error type + message;
4. assert `UNKNOWN` remains explicit;
5. prove retry count/fallback/cooldown state is unchanged;
6. measure duplicated branch reduction and Agent read-set delta;
7. reject if the shared helper requires provider registration/hooks.

Suggested corpus additions:

```text
ChunkedEncodingError
ProtocolError text
ReadTimeout / ConnectTimeout
403 / forbidden
429 / too many requests
non-English anti-bot text
empty exception message
nested exception cause
provider-specific API semantic error (must stay local)
```

---

## 9. Delete-first conclusion

### Likely DELETE

- duplicated Efinance/AkShare transport keyword tuples and identical branch ladder, **only after E10-C/D differential passes**.

### KEEP

- provider API-body interpretation;
- Futu SDK result semantics;
- existing application-level `DataFetchError` hierarchy;
- retry/fallback/cooldown ownership;
- causal/native diagnostic evidence.

### REJECT

- plugin-based error registry;
- a second provider health state machine;
- a universal exception wrapper that turns `AUTH`, `ENTITLEMENT`, `DATA_UNAVAILABLE`, or `UNKNOWN` into generic transient failure.

The Minimal Core target is one tiny repeated classifier removed, not a new error architecture.