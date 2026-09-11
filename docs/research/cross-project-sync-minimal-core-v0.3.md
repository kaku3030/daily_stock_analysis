# CROSS-PROJECT SYNC — Minimal Core Initiative V0.3

Timestamp: 2026-09-11 JST  
Canonical PR: #71  
Status: RESEARCH / SHADOW ONLY — NO PRODUCTION RUNTIME CHANGE

## Executive delta from V0.2

V0.3 moves from architectural references into concrete repository findings.

New durable experiments/audits:

- **E03 Retry / Fallback Semantic Inventory**
- **E05 Provider Escape Surface Audit**
- **E06 Agent Read-Set / Token Benchmark**

The current highest-value simplification hypotheses are now:

1. Efinance has a Tenacity retry decorator configured for only one attempt; test whether it can be removed without changing exception/fallback semantics.
2. Retry, source/provider failover, cooldown, timeout, circuit breaker, and fail-open must remain distinct semantics.
3. `DataCapabilityService` duplicates provider/routing/configuration knowledge and reaches through private manager/fetcher internals.
4. A manager-owned, immutable/read-only provider capability/routing snapshot may reduce duplication and agent read-set without creating a second runtime owner.
5. Current large-file/read-set cost must be measured directly before any token-saving claim.

## Global invariant

```text
Raw Provider Evidence
        ↓
AI Monitor authoritative provider/runtime boundary
        ↓
Governed normalized state / read-only snapshots
        ↓
Research / diagnostics / model projection
```

Never:

```text
Diagnostics registry → second routing truth
LLM/compression → canonical provider/currentness state
Generic retry → semantic failures become apparent success
```

## AI_MONITOR/HARVEST

### New findings

- Efinance imports/uses Tenacity but `_fetch_raw_data()` currently has `stop_after_attempt(1)` while comments/docs still describe multi-attempt retry.
- AkShare has both true transient retry and separate Eastmoney/Sina/Tencent fallback; these must not be conflated.
- `DataFetcherManager._run_with_retry()` is a custom total-budget-aware retry loop used by fundamental blocks.
- Futu largely uses fail-open/availability state, not generic retry.
- Longbridge contains cooldown and headless OAuth fail-loud semantics that should not become blind retries.

### Next research

- build E03-A exception-surface differential for Efinance;
- classify manager retry errors into transient vs semantic classes;
- inventory circuit breakers/cooldowns separately from retry.

### Do not do

- no blanket Tenacity migration;
- no retry on entitlement/auth/stale/UNKNOWN by default;
- no change to Delivery single-attempt semantics.

## AI_MONITOR/CONTROL_TOWER

### Control decision

Promote E03 and E05 to **Shadow design/test comparison**, not production refactor.

Highest-value candidate interface:

```text
DataFetcherManager
      ↓ read-only
capability_snapshot() / routing_snapshot()
      ↓
DataCapabilityService presentation only
```

This is a research shape, not an approved API name.

Promotion requires output equivalence, singular runtime ownership, no secret leakage, explicit UNKNOWN, unchanged routing order, and lower private-attribute/read-set cost.

## RADAR/HARVEST

Use E06 methodology for research-engine simplification as well:

- fresh-context task;
- files/bytes/tokens read;
- semantic owners touched;
- time to identify authoritative rule;
- correctness gate before savings count.

No large Strategy Lab/Replay refactor follows automatically from AI Monitor provider findings.

## RADAR/CONTROL_TOWER

Radar production/research ownership remains unchanged.

Potential transferable principle only:

> one executable owner for stable classification/gate semantics; provider-specific wire details stay at the adapter edge.

Any Radar adoption requires its own differential/replay evidence.

## RADAR/PERCEPTION_DATA_INTELLIGENCE

Contribute fixtures/evidence for:

- provider capability semantics;
- market/symbol classification edge cases;
- timestamp/timezone observations;
- entitlement/subscription observations;
- provider error categories;
- reconnect/restart sequences.

Do not implement a provider runtime or second currentness engine.

## Main Control & Trading Desk

No portfolio/trading behavior change.

This initiative remains infrastructure/reliability research. No HOLD/ADD/REDUCE/EXIT decision should consume Shadow Minimal Core outputs until they are promoted through AI Monitor governance.

## A-Share Radar / US Stock Radar / Global Policy Intelligence

No trading/discovery semantics changed.

Relevant future benefit if validated:

- lower tool/repository context cost;
- clearer provider health and UNKNOWN states;
- fewer architecture mistakes caused by duplicated source-priority knowledge.

No market signal or candidate score is modified by V0.3.

## Measured structural baseline added

E06 records repository byte-size evidence only as a read-set baseline, not as a quality score or token claim. Examples currently include:

- `realtime_monitor/server.py` ~304 KB;
- `data_provider/base.py` ~207 KB;
- `data_provider/akshare_fetcher.py` ~104 KB;
- `data_provider/efinance_fetcher.py` ~56 KB;
- `src/services/data_capability_service.py` ~46 KB.

Token savings must be measured with the same tokenizer/model/tooling before/after.

## V0.3 next execution order

1. E03-A — Efinance exception/fallback differential.
2. E05-A — current capability output fixture matrix.
3. E06 baseline — fresh-agent read-set measurement for Currentness/provider/retry tasks.
4. E03-B — manager budget-aware retry Shadow comparison if classification evidence supports it.
5. Headroom Layer-B tool-output benchmark after structural read-set baseline exists.

## Sync status

Sync to:
- `AI_MONITOR/HARVEST`
- `AI_MONITOR/CONTROL_TOWER`
- `RADAR/HARVEST`
- `RADAR/CONTROL_TOWER`
- `RADAR/PERCEPTION_DATA_INTELLIGENCE`
- `STOCK RAZOR｜Main Control & Trading Desk`
- `STOCK RAZOR｜A-Share Radar`
- `STOCK RAZOR｜US Stock Radar`
- `STOCK RAZOR｜Global Policy Intelligence`
