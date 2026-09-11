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
| E03 | retry/fallback | Efinance + YFinance evidence | SHADOW / separate retry from fallback |
| E05 | provider capability boundary | Golden Contract identified | SHADOW |
| E06 | Agent read-set/token | benchmark spec | SHADOW |
| E07 | Headroom/tool output | protected-field benchmark spec | SHADOW only |
| E08 | config facts | bounded drift matrix + Shadow test | tests/imported constants before framework |
| E09 | pipeline/read-set | HK symbol representative task measured at 7 file reads | SHADOW evidence |
| E10 | failure taxonomy | expanded differential found real divergences | SHADOW MORE; universal framework REJECT |
| E11 | cache semantics | semantic matrix + TTL boundary differential complete | SHADOW evidence; broad unification REJECT |
| E12 | symbol semantics | fixture corpus + adversarial wrapper Shadow test + 9→3 call-site delta | provider wire remains adapter-local |

## Strongest current DELETE candidates

Not production-approved:

1. **E12 suffix wrappers:** 9 exact-head wrapper-call expressions reduce to 3 Shadow lookups (-6) while preserving the existing classification corpus; production routing equivalence remains pending.
2. **E03 YFinance:** retry machinery may be behaviorally inactive on the ordinary wrapped transport path. Decide KEEP-single-attempt-and-simplify vs governed real retry.
3. **E08 config literals:** backend timeout/output/concurrency defaults are repeated across runtime constants, registry metadata and `.env.example`; tests/imported constants may remove duplicated facts without a config framework.
4. **E11 positive snapshot cache mechanics:** Efinance/AkShare simple `{data,timestamp,ttl}` mechanics may share a tiny primitive if it is genuinely smaller.

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
E12: validate the measured 9→3 call-site delta against routing/adversarial corpus
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
head: f7cea9a5266d1eca46a90647f832f9fd6406dc15
commit: research: sync Minimal Core current-state pointer
mode: Research / Shadow only
production runtime: unchanged
PR #71: open, unmerged
exact-head checks: in progress at sync time
```
