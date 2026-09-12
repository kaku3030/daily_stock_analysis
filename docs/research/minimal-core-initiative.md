# STOCK RAZOR Minimal Core Initiative

**Status:** `INITIATIVE_OPEN / RESEARCH_ONLY`  
**Phase:** `Phase 0 — Baseline` + `Phase 1 — External Harvest`  
**Primary metric:** **Minimum Semantic Code**, not minimum LOC.

## Purpose

The Minimal Core Initiative studies small, high-leverage systems and uses those lessons to reduce the amount of semantic machinery required to preserve Stock Razor behavior.

The desired outcome is not merely fewer lines. It is fewer state owners, duplicated contracts, branches, pass-through layers, hidden fallbacks, special cases, and files an agent must read before making a safe change.

Expected benefits:

- lower agent context and token load
- faster implementation and review
- faster bug reproduction and diagnosis
- smaller regression surface
- clearer runtime/research ownership
- more deterministic replay and testing

This initiative is complementary to the repository AI collaboration workflow (`spec -> tracer-bullet tickets -> fresh context -> implement -> review -> handoff`) and to later tool-output compression experiments. The workflow reduces context waste between phases; Minimal Core reduces the amount of system context that exists in the first place.

## Hard boundaries

1. **Research first.** No production rewrite is promoted because it is shorter or more elegant.
2. **Existing ownership is authoritative.**
   - AI Monitor owns Provider Worker, LiveFeed/runtime truth, Portfolio runtime truth, Currentness runtime enforcement, continuity/restart/reconciliation, notification runtime, AI invocation/runtime, and Shadow/LIVE runtime.
   - Radar owns Candidate Discovery, Relative Strength, Capital Persistence, Lifecycle research, Replay/OOS, Strategy Lab, Model Evaluation, and Candidate/Research scoring.
   - Perception/Data Intelligence may contribute observational evidence, provider semantics, fixtures, and replay material, but must not create a second production runtime.
3. **No semantic weakening.** Simplification must preserve fail-loud behavior, `UNKNOWN`, currentness, risk, and audit semantics.
4. **No opportunistic wide refactor.** Do not mix a broad simplification into an unrelated fix or feature.
5. **Prefer removal over layering.** Prefer deletion, merging, standard/established primitives, declarative tables, pure functions, and single state owners over additional abstraction layers.
6. **A smaller diff is not automatically simpler.** Track states, owners, branches, fan-out, dependencies, test seams, and agent read-set in addition to LOC.
7. **Rules live in durable artifacts.** The initiative does not replace `AGENTS.md` as the repository governance source of truth.

## Research lanes

### Lane A — Minimal systems and design exemplars

Study projects where complex behavior is expressed through unusually small, legible cores.

Initial references include:

- `karpathy/micrograd`
- `karpathy/nanoGPT`
- `karpathy/llama2.c`
- `tinygrad/tinygrad`

Questions:

- What did the authors deliberately *not* abstract?
- What is the real semantic core?
- Which complexity is represented as data/configuration instead of branch-heavy code?
- How are invariants exposed rather than hidden behind layers?

### Lane B — Runtime/state/scheduling/retry primitives

Study whether home-grown glue can be removed or compressed by proven primitives.

Initial references:

- `pytransitions/transitions`
- `jd/tenacity`
- `dbader/schedule`
- `rq/rq`
- `cachetools/cachetools`

Target areas:

- currentness state
- delivery/entitlement/subscription state
- worker lifecycle
- continuity/restart state
- retry/backoff
- scheduling
- bounded/TTL caches that are *not* runtime truth

### Lane C — Trading/replay/research engines

Study concise deterministic research and backtesting designs without importing a second production architecture.

Initial reference:

- `kernc/backtesting.py`

Questions:

- Can replay and strategy evaluation use fewer mutable owners?
- Can gates/entry/exit evaluation become table-driven or pure-function oriented?
- Which abstractions improve OOS/replay determinism rather than code aesthetics only?

### Lane D — Agent/context/tooling efficiency

Continue the existing harvest of:

- `mattpocock/skills`
- `headroomlabs-ai/headroom`
- `simonw/llm`

Targets:

- context pointers and progressive disclosure
- fresh context per ticket
- compact durable handoffs
- tool-output compression
- provider/plugin boundaries with minimal glue

## Audit dimensions

Each subsystem is evaluated across the following dimensions:

