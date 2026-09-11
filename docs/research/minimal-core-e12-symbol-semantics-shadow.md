# Minimal Core E12 — Symbol Semantics Shadow Contract

**Mode:** Research / Shadow  
**Production behavior change:** none  
**Primary owners:** Radar Harvest for semantic audit; AI Monitor only if later production/provider boundaries are affected  
**Evidence support:** RADAR/PERCEPTION_DATA_INTELLIGENCE

## Problem

Market identity and symbol formatting are related but not identical concerns.

Current code contains several useful pieces of symbol logic, including:

- `data_provider.base.normalize_stock_code()` for canonical-ish system/provider normalization;
- `src/services/market_symbol_utils.py` for table-driven JP/KR/TW suffix-market rules;
- `StockAnalysisPipeline._symbol_scope_lookup_values()` for persisted-intelligence lookup aliases;
- provider-local conversions such as Sina/Tencent prefixes, Yahoo suffixes, Longbridge/Futu symbols;
- provider-local market helpers such as HK/US detection.

Some duplication is necessary because wire formats differ. Other duplication may be accidental and increases the chance that one path accepts a symbol another path rejects.

## Core distinction

E12 freezes three separate semantic layers for research:

### 1. Canonical identity

Answers questions such as:

```text
what instrument/market identity does the user mean?
what is the canonical system spelling?
```

Examples:

- A-share `SH600519`, `600519.SH` → canonical A-share identity;
- HK `1810.HK`, `HK1810`, `HK01810` → canonical HK identity;
- US `aapl` → canonical `AAPL`;
- JP `7203.T` remains suffix-qualified;
- KR `005930.KS` remains suffix-qualified;
- TW `2330.TW` / `6505.TWO` remain suffix-qualified.

### 2. Lookup aliases

Answers:

```text
which historical/storage spellings may refer to the same canonical identity?
```

This is not canonicalization. Alias expansion may intentionally be one-to-many.

### 3. Provider wire symbol

Answers:

```text
how must this canonical identity be encoded for this provider endpoint?
```

Examples include `sh/sz/bj` prefixes, Yahoo suffixes, and provider-specific HK formats.

Provider wire formatting must remain adapter-local unless a truly shared provider protocol proves otherwise.

## Existing good pattern

`src/services/market_symbol_utils.py` is already a useful Minimal Core example. JP/KR/TW suffix-only markets are described by a small immutable table (`SuffixMarketSpec`) and generic helpers rather than separate copies of nearly identical branching logic.

E12 should extend the *principle* only where semantics are genuinely shared. It does not require moving every market/provider rule into that module.

## First fixture corpus

Build a differential fixture table containing at least:

```text
600519
SH600519
SH.600519
600519.SH
000001
SZ000001
920748
BJ920748
HK00700
hk1810
1810.HK
AAPL
aapl
BRK.B
7203.T
005930.KS
035720.KQ
2330.TW
6505.TWO
```

For each record capture:

```text
input
canonical identity
market
accepted lookup aliases
provider-specific representations where currently supported
ambiguous?/UNKNOWN?
```

## Bounded Shadow comparisons

### E12-A — canonical identity

Compare existing normalization/market-detection paths and identify disagreement. Do not fix disagreements in the research PR.

### E12-B — aliases

Compare persisted-intelligence lookup aliases with canonical identity. Verify aliases never silently become a new canonical identifier.

### E12-C — provider adapters

For each provider, document only the conversion from canonical identity to wire symbol and whether unsupported markets fail explicitly.

The goal is to delete duplicate **market identity rules**, not provider-specific wire requirements.

## Important ambiguity rules

Some raw symbols are genuinely ambiguous without market context. E12 must not make the system look simpler by guessing.

Examples/risks:

- bare numeric codes with different exchange conventions;
- HK digit padding;
- US tickers containing dots;
- JP/KR/TW suffix-only symbols;
- index vs stock collisions;
- BSE vs other six-digit instruments.

Where identity cannot be proven, preserve `UNKNOWN`/explicit parsing failure rather than inferring from convenience.

## Anti-goals

Do not:

- create a global provider-symbol registry duplicating adapter knowledge;
- make one giant `if market/provider` function;
- silently broaden accepted symbol forms;
- change storage keys as part of a cleanup;
- merge index identity with ordinary stock identity;
- infer market from price/data availability;
- force aliases into canonical state;
- add an abstraction that every provider must subclass unless it demonstrably lowers complexity.

## Measurements

Track:

- number of market-identity owners;
- number of duplicate HK/US/A-share/suffix-market detectors;
- number of provider-local rules that are truly wire-only;
- fixture disagreements;
- files needed to reason about one symbol end-to-end;
- regression tests required for canonical identity;
- `UNKNOWN`/ambiguous cases preserved.

## Promotion gate

Any production consolidation requires:

1. fixture-based differential evidence across CN/HK/US/JP/KR/TW and indices where supported;
2. storage/lookup behavior unchanged unless separately migrated;
3. provider wire formats remain correct;
4. ambiguity fails explicitly;
5. no second provider capability/routing registry;
6. fewer market-identity owners and smaller Agent read-set;
7. adversarial collision tests;
8. explicit rollback;
9. `net_complexity_result = SMALLER`.

## Desired end state

The target shape is intentionally boring:

```text
raw/user symbol
      ↓
small canonical identity rule
      ↓
canonical instrument identity
      ├── lookup alias expansion
      └── provider adapter → wire symbol
```

If achieving that requires a large symbol framework, E12 should stop and keep the current local logic.