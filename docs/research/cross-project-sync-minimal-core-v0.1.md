# CROSS-PROJECT SYNC — Minimal Core Initiative V0.1

Timestamp: 2026-09-11 JST
Source: Minimal Core Initiative / external Harvest
Canonical PR: #71
Status: RESEARCH-ONLY / NO PRODUCTION RUNTIME CHANGE

## Executive signal

Stock Razor should now optimize for **Minimum Semantic Code**, not merely fewer lines of code. The goal is to reduce state owners, duplicated contracts, repeated branches, pass-through glue, hidden fallbacks, and the agent read-set required to make a safe change.

External references, including Headroom and other strong open-source projects, are research inputs only. Nothing is promoted because it is popular or elegant; promotion requires differential/replay evidence, ownership safety, explicit UNKNOWN/currentness preservation, rollback, and no regression in governed behavior.

## Global rules for every lane

1. Preserve canonical truth and raw evidence.
2. Never compress or summarize away UNKNOWN, INDETERMINATE, timestamps/currentness, provider status, entitlement/subscription status, gate results, reason codes, or risk flags.
3. AI-facing compression/context reduction may exist only as a projection layer; it must never become source of truth.
4. Reversible/local retrieval is preferred when compression is tested.
5. Smaller LOC is not sufficient evidence. Measure semantic owners, branch count, contract duplication, fan-out, agent read-set, diagnosis time, replay determinism, and regression rate.
6. Mature libraries may replace bespoke glue only after behavior-equivalence tests.
7. Foundation & Data Reliability freeze remains authoritative. This initiative does not reopen FEATURE / STRATEGY / UI / AI_TRADER / NEW_LENS work.

## Sync: AI_MONITOR/HARVEST

Primary responsibility:
- research Headroom-style context compression
- study retry/scheduling/cache/library replacements
- study small-core agent/runtime architectures

Immediate harvest priorities:
- Headroom: reversible local compression, tool-output reduction, cross-agent memory patterns
- tenacity: retry consolidation candidates
- schedule: scheduler simplification candidates
- cachetools: cache ownership and expiry simplification
- Simon Willison `llm`: small composable AI invocation patterns
- Karpathy/tinygrad-style small-core design as architecture references

Required output:
- transferability decision: ADOPT / ADAPT / SHADOW / REJECT
- exact Stock Razor target surface
- semantic risks
- test/replay plan
- rollback path
- owner impact

Do not implement production Provider Worker, Portfolio runtime truth, Currentness runtime, notifications, AI invocation runtime, or Shadow/LIVE runtime outside AI Monitor ownership.

## Sync: AI_MONITOR/CONTROL_TOWER

Control decision:
- treat Minimal Core as a governed simplification program, not a refactor campaign
- permit research/docs/tests and tightly scoped reliability fixes
- require fail-loud behavior where evidence is incomplete
- require UNKNOWN to remain explicit

Top AI Monitor simplification candidates:
1. realtime_monitor semantic-core extraction
2. Currentness table/state-machine candidate
3. Delivery/Entitlement status normalization
4. retry consolidation
5. scheduler consolidation
6. cache ownership/expiry consolidation
7. provider normalization boundary
8. agent-facing tool-output projection/compression

Promotion gate:
- behavior-equivalent tests pass
- adversarial currentness cases pass
- runtime ownership unchanged
- raw evidence still retrievable
- semantic metrics improve
- rollback is trivial and explicit

## Sync: RADAR/HARVEST

Primary responsibility:
- research minimal research-engine architectures
- study table-driven gates/state models
- study replay-first testing patterns
- evaluate whether context compression can reduce research-agent read-set without touching canonical evidence

Priority external references:
- pytransitions/transitions for lifecycle/state-machine simplification
- backtesting.py for compact replay/research interfaces
- Karpathy/tinygrad for small composable core design
- Headroom only for LLM-facing research context, never candidate/evidence truth

Required output:
- candidate simplification
- Evidence -> Gate -> Narrative impact
- replay/OOS validation plan
- Candidate/Gate stability impact
- expected read-set reduction

## Sync: RADAR/CONTROL_TOWER

Control decision:
- preserve Candidate Discovery, RS, Capital Persistence, Lifecycle, Replay/OOS, Strategy Lab, Model Evaluation ownership in Radar
- no production decision runtime may emerge from Minimal Core work
- no compensatory scoring may be reintroduced through simplification

Top Radar simplification candidates:
1. Gate/schema mapping -> table-driven candidates
2. Lifecycle state representation
3. Replay/OOS harness ergonomics
4. candidate/research scoring duplication
5. research-agent context projection

Required invariants:
- Evidence -> Gate -> Narrative remains one-way
- Narrative reads only governed fields
- model expresses; system decides
- Decision Quality != P&L
- RULES_IN_CODE_NOT_MEMORY remains enforced

