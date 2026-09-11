# Minimal Core E12-B — Suffix-Market Wrapper Delete Audit

**Mode:** Research / Shadow  
**Production behavior change:** none

## Finding

`data_provider/base.py` currently contains three thin wrappers:

```python
_is_jp_market(code) -> is_suffix_market_symbol(code, "jp")
_is_kr_market(code) -> is_suffix_market_symbol(code, "kr")
_is_tw_market(code) -> is_suffix_market_symbol(code, "tw")
```

The semantic owner already exists in `src/services/market_symbol_utils.py`, where `get_suffix_market()` and the table-driven `SuffixMarketSpec` define JP/KR/TW suffix semantics.

The wrappers are therefore legitimate **pass-through deletion candidates**, but only if their call sites can become simpler rather than merely replacing one function name with another.

---

## Current call-site shape

Inside `data_provider/base.py`, the wrappers are used in at least three semantic paths:

1. `_market_tag()`;
2. daily-data market routing;
3. realtime/market-specific routing logic.

The repeated pattern is effectively:

```text
is_jp = _is_jp_market(code)
is_kr = _is_kr_market(code)
is_tw = _is_tw_market(code)
```

This invokes the same suffix parser up to three times and creates three local booleans for one mutually-exclusive semantic fact.

---

## Shadow simplification

For the shared suffix-only markets, the smaller representation is:

```text
suffix_market = get_suffix_market(code)
```

with one value in:

```text
jp | kr | tw | None
```

US and HK precedence remains explicit because they use different identity rules:

```text
US check
  ↓
HK check
  ↓
get_suffix_market(code)
  ↓
CN fallback
```

This does **not** move provider wire formatting into the shared helper.

---

## Executable evidence

`tests/test_minimal_core_e12b_market_wrapper_shadow.py` compares current `_market_tag()` with a Shadow implementation that calls `get_suffix_market()` once.

The corpus includes:

```text
CN A-share / BSE
HK canonical / suffix / bare numeric
US stock / index
JP
KR KOSPI / KOSDAQ
TWSE / TPEx
invalid suffix
```

Passing evidence proves only equivalence for the classification corpus. It does not authorize production deletion.

---

## Candidate deletion

If the larger routing corpus remains green, a later production patch may:

1. replace three suffix booleans with one `suffix_market` value at repeated call sites;
2. delete `_is_jp_market`, `_is_kr_market`, `_is_tw_market` if no compatibility imports remain;
3. keep `market_symbol_utils.py` as the only suffix-market semantic owner.

Expected benefits:

```text
- 3 pass-through wrappers
- repeated suffix parsing
- repeated local booleans
- one layer of agent indirection
```

---

## Compatibility risk

The wrappers are private by naming convention, but private does not prove unused. Before deletion:

- check repository imports/call sites on the exact head;
- preserve tests that import private helpers if they intentionally pin behavior;
- verify DataFetcherManager daily/realtime routing;
- verify JP/KR/TW fallback ordering;
- verify HK bare numeric precedence remains ahead of CN/suffix fallback;
- verify US index handling remains ahead of suffix logic.

If external/downstream consumers rely on these private helpers, a deprecation seam may cost more than the deletion saves. In that case KEEP is acceptable.

---

## `net_complexity_result`

For `_market_tag()` itself, the Shadow form is clearly smaller.

For the exact-head repository-wide call surface, the AST Shadow audit records
9 wrapper calls (3 in each of the market-tag, daily-routing, and
realtime-routing paths). A one-lookup-per-path candidate is 3 calls, a delta
of **-6 wrapper-call expressions** before accounting for the three wrapper
definitions and local boolean removal. This is an executable call-site/read
surface measurement, not production approval.

Therefore `net_complexity_result = SMALLER` for the measured call surface;
provider routing equivalence and compatibility-import review remain required
before any production deletion.

No generic `Symbol` object or provider registry is needed for this simplification.
