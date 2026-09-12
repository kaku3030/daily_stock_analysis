# STOCK RAZOR — Minimal Core Current State

**Purpose:** default context pointer for current Minimal Core work.  
**Rule:** agents should read this file first. Historical `cross-project-sync-minimal-core-v0.*.md` files are audit/delta history and should not be loaded by default.

## Current mode

```text
Research / Shadow only
Production runtime owner unchanged
No production simplification promoted from this branch yet
```

Goal: **Minimum Semantic Code**, not minimum LOC.

Promotion always requires:

```text
preserved governed semantics
+ singular production owner
+ differential/replay/adversarial evidence
+ smaller semantic owner/read-set result
+ rollback
+ net_complexity_result = SMALLER
```

## Active experiments

| ID | Surface | Current status | Current decision |
| --- | --- | --- | --- |
| E01 | Currentness | delegated / differential replay spec | SHADOW |
| E03 | retry/fallback | Efinance four-exception matrix, AkShare retry-vs-provider fallback, manager budget, and negative semantic paths are recorded at exact head `b8e50a1cfcd3aa6339d260997518349af672c52b` | KEEP CURRENT PRODUCTION; no simplification promoted |
| E05 | provider capability boundary | Golden Contract identified | SHADOW |
| E06 | Agent read-set/token | benchmark spec | SHADOW |
| E07 | Headroom/tool output | protected-field benchmark spec | SHADOW only |
| E08 | config facts | bounded drift matrix + Shadow test; five aligned defaults measured across runtime/registry/example; STOCK_LIST and empty fallback semantics protected | SHADOW / imported-constant deletion remains unproven |
| E09 | pipeline/read-set | HK symbol representative task measured at 7 file reads | SHADOW evidence |
| E10 | failure taxonomy | expanded differential found real divergences | SHADOW MORE; universal framework REJECT |
| E11 | cache semantics | positive TTL boundary passes; real write/clear/thread/logging/read-set comparison remains incomplete | SHADOW boundary only; abstraction UNKNOWN, broad unification REJECT |
| E12 | symbol semantics | fixture corpus + full routing differential + 9→3 call-site delta | PROMOTION CANDIDATE; production owner review still required |

## Strongest current DELETE candidates

Not production-approved:

1. **E12 suffix wrappers:** full Shadow differential preserves market-tag and daily/realtime route decisions across CN/HK/US, JP/KR/TW, unknown and adversarial suffix inputs. The measured 9 wrapper-call expressions reduce to 3 Shadow lookups (-6), with `net_complexity_result = SMALLER`; production deletion remains frozen pending owner authorization.
2. **E03 YFinance:** retry machinery is behaviorally inactive on the ordinary wrapped transport path, but undecorated behavior exposes native exceptions while the decorated path exposes `DataFetchError` (with preserved cause). `net_complexity_result = UNKNOWN`; compatibility-visible semantics require SHADOW MORE.
3. **E08 config literals:** five aligned backend/numeric defaults are measured across runtime constants, registry metadata, and `.env.example`; no production owner was deleted. `net_complexity_result = UNKNOWN`.
4. **E11 positive snapshot cache mechanics:** TTL predicate boundary is Shadow-pass only; miss/empty and negative-age behavior also match the model, but lifecycle/read-set evidence is absent. `net_complexity_result = UNKNOWN`.

## Candidate downgraded after evidence

**E10 Efinance/AkShare classifier direct merge** was initially stronger. Expanded differential found divergences:

```text
ChunkedEncodingError:
  Efinance -> request_error
  AkShare  -> remote_disconnect

ValueError("") detail:
  Efinance -> ""
  AkShare  -> "ValueError"
```

Therefore direct deletion/merge is **not safe yet**. This is a good example of Shadow evidence preventing a false simplification.

## Hard KEEP boundaries

Do not simplify away or compress as ordinary glue:

```text
UNKNOWN / INDETERMINATE
provider timestamps / timezone / expected session
Currentness evidence
entitlement / subscription
Portfolio runtime truth
Delivery semantics
Lifecycle / Continuity / Recovery
Risk / Gate reason fields
provider API-body semantics
provider wire symbol formatting
provider cooldown / health state
credential/token persistence
```

## Ownership