## Sync: RADAR/PERCEPTION_DATA_INTELLIGENCE

Primary responsibility:
- test data semantics that simplification must not damage
- define canonical provider/timestamp/currentness fixtures
- provide raw capture/replay evidence for differential tests

Specific work:
- create adversarial fixtures for pre-open, lunch break, post-close, timezone boundaries, missing timestamps, provider UNKNOWN fields
- distinguish canonical raw payload from normalized projection
- measure whether any compression changes units, timestamps, null/UNKNOWN semantics, provider status, breadth/flow/regime evidence

Hard boundary:
- this lane researches provider semantics and data quality but must not create a second Provider Worker, LiveFeed runtime, or Currentness runtime.

## Sync: STOCK RAZOR | Main Control & Trading Desk

Portfolio decision logic is unchanged. Minimal Core is an engineering acceleration initiative only.

Main should consume future benefits only after governed promotion:
- faster evidence delivery
- smaller agent context
- lower semantic drift
- more reliable currentness/status handling
- faster diagnosis and safer change velocity

No HOLD / ADD / REDUCE / EXIT / NO TRADE rule changes are authorized by this initiative.

## Sync: STOCK RAZOR | A-Share Radar

No strategy change.
Future benefit target:
- smaller research context
- more deterministic sector/theme/RS/capital-persistence evidence transport
- less duplicated gate logic

Any compression layer must preserve price, breadth, RS, capital persistence, timestamps and UNKNOWN exactly enough for downstream gates.

## Sync: STOCK RAZOR | US Stock Radar

No strategy change.
Future benefit target:
- reduce premarket/opening/close audit context overhead
- keep leadership/capital-persistence/lifecycle evidence canonical
- avoid model-context bloat without altering Entry Gate semantics

## Sync: STOCK RAZOR | Global Policy Intelligence

No policy/macro logic change.
Future benefit target:
- compress long source/tool outputs only after canonical evidence capture
- preserve Global Event -> Transmission Channel -> Market/Theme -> Expected Price Acceptance chain
- never remove uncertainty/confidence/source timestamps during compression

## Initial Top 10 simplification map

1. Realtime Monitor read-set / semantic-core extraction
2. Currentness state machine/table-driven implementation candidate
3. Delivery / Entitlement / Subscription status normalization
4. Retry consolidation
5. Scheduler consolidation
6. Cache/TTL ownership consolidation
7. Provider normalization boundary
8. Replay/OOS harness simplification
9. Gate/schema table-driven mapping
10. Agent context/tool-output projection and reversible compression

## First validation experiments

### Experiment A — Retry consolidation
Compare bespoke retry branches against a single governed retry policy. Measure branch count, behavior equivalence, failure classification, and retry timing.

### Experiment B — Currentness differential model
Implement a pure shadow candidate using table/state-machine semantics. Replay currentness fixtures against existing behavior. Any mismatch affecting UNKNOWN, market-session boundaries, or fail-loud behavior blocks promotion.

### Experiment C — Realtime Monitor semantic read-set
Map what an agent must read to safely change one pure domain rule. Extract only if behavior, ownership, and tests remain unchanged. Measure read-set before/after.

## HEADROOM-specific ruling

Current decision: SHADOW / RESEARCH, not production integration.

Potentially useful:
- local compression
- reversible retrieval
- tool-output/context reduction
- cross-agent memory ideas

Forbidden placement:
- before canonical provider evidence capture
- as Portfolio runtime truth
- as Currentness authority
- as Gate authority
- as replacement for raw evidence/replay fixtures

The acceptable architecture is:

Canonical Raw Evidence -> Governed Normalization -> Canonical State -> Optional LLM Projection/Compression -> Model

Never:

Provider Payload -> Compression/Summary -> Canonical State

## Required cross-lane feedback loop

Every future Harvest finding that could affect production must report:
- source_lane
- external_source
- target_surface
- proposed_decision
- owner
- invariants_at_risk
- UNKNOWN/currentness impact
- replay/test evidence
- semantic complexity delta
- agent read-set delta
- rollback
- promotion status
- conflicts_with_other_lanes
- next_validation_condition

Sync targets:
- AI_MONITOR/HARVEST
- AI_MONITOR/CONTROL_TOWER
- RADAR/HARVEST
- RADAR/CONTROL_TOWER
- RADAR/PERCEPTION_DATA_INTELLIGENCE
- STOCK RAZOR | Main Control & Trading Desk
- STOCK RAZOR | A-Share Radar
- STOCK RAZOR | US Stock Radar
- STOCK RAZOR | Global Policy Intelligence

## Final status

Minimal Core Initiative V0.1 is now a shared cross-project research program.

Principle:

**Grow capability while shrinking the semantic core.**

No lane may treat this document as authorization to bypass existing governance, ownership, Foundation freeze, or production promotion gates.
