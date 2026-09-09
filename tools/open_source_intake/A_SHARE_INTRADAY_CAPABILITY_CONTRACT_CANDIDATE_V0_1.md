# A-Share Intraday Capability Contract Candidate V0.1

Status: `DESIGN:CANDIDATE` — Harvest handoff for Architecture & Promotion Control Tower review. **NOT FROZEN.**

Scope: normalize provider capability/evidence for CN `15m` / `1H` K-line data before any provider is admitted as an intraday Currentness authority.

No implementation, routing, scoring, fallback, Currentness threshold, SHADOW/CORE, strategy, AI, or trading behavior is authorized by this document.

## Why this contract is needed

Current Stock Razor capability metadata is provider/dataset oriented (`quote.realtime`, `kline.daily`, etc.). External A-share sources already expose 15m/60m data in several ways, but method availability alone cannot answer:

- whether the source is actually wired into Radar;
- whether two adapters are independent upstream evidence;
- whether a timestamp names bar start, bar end, or something else;
- whether the newest row is forming or complete;
- whether 11:30–13:00 lunch break is represented as silence, a gap, or another provider convention;
- whether values are adjusted and what the volume unit means;
- whether minute permission is actually entitled;
- whether the call can block the caller indefinitely;
- whether the data is historical-only, diagnostic, or eligible for Currentness authority.

Therefore:

> `method exists != capability admitted != semantic contract verified != Currentness authority`

## Relationship to existing frozen / validated work

This candidate MUST reuse rather than duplicate:

- PR #40 `RealtimeSourceLineage` / reconciliation independence substrate for `upstream_lineage_id` semantics;
- shared Data Health / Currentness architecture for final freshness authority;
- provider-specific evidence discipline used in Futu semantics work;
- malformed-vs-missing Data Reliability rule;
- provider blocking-isolation principles where synchronous calls can hang.

It MUST NOT create a provider-specific parallel Currentness engine.

## Proposed identity key

One capability observation should be identified by the tuple:

`(provider_id, adapter_id, upstream_lineage_id, market, instrument_kind, interval, access_mode)`

Where:

- `provider_id`: Radar provider identity, e.g. `tushare`, `akshare`, `pytdx`;
- `adapter_id`: concrete Stock Razor adapter path;
- `upstream_lineage_id`: independent upstream family from PR #40 semantics;
- `market`: `cn` for this candidate;
- `instrument_kind`: at minimum `STOCK | ETF | INDEX`;
- `interval`: `15M | 1H`;
- `access_mode`: one of the evidence categories below.

Two capability records with different adapters but the same upstream lineage are **not independent corroboration**.

## Proposed access-mode vocabulary

Design candidate only:

- `REALTIME_PUSH`
- `REALTIME_REQUEST`
- `CURRENT_DAY_REPLAY`
- `HISTORICAL_REQUEST`
- `LOCAL_FILE_HISTORY`

Access mode must stay separate from Currentness eligibility. A `REALTIME_REQUEST` API may still be semantically insufficient for Currentness.

## Proposed evidence / semantics record

A normalized capability record should expose these groups explicitly.

### A. Identity / scope

- `provider_id: str`
- `adapter_id: str`
- `upstream_lineage_id: str | UNKNOWN`
- `market: cn`
- `instrument_kind: STOCK | ETF | INDEX`
- `interval: 15M | 1H`
- `access_mode`
- `endpoint_semantic_id`

### B. Admission state

- `radar_implementation_status`:
  - `NOT_IMPLEMENTED`
  - `IMPLEMENTED_NOT_VALIDATED`
  - `VALIDATING`
  - `ADMITTED`
- `provider_availability_status`
- `entitlement_status`:
  - `NOT_REQUIRED`
  - `REQUIRED_UNVERIFIED`
  - `VERIFIED_AVAILABLE`
  - `VERIFIED_UNAVAILABLE`
  - `UNKNOWN`

A configured token/API key is not itself entitlement proof.

### C. Source timestamp semantics

- `source_timestamp_field`
- `source_timezone`
- `timestamp_boundary_semantic`:
  - `BAR_START`
  - `BAR_END`
  - `PROVIDER_DEFINED_OTHER`
  - `UNKNOWN`
- `timestamp_precision`
- `cross_request_comparable: VERIFIED | PARTIAL | UNKNOWN`

No start/end value may be filled from intuition or from another provider's behavior.

### D. Forming / completion semantics

- `forming_bar_included`:
  - `YES`
  - `NO`
  - `CONDITIONAL`
  - `UNKNOWN`
- `forming_bar_mutates_same_identity`:
  - `YES | NO | UNKNOWN`
- `completion_marker_field: str | NONE_OBSERVED | UNKNOWN`
- `completion_inference_authorized: bool`

`completion_inference_authorized=True` requires evidence; absence of a completion flag does not authorize a clock heuristic.

### E. Session / expected-silence semantics

- `session_model_id`
- `morning_session_alignment`
- `lunch_break_behavior`
- `afternoon_session_alignment`
- `close_final_bar_behavior`
- `suspension_behavior`
- `zero_trade_interval_behavior`
- `temporary_closure_authority`

For A-shares, the 11:30–13:00 break must be explicitly modeled before simple wall-clock age can be used.

### F. Price / volume semantics

- `adjustment_mode`:
  - `NONE`
  - `FORWARD_ADJUSTED`
  - `BACKWARD_ADJUSTED`
  - `CALLER_SELECTABLE`
  - `UNKNOWN`
- `volume_unit`
- `amount_unit`
- `lot_size_semantics`
- `numeric_missing_semantics`
- `numeric_malformed_semantics`

