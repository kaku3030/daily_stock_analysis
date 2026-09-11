# Minimal Core E12-A — Symbol Semantics Fixture Corpus

**Mode:** Research / Shadow  
**Production behavior change:** none  
**Goal:** pin current symbol semantics before deleting duplicated market/symbol helpers.

## 1. Why a fixture corpus comes before refactor

Stock Razor currently carries several different symbol concerns that look similar in code but are not the same contract:

```text
canonical user/storage identity
market classification
lookup aliases
provider wire symbol
```

A safe Minimal Core refactor must first prove which transformations are genuinely shared.

The target architecture is:

```text
Canonical Identity / Market Classification
              ↓
       one semantic owner

Storage / Search Alias Expansion
              ↓
       explicit alias contract

Provider Wire Symbol
              ↓
       provider adapter only
```

E12-A records current behavior. It does not declare that every current behavior is desirable.

---

## 2. Existing small-core pattern worth preserving

`src/services/market_symbol_utils.py` is already a good Minimal Core example for suffix-only offshore markets:

```text
JP: .T    -> 4/5 digit base
KR: .KS/.KQ -> 6 digit base
TW: .TW/.TWO -> 4/5/6 digit base
```

The rules live in `SuffixMarketSpec` table data and a few dependency-light pure helpers.

**Decision:** KEEP this shape. Extend only if another market truly fits the same semantic model.

Do not force HK/CN/US into the suffix table merely to make the code visually uniform.

---

## 3. Canonical normalization corpus

Current `data_provider.base.normalize_stock_code()` behavior to pin as Shadow evidence:

| Input | Current normalized form | Semantic note |
| --- | --- | --- |
| `600519` | `600519` | CN already clean |
| `SH600519` | `600519` | CN prefix stripped |
| `SH.600519` | `600519` | dotted prefix stripped |
| `600519.SH` | `600519` | CN suffix stripped |
| `SZ000001` | `000001` | CN prefix stripped |
| `BJ920748` | `920748` | BSE prefix stripped |
| `920748.BJ` | `920748` | BSE suffix stripped |
| `hk1810` | `HK01810` | HK canonical prefix + 5 digits |
| `1810.HK` | `HK01810` | HK suffix → canonical prefix |
| `7203.T` | `7203.T` | JP suffix retained |
| `005930.KS` | `005930.KS` | KR suffix retained |
| `035720.KQ` | `035720.KQ` | KR suffix retained |
| `2330.TW` | `2330.TW` | TWSE suffix retained |
| `6505.TWO` | `6505.TWO` | TPEx suffix retained |
| `AAPL` | `AAPL` | US ticker retained |

Important distinction: `canonical_stock_code()` is an input/display/storage case-normalizer, while `normalize_stock_code()` also removes some exchange wrappers. They are **not currently one function** and should not be merged without an explicit boundary decision.

Example:

```text
canonical_stock_code("aapl") -> "AAPL"
normalize_stock_code("aapl") -> "aapl"   # current behavior
```

That difference is useful evidence that “canonical” currently means different things at different layers.

---

## 4. Suffix-market corpus

Current shared market-symbol helper behavior:

| Symbol | `get_suffix_market()` |
| --- | --- |
| `7203.T` | `jp` |
| `005930.KS` | `kr` |
| `035720.KQ` | `kr` |
| `2330.TW` | `tw` |
| `6505.TWO` | `tw` |
| `7203.X` | `None` |
| `AAPL` | `None` |
| `123.KS` | `None` |

These are strong candidates to remain one pure table-driven semantic owner.

---

## 5. Provider wire-format corpus

Provider wire symbols are **not canonical identity** and should remain adapter-local.

### Tencent direct endpoint

Representative current mappings:

```text
600519   -> sh600519
000001   -> sz000001
BJ920748 -> bj920748
```

### Yahoo Finance

Representative current mappings:

```text
600519  -> 600519.SS
000001  -> 000001.SZ
HK00700 -> 0700.HK
AAPL    -> AAPL
7203.T  -> 7203.T
2330.TW -> 2330.TW
```

### Futu HK

Representative current mappings:

```text
HK00700 -> HK.00700
00700   -> HK.00700
700.HK  -> HK.00700
```

These three formats intentionally disagree because they are wire contracts for different providers.

**Hard rule:** a future canonical symbol helper must never replace provider wire conversion.

---

## 6. Alias expansion is a separate contract

`src/pipeline.py::_symbol_scope_lookup_values()` expands canonical/raw input into persisted-intelligence lookup spellings.

Examples of current intent include variants such as:

```text
HK01810
1810
01810
1810.HK
01810.HK

600519
SH600519
SH.600519
600519.SH
SS.600519
600519.SS
```

This is different from canonical normalization: aliases deliberately create **multiple accepted spellings** to find historical/persisted records.

Therefore:

- do not move alias expansion into provider adapters;
- do not make canonical identity return a list of aliases;
- do not make provider wire helpers responsible for persistence lookup.

E12-B should decide whether this alias logic deserves a small explicit module/fixture, but E12-A only records the separation.

---

## 7. Shadow executable evidence

`tests/test_minimal_core_e12_symbol_corpus.py` should pin three layers independently:

1. canonical/normalization behavior;
2. suffix-market classification;
3. provider wire mappings.

The test is **not** a production contract freeze. If it exposes a current inconsistency, that inconsistency may later be repaired through a separate governed change.

---

## 8. Initial DELETE candidates

### Candidate A — duplicate HK recognition rules

Current HK recognition exists in multiple places, including base/provider helpers. If fixture comparison proves identical accepted/rejected sets, wrappers that add no provider-specific semantics may become DELETE candidates.

### Candidate B — JP/KR/TW wrapper helpers

`data_provider.base._is_jp_market/_is_kr_market/_is_tw_market` already delegate directly to `is_suffix_market_symbol()`.

If call-site migration is low-risk, these thin pass-through wrappers are possible DELETE candidates because the semantic owner already exists in `market_symbol_utils.py`.

Do not delete them merely for LOC reduction if they provide an important compatibility/import seam.

### Candidate C — repeated CN exchange inference

Tencent conversion, pipeline aliases, YFinance conversion and base normalization all infer CN exchange in different contexts. Some branches may be shared, but they must first be separated into:

```text
market identity
exchange identity
provider wire formatting
legacy alias compatibility
```

Only the truly identical inference can be centralized.

---

## 9. Promotion gate

Any symbol simplification requires:

1. fixture parity across CN/HK/US/JP/KR/TW;
2. no routing regression;
3. no persisted-record lookup regression;
4. provider wire output unchanged unless intentionally governed;
5. index-vs-stock identity preserved;
6. BSE/ETF distinctions preserved;
7. malformed/ambiguous inputs fail the same way or become explicitly stricter;
8. Agent read-set and semantic-owner count decrease;
9. `net_complexity_result = SMALLER`.

If one universal `Symbol` abstraction requires every provider to register formatting callbacks, aliases and market rules, it is probably **LARGER** and should be rejected.

---

## 10. Expected Minimal Core outcome

The desired result is not “one function that does every symbol thing”. It is three tiny explicit contracts:

```text
identify / normalize
lookup aliases
provider format
```

Each should have one reason to change. That is smaller semantic code even if the total number of functions does not fall dramatically.