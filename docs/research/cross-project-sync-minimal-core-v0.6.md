# STOCK RAZOR — Minimal Core Cross-Project Sync V0.6

**Mode:** delta sync only  
**Production behavior change:** none  
**Source:** Minimal Core cross-lane research audit

## New evidence since V0.5

### E10-B — provider failure-surface inventory

The provider layer does not have one uniform error model. Three materially different surfaces are now documented:

1. Efinance/AkShare: explicit transport classifier + native detail.
2. YFinance/Finnhub/AlphaVantage-style daily paths: broad exception wrapping into `DataFetchError` plus provider-specific semantic checks.
3. Futu: SDK result/fail-soft paths returning `None`, `[]`, or empty frames in many operations.

**Cross-lane decision:** do not build a universal error framework. Continue only the narrow Efinance/AkShare classifier-deduplication Shadow path.

### E03-B — YFinance retry surface

A new Shadow test pins current behavior where a synthetic `ConnectionError` from `yf.download()` is caught inside `_fetch_raw_data()` and wrapped as `DataFetchError`. Because the Tenacity decorator retries `ConnectionError`/`TimeoutError`, the ordinary wrapped path currently produces one download call rather than a second attempt.

This is not authorization to remove or restore retry. It is evidence for AI Monitor E03 review.

### E12-A — symbol fixture corpus

A new Shadow fixture corpus separates:

```text
canonical/normalization semantics
suffix-market classification
provider wire symbols
```

Representative identity separation is now executable evidence:

```text
HK00700 canonical -> HK00700
Yahoo wire        -> 0700.HK
Futu wire         -> HK.00700
```

Provider wire formatting remains adapter-owned.

## Lane actions

### AI_MONITOR/HARVEST

Continue E03 using the YFinance call-count evidence. Determine whether current single-call behavior is intentional and whether inactive retry machinery is a safe DELETE candidate. Do not change production behavior from this sync alone.

For E10, expand differential corpus only for the Efinance/AkShare common classifier seam. Do not absorb Futu SDK semantics or provider API-body semantics into generic transport classification.

### AI_MONITOR/CONTROL_TOWER

At Shadow Evidence Ready, adjudicate E03-B as one of:

```text
KEEP single-call semantics + simplify dead retry surface
DESIGN real retry under explicit budget
SHADOW MORE
```

Any real retry restoration is a behavior change and requires separate design/implementation review.

### RADAR/PERCEPTION_DATA_INTELLIGENCE

For E10, contribute provider-native examples where HTTP transport success still carries semantic failure (rate limit, entitlement, no-data, subscription, protocol result). This evidence protects against over-generalization.

For E12, extend fixtures with real observed/provider-native symbol forms and ambiguous inputs, but do not create routing/runtime code.

### RADAR/HARVEST

Use E12-A as a read-set experiment: identify pass-through symbol helpers whose only behavior is delegating to an existing semantic owner. Report candidate deletion with call-site count and compatibility risk.

### RADAR/CONTROL_TOWER

Check E12 simplification against persisted Candidate/Replay identities and historical lookup aliases. Canonical identity consolidation must not break replay joins or candidate continuity.

## New DELETE candidates

Candidate status only; not approved for production deletion:

```text
E10: duplicated Efinance/AkShare transport keyword tuples + identical branch ladder
E03: YFinance retry decoration/policy surface if proven behaviorally inactive and intentionally single-attempt
E12: JP/KR/TW pass-through market wrappers if call-site compatibility permits
E12: duplicate HK recognition helpers only where accepted/rejected fixture sets are identical
```

## Explicit KEEP

```text
provider API-body semantic interpretation
Futu SDK result/entitlement semantics
provider wire symbol conversion
lookup alias expansion as a separate contract
DataFetchError existing application error surface
retry/fallback/cooldown ownership boundaries
```

## Promotion condition

No candidate advances because it looks shorter. It advances only when:

```text
same observable semantics (or explicit bug-fix contract)
+ no UNKNOWN/currentness/entitlement loss
+ no provider-routing change
+ smaller semantic-owner/read-set result
+ negative/adversarial evidence
+ rollback
+ net_complexity_result = SMALLER
```

## Sync status

Sync to:

- AI_MONITOR/HARVEST
- AI_MONITOR/CONTROL_TOWER
- RADAR/HARVEST
- RADAR/CONTROL_TOWER
- RADAR/PERCEPTION_DATA_INTELLIGENCE

Trading intelligence lanes remain downstream consumers unless a later promoted change affects data freshness, confidence, routing, Candidate/Gate semantics, Portfolio truth, or Risk Budget inputs.