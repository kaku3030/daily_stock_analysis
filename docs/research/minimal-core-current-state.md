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
| E03 | retry/fallback | YFinance ordinary wrapped path is single-call; exception matrix still incomplete | SHADOW MORE / no retry restoration |
| E05 | provider capability boundary | Golden Contract identified | SHADOW |
| E06 | Agent read-set/token | benchmark spec | SHADOW |
| E07 | Headroom/tool output | protected-field benchmark spec | SHADOW only |
| E08 | config facts | bounded drift matrix + Shadow test; STOCK_LIST and empty fallback semantics protected | SHADOW / tests or imported constants only |
| E09 | pipeline/read-set | HK symbol representative task measured at 7 file reads | SHADOW evidence |
| E10 | failure taxonomy | expanded differential found real divergences | SHADOW MORE; universal framework REJECT |
| E11 | cache semantics | positive TTL boundary passes; lifecycle/read-set comparison incomplete | SHADOW boundary only; abstraction UNKNOWN, broad unification REJECT |
| E12 | symbol semantics | fixture corpus + full routing differential + 9→3 call-site delta | PROMOTION CANDIDATE; production owner review still required |

## Strongest current DELETE candidates

Not production-approved:

1. **E12 suffix wrappers:** full Shadow differential preserves market-tag and daily/realtime route decisions across CN/HK/US, JP/KR/TW, unknown and adversarial suffix inputs. The measured 9 wrapper-call expressions reduce to 3 Shadow lookups (-6), with `net_complexity_result = SMALLER`; production deletion remains frozen pending owner authorization.
2. **E03 YFinance:** retry machinery is behaviorally inactive on the ordinary wrapped transport path; keep production unchanged until the remaining exception/fallback matrix decides whether dead machinery can be deleted.
3. **E08 config literals:** only aligned numeric/backend defaults are candidates; use tests/imported constants, exclude `STOCK_LIST`, and preserve missing-versus-empty fallback semantics. `net_complexity_result = UNKNOWN`.
4. **E11 positive snapshot cache mechanics:** TTL predicate boundary is Shadow-pass only. A generic abstraction is rejected; a local primitive remains `net_complexity_result = UNKNOWN` until lifecycle/read-set evidence proves it smaller.

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
head: 25cbb5af564d58b2fea763b5d586e7a7f30b8be1
commit: test: fix E12 routing differential imports
mode: Research / Shadow only
production runtime: unchanged
PR #71: open, unmerged
exact-head checks: CI #221 success; Research Radar Tests #239 success
```
