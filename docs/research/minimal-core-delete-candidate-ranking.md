# Minimal Core — Production DELETE Candidate Ranking

**Mode:** Research / Shadow  
**Exact head under test:** `28865aed45fe65a28c5527b777762325a16a666a`

This ranks deletion candidates by evidence quality and expected semantic risk.
It is not a promotion decision.

| Rank | Candidate | Evidence | Missing gate | Current decision |
| ---: | --- | --- | --- | --- |
| 1 | E12 suffix wrappers and repeated booleans | full routing corpus + one-lookup Shadow equivalence + compatibility scan | production owner authorization and rollback design | **PROMOTION CANDIDATE / FROZEN** |
| 2 | E03 YFinance inactive retry surface | five-case matrix: one provider call; decorated `DataFetchError`/cause surface; undecorated native surface | compatibility review of wrapper deletion; no real retry restoration | **SHADOW MORE; `net_complexity_result = UNKNOWN`** |
| 3 | E08 repeated config literals | five aligned defaults match runtime/registry/example; protected counterexamples remain | imported-constant implementation plus rollback and read-set measurement | **SHADOW; `net_complexity_result = UNKNOWN`** |
| 4 | E11 positive snapshot mechanics | strict TTL boundary plus miss/empty/negative-age model equivalence | real write/clear/thread/logging differential and total read-set accounting | **SHADOW / `net_complexity_result = UNKNOWN`** |
| 5 | E10 classifier merge | expanded differential found real category/detail divergence | no credible path while provider semantics differ | **REJECT for now** |

## Ordering rule

E12 ranks first because it has an existing singular semantic owner and a
small, reversible deletion shape. E03 ranks ahead of configuration/cache
work only as an investigation candidate; its production decision is blocked
by replay evidence. E11 is deliberately below E08 because matching TTL
predicates do not yet prove matching lifecycle, concurrency, or observability
semantics.

No candidate satisfies all promotion gates yet. In particular, none has a
verified rollback artifact and `net_complexity_result = SMALLER` for the
production patch.
