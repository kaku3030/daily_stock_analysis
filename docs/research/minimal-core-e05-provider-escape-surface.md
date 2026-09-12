# MCI-E05 — Provider Escape Surface Audit

**Initiative:** Minimal Core V0.3  
**Production owner:** `AI_MONITOR/CONTROL_TOWER`  
**Research evidence contributor:** `RADAR/PERCEPTION_DATA_INTELLIGENCE`  
**Mode:** research / Shadow only  
**Production behavior change:** none

## 1. Question

How much provider-specific vocabulary, private state, routing knowledge, and symbol/timestamp logic escapes the `data_provider` boundary into higher layers?

The target is **not** to hide provider identity. Observability must still be able to say “Futu”, “AkShare”, or “Longbridge”. The target is to stop higher layers from needing to understand provider implementation details in order to answer generic questions such as:

- is this capability configured/available?
- which markets/datasets are supported?
- what is the source priority?
- what was the last governed failure?
- is this timestamp normalized?

## 2. Good boundary examples already present

### E05-G01 — Futu timestamp normalization stays inside the adapter

`data_provider/futu_fetcher.py` documents that Futu `update_time` is a naive HK/Beijing-time string and normalizes it to an offset-aware ISO timestamp before constructing `UnifiedRealtimeQuote`.

This is exactly the desired direction:

```text
Futu-native update_time
       ↓ provider adapter
normalized provider_timestamp
       ↓
UnifiedRealtimeQuote
```

Higher layers should consume the normalized timestamp and should not need Futu timezone folklore.

**Decision:** `KEEP / use as reference pattern`.

### E05-G02 — Unified realtime quote exists

Futu maps provider-native fields such as `last_price`, `prev_close_price`, `change_rate`, `turnover_rate`, `pe_ttm_ratio`, etc. into `UnifiedRealtimeQuote`.

**Decision:** `KEEP`. New simplification should strengthen this boundary instead of bypassing it.

## 3. Confirmed escape surfaces

### E05-F01 — `DataCapabilityService` duplicates the provider registry

`src/services/data_capability_service.py` defines a central `_PROVIDER_DEFINITIONS` table containing provider names, labels, fetcher class names, datasets and markets for Efinance, AkShare, Tencent, YFinance, PyTDX, Baostock, Tushare, TickFlow, Longbridge, Futu, Finnhub and Alpha Vantage.

The same service also defines additional provider-specific maps/sets:

- `_FETCHER_TO_PROVIDER`
- `_REALTIME_SOURCE_PROVIDER`
- `_AKSHARE_REALTIME_CIRCUIT_KEYS`
- `_CN_REALTIME_SOURCES`
- `_SCREENING_SOURCES`
- `_MARKET_OVERVIEW_PROVIDER_MARKETS`

Meanwhile `data_provider/base.py` independently owns routing/capability facts such as `_CN_INDEX_DAILY_SOURCE_ORDER`, and `data_provider/__init__.py` independently documents/export-lists providers and priority semantics.

**Finding:** provider capability/routing knowledge has more than one definition surface.

This does not prove the values are currently inconsistent; it proves an agent changing one provider may need to inspect multiple files to know whether the contract is complete.

**Decision:** `SHADOW → candidate MERGE`, but only after a duplication/diff test.

### E05-F02 — service layer reaches into provider-manager private internals

`DataCapabilityService._fetchers_snapshot()`:

- imports `DataFetcherManager` directly;
- calls private `_get_fetchers_snapshot()` when available;
- otherwise reads private `_fetchers`.

Availability diagnostics also call `DataFetcherManager._call_availability_probe()` and inspect fetcher private/public attributes such as `_available`, `_last_error`, `name`, and `priority`.

**Finding:** diagnostics currently depend on provider implementation internals instead of a narrow public capability snapshot contract.

**Risk:** changes to manager internals expand blast radius into service/UI diagnostics even when provider runtime semantics are unchanged.

**Decision:** `ADAPT / strong simplification candidate`.

### E05-F03 — provider configuration knowledge leaks into service layer

`DataCapabilityService._is_provider_configured()` understands provider-specific credentials/configuration:

- Tushare token;
- TickFlow API key;
- Futu OpenD host;
- Longbridge legacy vs OAuth credential combinations;
- Finnhub API key;
- Alpha Vantage API key.

**Finding:** the service knows how each provider authenticates/configures itself.

**Decision:** `SHADOW candidate`. Prefer provider-owned metadata such as `configured_status()` or an immutable descriptor, provided this does not create another runtime owner.

### E05-F04 — source priority knowledge is duplicated above the manager

`DataCapabilityService` reconstructs priorities for:

- CN realtime;
- HK realtime;
- US realtime;
- generic daily;
- CN index daily;
- market overview;
- screening snapshot;
- news.

Some entries cite `DataFetcherManager` source-order constants as their source, but the service still keeps parallel provider-name tables and fallback logic.

**Decision:** do not invent another generic router. Evaluate whether the authoritative manager can expose a read-only `capability_snapshot()` / `routing_snapshot()` generated from the actual runtime configuration.