Malformed numeric evidence must remain distinguishable from genuinely missing values.

### G. Retrieval constraints

- `max_rows_per_call`
- `max_lookback`
- `pagination_model`
- `publication_delay_semantic`
- `rate_limit_semantic`
- `blocking_risk`:
  - `BOUNDED_BY_PROVIDER`
  - `CALLER_BOUNDED_ISOLATION_REQUIRED`
  - `UNKNOWN`

A caller-side thread timeout that leaves a blocking provider operation alive does not prove hard execution isolation.

### H. Evidence provenance

- `official_evidence_refs[]`
- `controlled_observation_refs[]`
- `sdk_version`
- `provider_service_version` if known
- `observed_symbol_scope[]`
- `observed_date_scope[]`
- `evidence_status`:
  - `UNKNOWN`
  - `PARTIALLY_VERIFIED`
  - `VERIFIED_TESTED_SCOPE`
  - `SOURCE_VERIFIED`

Tool/test green status stays separate from provider evidence status.

## Proposed Currentness eligibility state

Design candidate only; no production enum is authorized yet.

- `HISTORICAL_ONLY`
- `DIAGNOSTIC_ONLY`
- `CURRENTNESS_CANDIDATE`
- `CURRENTNESS_ELIGIBLE`

### Hard gates for `CURRENTNESS_ELIGIBLE`

All of the following must be non-UNKNOWN and evidenced for the exact provider/market/instrument/interval/access mode:

1. provider/adaptor identity is explicit;
2. upstream lineage identity is explicit for reconciliation;
3. runtime entitlement/capability is verified where required;
4. source timestamp field and timezone are known;
5. timestamp boundary semantic is known;
6. forming-bar inclusion/completion behavior is known;
7. morning/lunch/afternoon/close session behavior is known;
8. suspension / expected-silence behavior is bounded sufficiently to avoid false stale;
9. adjustment and volume/amount units are known;
10. malformed-vs-missing behavior is explicit;
11. blocking/failure behavior has an accepted containment strategy;
12. controlled provider observation exists in target scope;
13. independent review accepts the evidence mapping;
14. governance explicitly promotes the capability.

Failure of any hard semantic gate must **not** be compensated by source count, confidence score, provider reputation, low latency, or agreement with another adapter.

## Reconciliation rule

Reconciliation works over **independent upstream lineage groups**, not adapter count.

Example:

- Efinance 15m + AkShare EM 15m agreeing = one Eastmoney lineage observation, not two votes.
- Tushare + TDX agreeing may be independent evidence if both capability records meet their own semantic gates.
- unknown lineage remains visible for diagnostics but is not eligible to increase independence count.

No numeric decision weighting is defined in V0.1.

## Candidate mappings from current Harvest audit

### Efinance / Eastmoney

- external interval capability: 15m/60m exists upstream;
- Radar implementation: current adapter daily-only;
- lineage: Eastmoney;
- timestamp/forming/session semantics: not yet verified;
- candidate eligibility now: `DIAGNOSTIC_ONLY` at best after adapter implementation; currently `NOT_IMPLEMENTED`.

### AkShare Eastmoney minute routes

- external interval capability: 15m/60m exists;
- Radar implementation: current adapter daily-only;
- lineage: Eastmoney;
- must not corroborate Efinance as an independent source;
- current eligibility: not admitted.

### TDX / PyTDX / mootdx

- protocol/wrapper interval capability: 15m/1h exists;
- Radar PyTDX implementation: current fetch path daily-only;
- lineage: TDX family candidate, distinct from Eastmoney/Tushare;
- timestamp/session/blocking semantics: require controlled audit;
- current eligibility: not admitted.

### Tushare

- official minute services expose A-share 15m/60m and current-day replay; ETF/index minute services also exist;
- minute access requires explicit entitlement;
- independent Tushare lineage;
- timestamp/forming/session semantics still require target-scope evidence;
- strong `CURRENTNESS_CANDIDATE` research lane after adapter + entitlement + semantic validation, not eligible yet.

### BaoStock

- external stock historical 15m/60m exists;
- current Radar adapter daily-only;
- minute data is a historical/backfill candidate, not assumed realtime;
- likely target eligibility: `HISTORICAL_ONLY` unless provider evidence proves a different service contract.

### TickFlow

- current Radar adapter daily path confirmed;
- authoritative external 15m/1h evidence remains UNKNOWN in current Harvest audit;
- keep capability UNKNOWN rather than infer from a generic K-line API name.

## Minimal implementation order if Control Tower accepts the shape

This is a proposed order, not authorization:

1. freeze vocabulary/field shape in docs;
2. implement immutable capability/evidence types only;
3. expose read-only capability records through `DataCapabilityService` without routing changes;
4. add anti-shrink and fail-closed tests;
5. populate records only with currently proven facts; leave unknowns explicit;
6. build provider-specific evidence harnesses;
7. only after evidence closure, consider Currentness candidate integration;
8. routing/fallback/decision changes remain a separate promoted slice.

## Exit criteria for this design candidate

Control Tower review should answer:

- Does this duplicate an existing frozen model? If yes, merge/reuse rather than create a parallel type.
- Is `upstream_lineage_id` sourced from the PR #40 substrate rather than redefined?
- Are Currentness eligibility and provider evidence separate dimensions?
- Are all UNKNOWN states fail-closed?
- Is entitlement explicit rather than inferred from configuration?
- Are lunch-break / suspension / forming-bar semantics first-class?
- Is there any hidden compensatory scoring? There must not be.
- Can the type be exposed read-only without changing routing?

Until those questions are accepted, this remains `DESIGN:CANDIDATE`, not FROZEN.