| Dimension | Question |
| --- | --- |
| LOC / file size | Where is sheer volume concentrated? |
| Branch count | Where are provider/status/state branches repeated? |
| State owners | Is the same state represented or mutated in multiple places? |
| Contract duplication | Are schemas, enums, validation, or mappings repeated? |
| Fan-out | Does one semantic change require edits across unrelated areas? |
| Pass-through layers | Which wrappers add no new semantics? |
| Hidden fallback | Where can failure silently become stale/default data? |
| I/O coupling | Can judgment become `input -> output` pure logic? |
| Replay seam | Can behavior be reproduced deterministically? |
| Agent read-set | How much code/context must an agent read to change this safely? |

## Decision vocabulary

Every finding ends in one of these states:

- **KEEP** — complexity is justified or protective.
- **SIMPLIFY** — preserve owner/behavior with fewer states, branches, or code paths.
- **MERGE** — duplicate concepts/contracts become one owner.
- **TABLE-DRIVE** — repeated branching becomes declarative data/rules.
- **REPLACE** — a proven primitive/library is demonstrably safer and smaller.
- **DELETE** — dead/redundant compatibility, wrapper, fallback, state, or path.
- **SHADOW** — promising, but differential/replay evidence is still required.
- **REJECT** — externally elegant but incompatible with Stock Razor governance/runtime needs.

## Promotion evidence

A simplification may move from research toward implementation only when all applicable evidence exists:

1. The current behavior and contract are documented.
2. A red-capable regression test or deterministic replay seam exists.
3. Before/after metrics include LOC plus at least one semantic metric (states, owners, branches, dependencies, files/read-set).
4. `UNKNOWN`, fail-loud, currentness, risk, and audit semantics are preserved.
5. Compatibility impact and rollback path are explicit.
6. The production/research owner is explicit; no duplicate runtime is created.
7. High-risk paths have Shadow or differential comparison evidence.

## Phase 0 — Baseline

Produce a repository complexity map without changing production behavior:

- largest/high-read-set source modules
- likely high-branch modules
- duplicate schema/state/mapping hotspots
- adapter/pass-through chains
- runtime vs research ownership map
- Top 10 simplification candidates
- representative agent read-set estimates

Finding format:

`Current -> Pain -> Minimal reference -> Candidate simplification -> Expected gain -> Risk -> Validation seam -> Owner -> Decision`

See `docs/research/minimal-core-current-state.md` for the durable current-state pointer; historical baseline detail is preserved in PR history.

## Phase 1 — External harvest

Each external reference gets a harvest card containing:

- source/revision or current repository reference
- problem solved
- core shape
- key design idea
- why it stays small
- what is not transferable
- Stock Razor target subsystem
- expected speed/token/reliability/maintainability value
- license/attribution considerations
- `ADOPT / ADAPT / SHADOW / REJECT`

No external code is vendored during this phase.

See `docs/research/minimal-core-harvest-ledger-v0.2.md`.

## Success metrics

Track trends rather than vanity targets:

- median files touched per semantic change
- median agent read-set before implementation
- average context/token on representative maintenance tasks, where measurable
- time to a tight red-capable bug reproduction
- duplicate runtime/state owners removed
- branches/state transitions reduced
- replay/test determinism
- regression rate after simplification
- production LOC as a secondary metric only

A change that removes 1,000 LOC but increases hidden state, weakens observability, or makes failures quieter is a failure.

## Control Tower sync contract

### MAIN_SYNC_PACKET — 2026-09-11

- `initiative`: Minimal Core Initiative
- `phase`: Phase 0 baseline + Phase 1 external harvest
- `production_change`: none
- `expected_benefit`: faster agent work, lower token/read-set, smaller bug surface, faster review/debug
- `immediate_targets`: runtime orchestration; currentness/delivery state; provider glue; replay/research loops; agent context/tool output
- `promotion_gate`: evidence + replay/tests + owner boundary + rollback
- `next_validation`: repository complexity map + first 8–12 harvest cards + differential/replay plans for highest-value candidates
- `sync_to_ai_monitor`: findings touching Provider Worker, runtime truth, Currentness, Delivery, continuity/restart, notification, and AI runtime
- `sync_to_radar`: findings touching Candidate/Strategy Lab/Replay/OOS/research scoring and research-engine simplification
- `cross_project_rule`: a harvested design must never create a second production owner

## Definition of done

This initiative remains open until:

- a baseline complexity map exists
- at least 8 high-quality external harvest cards exist
- Top 10 simplification candidates are ranked
- at least 3 candidates have measurable differential/replay validation plans
- Control Tower has explicit Promote/Shadow/Reject decisions for the first wave

No production simplification is merged merely to complete this initiative.
