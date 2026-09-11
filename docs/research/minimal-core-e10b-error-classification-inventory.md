# Minimal Core E10-B/C — Provider Failure-Surface Inventory + Differential

**Mode:** Research / Shadow  
**Production behavior change:** none  
**Goal:** identify which failure-classification branches are truly duplicated and therefore deletion candidates, without changing provider-owned retry/fallback/cooldown behavior.

## 1. Executive result

The repository does **not** currently have one uniform provider failure model. It has at least three materially different surfaces:

1. **Explicit classifier + detail** — Efinance / AkShare.
2. **Broad exception wrapping into `DataFetchError`** — YFinance / Finnhub / AlphaVantage-style daily paths.
3. **Fail-soft return values / SDK results** — several Futu methods return `None`, `[]`, or empty `DataFrame` after logging provider-native failures.

A broad common error framework remains **LARGER / REJECT**.

A narrow Efinance/AkShare shared transport helper is still worth studying, but E10-C proves that the two current classifiers are **not fully equivalent**. Therefore direct deduplication is **not yet a safe DELETE**.

`net_complexity_result` for a tiny shared classifier: **UNKNOWN / SHADOW MORE**.

---

## 2. Existing shared application error surface

`data_provider/base.py` already defines:

- `DataFetchError`
- `RateLimitError`
- `DataSourceUnavailableError`
- `unwrap_exception()`
- `summarize_exception()`

Do not introduce a second exception hierarchy merely to obtain typed diagnostics.

A future shared failure-kind helper, if justified, should be a pure diagnostic primitive and must not become a second provider-health or retry owner.

---

## 3. Inventory matrix

| Surface | Current behavior | Classification shape | Policy coupling | Decision |
| --- | --- | --- | --- | --- |
| Efinance Eastmoney | category + native detail | keyword/type ladder | caller owns retry/fallback | **SHADOW MORE** |
| AkShare Sina/Tencent realtime | same broad category vocabulary, but not identical edge semantics | keyword/type ladder | separate retry/source fallback | **SHADOW MORE** |
| YFinance daily | broad catch -> `DataFetchError(... ) from e` | wrapper | Tenacity decorator outside body | **KEEP / E03 AUDIT** |
| Finnhub daily | HTTP wrapper + separate no-data response semantics | provider-specific | local | **KEEP LOCAL** |
| AlphaVantage daily | HTTP wrapper + JSON body rate-limit/API/no-data semantics | provider-specific | local | **KEEP LOCAL** |
| Tencent direct daily | native `raise_for_status`; empty/incomplete history -> empty frame | no local taxonomy | manager fallback later | **KEEP LOCAL** |
| Futu HK paths | SDK result/fail-soft `None`/`[]`/empty frame | provider SDK semantics | availability/context | **KEEP / SEPARATE GOVERNANCE** |

---

## 4. E10-C differential result — common core exists, exact equivalence does not

The expanded Shadow corpus confirms a shared category surface for representative cases:

```text
remote_disconnect
timeout
rate_limit_or_anti_bot
request_error
unknown_request_error
```

Shared examples currently agree for:

- `RemoteDisconnected` text;
- `ProtocolError` / connection-broken text;
- `Timeout`, `ReadTimeout`, `ConnectTimeout`;
- HTTP 403/forbidden;
- HTTP 429/too-many-requests;
- Chinese frequency-limit text;
- generic `RequestException`;
- ordinary unknown exception.

However two current divergences are now permanently recorded in `tests/test_minimal_core_e10_failure_taxonomy_evidence.py`.

### Divergence A — `ChunkedEncodingError`

AkShare explicitly includes `chunkedencodingerror` in its remote-disconnect keyword set.

Current result:

```text
Efinance -> request_error
AkShare  -> remote_disconnect
```

Therefore the previous shorthand “identical branch ladder” was too strong and is superseded by this document.

### Divergence B — empty exception detail

For `ValueError("")` both classify as `unknown_request_error`, but diagnostic detail differs:

```text
Efinance -> ""
AkShare  -> "ValueError"
```

This matters because Minimal Core must not silently degrade or rewrite native diagnostic evidence.

---

## 5. Revised deletion candidate

The candidate is no longer “delete one classifier and call the other”.

The only safe next candidate is:

> build a tiny **Shadow** pure classifier that explicitly chooses governed edge semantics, then differential-test every existing call site before considering production deletion.

A production consolidation would need an explicit decision for `ChunkedEncodingError` and empty-detail normalization. That decision would be a semantic change for at least one provider unless the helper preserves provider-local override behavior—which may erase the complexity win.

If provider overrides/hooks are required, default decision becomes **KEEP LOCAL**.

---

## 6. Provider-native semantics stay local

### AlphaVantage

HTTP success can still carry provider failure in JSON:

- `Note` -> rate limit;
- `Error Message` -> provider API error;
- missing time-series -> no data.

A generic transport classifier cannot replace these branches.

### Finnhub

Request failure is different from a response whose `s != ok` or whose candle array is empty.

### Futu

SDK return codes, context availability, data emptiness and entitlement/subscription semantics are not ordinary HTTP transport errors.

**Decision:** provider-native semantic interpretation remains adapter-local.

---

## 7. YFinance retry-surface evidence moved to E03-B

`YfinanceFetcher._fetch_raw_data()` is decorated to retry `ConnectionError` / `TimeoutError`, but the ordinary body catches generic `Exception` and wraps it in `DataFetchError` before it escapes.

`tests/test_minimal_core_e03_yfinance_retry_surface.py` now pins a synthetic `ConnectionError` path with **one** observed `yf.download()` call.

This is a Retry/Fallback question, not an E10 classification fix.

---

## 8. Promotion gate

Before deleting either Efinance/AkShare local classifier:

1. define the intended behavior for every currently divergent case;
2. compare existing vs Shadow category, native type and detail;
3. prove retry/fallback/cooldown/routing call counts are unchanged;
4. keep provider API-body/SDK semantics outside the helper;
5. keep `UNKNOWN` explicit;
6. measure duplicated branch/read-set reduction;
7. reject plugin hooks/registries unless they still make the net system smaller;
8. require negative/adversarial tests and rollback;
9. require `net_complexity_result = SMALLER`.

---

## 9. Current decision

### SHADOW MORE

- Efinance/AkShare transport classification has a real shared core, but not exact equivalence.

### KEEP

- provider API-body interpretation;
- Futu SDK result semantics;
- existing `DataFetchError` hierarchy;
- retry/fallback/cooldown ownership;
- native diagnostic evidence.

### REJECT

- universal provider error framework;
- second provider health state machine;
- generic transient wrapper that collapses `AUTH`, `ENTITLEMENT`, `DATA_UNAVAILABLE`, or `UNKNOWN`.

Minimal Core succeeded here by finding a **counterexample before deletion**. Avoiding a wrong abstraction is itself a complexity reduction.