### E05-F05 — market-symbol semantics are intentionally duplicated across fetchers

`base._is_hk_market`, `AkshareFetcher._is_hk_code`, and provider-specific symbol conversion functions all encode parts of HK symbol semantics. Comments explicitly mention keeping their accepted 4–5 digit forms aligned.

This is a warning sign: when comments say two implementations “must stay consistent,” the contract may lack a single executable owner.

**Decision:** `SHADOW / candidate MERGE` for **classification only**. Provider-specific conversion must remain in adapters where APIs require different symbol formats.

Target separation:

```text
canonical market classification      → one shared semantic owner
provider-specific wire symbol        → provider adapter
```

### E05-F06 — Futu non-realtime methods can return provider-native shapes

Several Futu helper methods return provider SDK DataFrames/records directly (`get_stock_basicinfo`, financial statements, company profile, capital flow, owner plate, etc.).

This is not automatically a bug: these may be consumed only by a provider-local fundamental adapter.

**Decision:** `UNKNOWN / caller audit required`. Do not normalize merely for aesthetic consistency. Promote only if provider-native shapes cross into generic application services.

## 4. Proposed minimal public provider descriptor

Research shape only; no production API proposal yet:

```python
ProviderDescriptor(
    provider_id,
    display_name,
    capabilities,
    markets,
    configured,
    runtime_status,
    priority_by_capability,
    last_error_code,
)
```

Rules:

- immutable/read-only snapshot;
- generated by the authoritative provider runtime/manager;
- no secrets;
- no SDK objects/DataFrames;
- no mutation methods;
- no second source of routing truth;
- retain provider identity for observability;
- `UNKNOWN` remains possible and explicit.

A descriptor is worth adding only if it deletes more duplicated knowledge/read-set than it adds in abstraction cost.

## 5. Candidate architecture comparison

### Candidate A — current model

```text
DataFetcherManager runtime
        +
DataCapabilityService provider registry/maps
        +
provider package exports/docs
        +
config-specific provider knowledge
```

Strength: explicit and easy to patch locally.  
Weakness: duplicated provider facts and private-attribute reach-through.

### Candidate B — manager-owned read-only snapshot

```text
Provider adapters
      ↓
DataFetcherManager (authoritative runtime/routing)
      ↓ capability_snapshot()
DataCapabilityService (presentation/aggregation only)
```

Strength: fewer provider facts outside provider boundary.  
Risk: snapshot method can become a giant god-interface if it absorbs UI concerns.

### Candidate C — provider plugin framework

**Rejected for now.** There is no evidence that introducing plugin registration machinery would reduce the total semantic/read-set cost. Provider count alone is not sufficient reason.

## 6. E05 differential audit

Before any refactor, construct a provider matrix from the current implementation:

| Provider | configured | available | markets | datasets | priority/routes | last error | notes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Efinance | fixture | fixture | current | current | current | fixture | |
| AkShare | fixture | fixture | current | current | current | fixture | |
| Tushare | fixture | fixture | current | current | current | fixture | |
| TickFlow | fixture | fixture | current | current | current | fixture | |
| Futu | fixture | fixture | current | current | current | fixture | |
| Longbridge | fixture | fixture | current | current | current | fixture | |
| YFinance | fixture | fixture | current | current | current | fixture | |
| remaining providers | fixture | fixture | current | current | current | fixture | |

Then compare current `DataCapabilityService` output against a Shadow descriptor-generated output.

Protected fields:

- provider identity;
- enabled/configured distinction;
- `unknown` status;
- market/dataset support;
- source ordering;
- warning/reason semantics;
- last-error sanitization;
- entitlement/subscription state where applicable.

## 7. Read-set hypothesis

A generic provider capability change can currently touch or require reading at least:

- `data_provider/base.py` — large manager/routing surface;
- one provider fetcher;
- `src/services/data_capability_service.py` — parallel capability/priority registry;
- `data_provider/__init__.py` — package-level provider list/docs;
- config definitions when credentials/routing change.

This is a **hypothesis to measure in E06**, not yet a token-saving claim.

## 8. Promotion gate

A provider-boundary simplification must prove:

1. one production owner remains `DataFetcherManager`/AI Monitor runtime;
2. capability snapshot is read-only;
3. no provider-specific timestamp/entitlement evidence is lost;
4. current `DataCapabilityService` fixtures are output-equivalent unless an existing bug is explicitly documented;
5. routing order is unchanged;
6. private-attribute dependencies decrease;
7. duplicated capability definitions decrease;
8. agent read-set decreases on at least two provider-change tasks;
9. no plugin framework is introduced unless it demonstrably reduces total complexity.

## 9. Current decision

**PROMOTE E05 TO SHADOW DESIGN COMPARISON.**

The strongest first candidate is not “rewrite all providers.” It is much smaller:

> expose one authoritative, read-only provider/routing capability snapshot and see whether it can delete the parallel registry/private reach-through in `DataCapabilityService` while preserving all diagnostics.
