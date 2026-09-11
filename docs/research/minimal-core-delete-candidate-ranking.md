# Minimal Core — Production DELETE Candidate Ranking

**Mode:** Research / Shadow  
**Exact head under test:** `6b1ad363c1c65fc075e3ac7f3df1fd5c77902d23`

This ranks deletion candidates by evidence quality and expected semantic risk.
It is not a promotion decision.

| Rank | Candidate | Evidence | Missing gate | Current decision |
| ---: | --- | --- | --- | --- |
| 1 | E12 suffix wrappers and repeated booleans | fixture corpus + one-lookup Shadow equivalence | full routing corpus, private-import audit, rollback patch | **SHADOW MORE** |
| 2 | E03 YFinance inactive retry surface | ordinary wrapped transport appears behaviorally inactive | replay transient failures, prove no governed retry path is lost | **SHADOW MORE** |
| 3 | E08 repeated config literals | bounded drift matrix identifies duplicate facts | exact-head CI, imported-constant compatibility and rollback | **SHADOW** |
| 4 | E11 positive snapshot mechanics | TTL boundary differential now passes; shapes are similar | write/clear/thread/logging differential and total read-set accounting | **SHADOW** |
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