```text
AI Monitor = production Provider/LiveFeed/Currentness/Portfolio/Delivery/AI runtime owner
Radar = Candidate/RS/Capital Persistence/Lifecycle research/Replay/OOS/Strategy Lab owner
Radar Perception & Data Intelligence = evidence/fixtures/provider semantics only
```

Research may run in parallel; production owner stays unique.

## Default read-set by task

### E03 retry task

Read only:

```text
this file
minimal-core-e03-retry-inventory.md
minimal-core-e03b-yfinance-retry-surface.md
relevant provider function + Shadow tests
```

### E10 failure-classification task

Read only:

```text
this file
minimal-core-e10b-error-classification-inventory.md
current E10 Shadow test
relevant provider classifiers
```

### E12 symbol task

Read only:

```text
this file
minimal-core-e12a-symbol-fixture-corpus.md
minimal-core-e12b-market-wrapper-delete-audit.md
market_symbol_utils.py
current E12 Shadow tests
```

Do **not** load all historical sync packets unless a provenance question requires them.

## Next executable frontier

```text
E10: treat divergences as governed evidence; no common production helper yet
E12: re-check exact-head CI and complete compatibility-import review; do not promote production deletion from Shadow evidence alone
E11: test TTL boundary equivalence before any cache helper
E08: let exact-head CI validate drift assertions
E09: choose one representative pipeline change and measure minimum safe read-set
```

## Audit history

Historical sync/delta packets remain in `docs/research/cross-project-sync-minimal-core-v0.*.md` for traceability. They are not current-state authority.

**Current-state authority for Minimal Core research is this file plus exact-head GitHub/CI evidence.**

## Latest exact-head evidence

```text
branch: research/minimal-core-initiative-v0-1
head: 437728135eda23e0fbfd53aa8f0f2d7d8fa9631e
commit: docs(research): close E03 E08 E11 evidence
mode: Research / Shadow only
production runtime: unchanged
PR #71: open, unmerged
exact-head checks: CI #219 success; Research Radar Tests #237 success
changed-files: 46 (PR metadata)
```

## E12 production-promotion design review (design only)

Verdict: `READY_FOR_IMPLEMENTATION_REVIEW`, not production authorization.

The smallest proposed patch replaces the three routing-surface groups of
JP/KR/TW pass-through wrapper calls with one `get_suffix_market(code)` lookup,
then deletes only wrappers and local booleans proven to add no semantics.
`market_symbol_utils.py` remains the sole semantic owner. US-before-HK
precedence, unknown handling, aliases, provider wire formatting, timestamps,
`UNKNOWN`, reason and risk fields remain protected.

Compatibility surface: direct imports, monkeypatch targets, persisted/replay
symbol identities, provider adapters and every caller branch. Required negative
tests cover malformed/empty symbols, ambiguous suffixes, mixed case,
CN/HK/US precedence, unknown suffixes, direct wrapper imports and provider-wire
output. Any mismatch is `BLOCKED`; rollback is a single revert and owner review
is required from AI Monitor/Data Reliability and each routing owner.

Measured Shadow delta: 9 wrapper-call expressions -> 3 lookups, with 3
pass-through definitions/local booleans removable; `net_complexity_result = SMALLER`.
Implementation remains owner-gated and production runtime stays unchanged.

## New local DELETE/SIMPLIFY scan

| Candidate | Owner/read-set evidence | Required next evidence | `net_complexity_result` |
| --- | --- | --- | --- |
| E12 suffix wrappers | `market_symbol_utils.py`; 9 calls / 3 surfaces | import, precedence and bypass tests | `SMALLER` |
| E03 YFinance decorator | provider-local; one ordinary call, error surface differs | public/manager exception matrix | `UNKNOWN` |
| E08 repeated defaults | ConfigManager owner plus registry/example literals | imported-constant Shadow diff | `UNKNOWN` |
| E11 positive snapshot | provider-local writes/clears plus TTL predicate | lifecycle/concurrency/logging differential | `UNKNOWN` |
| E10 classifier | two owners with category/detail divergence | preserve retry/fallback/native detail | `LARGER / REJECT` |

No new promotion candidate beyond E12: **`NO NEW PROMOTION CANDIDATE`**.
