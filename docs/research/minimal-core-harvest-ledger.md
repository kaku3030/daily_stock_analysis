# Minimal Core External Harvest Ledger

**Initiative:** STOCK RAZOR Minimal Core Initiative  
**Mode:** research-only; no vendoring or production replacement from this ledger alone.

The goal is to harvest *design leverage*, not copy fashionable architecture. A small external project is useful only if its idea reduces Stock Razor semantic complexity without weakening runtime truth, `UNKNOWN`, currentness, risk, replay, or auditability.

## Decision summary

| Source | Primary lesson | Razor target | Decision |
| --- | --- | --- | --- |
| `mattpocock/skills` | phase boundaries, context pointers, fresh-context tickets, handoff | agent workflow | **ADAPT** |
| `headroomlabs-ai/headroom` | compress large/repetitive tool output before LLM | logs/JSON/tool output | **SHADOW** |
| `karpathy/micrograd` | expose a tiny semantic core; keep mechanism legible | pure decision/replay cores | **ADAPT principles** |
| `karpathy/nanoGPT` | minimal end-to-end path with few indirections | orchestration/read-set reduction | **ADAPT principles** |
| `karpathy/llama2.c` | one explicit execution path; abstractions only when they earn their cost | runtime hot paths | **ADAPT principles** |
| `tinygrad/tinygrad` | small composable primitives, aggressive simplification | data/compute/research architecture | **ADAPT / SHADOW** |
| `pytransitions/transitions` | explicit state machine instead of scattered state branches | currentness/delivery/lifecycle candidates | **SHADOW** |
| `jd/tenacity` | centralized retry policy/composition | provider/API retry glue | **ADOPT existing dependency where semantics match** |
| `dbader/schedule` | tiny in-process scheduling vocabulary | simple non-durable schedules | **KEEP/ADOPT narrowly** |
| `cachetools/cachetools` | bounded/TTL caches as explicit primitives | non-authoritative caches | **ADOPT narrowly** |
| `simonw/llm` | thin provider/plugin boundary and CLI composition | AI/provider adapters | **ADAPT** |
| `kernc/backtesting.py` | concise event/research loop | Replay/OOS/Strategy Lab research | **SHADOW** |

## Harvest cards

### H01 — `mattpocock/skills`

- **Problem solved:** engineering agents accumulate too much context and repeatedly reopen decisions.
- **Core shape:** small `SKILL.md` workflows composed around explicit phase boundaries.
- **Key ideas:** context pointers, progressive disclosure, tracer-bullet tickets, tight debugging loops, fresh context per implementation ticket, handoff, separate review axes.
- **Why it stays small:** workflow knowledge is declarative and reached on demand instead of duplicated in every prompt/session.
- **Not transferable:** its issue-tracker conventions and generic review model cannot override Stock Razor governance or ownership.
- **Razor target:** repository agent workflow and AI collaboration assets.
- **Expected value:** lower token/read-set, less design drift, faster implementation and review.
- **License/attribution:** MIT; attribution required if substantial source text/code is copied. Stock Razor adaptation should prefer original repo-native wording.
- **Decision:** **ADAPT**. Initial adaptation is tracked separately from this research initiative.

### H02 — `headroomlabs-ai/headroom`

- **Problem solved:** repetitive tool outputs, logs, and structured payloads consume LLM context.
- **Core shape:** interception/compression layer before model context.
- **Key idea:** data-type-aware compression/deduplication/sampling rather than blind text truncation.
- **Why it stays useful:** large JSON/log payloads often contain much more repetition than semantic information.
- **Not transferable:** Stock Razor governance fields cannot be sampled away. Runtime truth, timestamps, `UNKNOWN`, gate results, reason/risk fields, portfolio state, and lifecycle identifiers need protected passthrough rules.
- **Razor target:** GitHub/CI logs, provider JSON, replay output, large tool responses.
- **Expected value:** token and latency reduction after workflow-level context reduction is already in place.
- **Risk:** semantic loss can be silent and therefore more dangerous than token waste.
- **Decision:** **SHADOW** only. Require Critical Field Recall and decision/gate equivalence benchmarks before promotion.

### H03 — `karpathy/micrograd`

- **Problem solved:** automatic differentiation and a neural-network layer with an intentionally tiny educational core.
- **Core shape:** a very small value/graph primitive, explicit operations, and a direct backward traversal.
- **Key idea:** make the semantic object obvious and build capability by composition instead of framework layers.
- **Why it stays small:** no redundant manager/service/factory hierarchy around the core mathematical state.
- **Not transferable:** educational minimalism omits many production concerns; Stock Razor cannot discard observability, retries, persistence, governance, or recovery merely to emulate the size.
- **Razor target:** deterministic decision functions, gate evaluation, replay calculation seams.
- **Expected value:** easier reasoning, tests, replay, and smaller agent read-set.
- **Decision:** **ADAPT principles**.

### H04 — `karpathy/nanoGPT`

- **Problem solved:** end-to-end GPT training/finetuning with a deliberately simple and fast repository.
- **Core shape:** a short path from configuration/data to model/training loop rather than a framework of interchangeable layers.
- **Key idea:** make the common path obvious; do not pre-abstract hypothetical requirements.
- **Why it stays small:** limited indirection and a narrow supported contract.
- **Not transferable:** Stock Razor necessarily has more provider, market, restart, and audit heterogeneity.
- **Razor target:** orchestration and hot-path read-set reduction.
- **Expected value:** fewer pass-through layers and lower cognitive/agent context cost.
- **Decision:** **ADAPT principles**.

### H05 — `karpathy/llama2.c`

- **Problem solved:** Llama 2 inference in one pure-C implementation path.
- **Core shape:** explicit loading, tensor operations, transformer execution, and sampling without a large runtime framework.
- **Key idea:** a readable execution path can be more maintainable than an abstraction forest when the domain is stable.
- **Why it stays small:** few semantic owners and almost no architectural ceremony between data and execution.
- **Not transferable:** production Stock Razor needs explicit module boundaries where ownership/security/recovery semantics differ; one giant file is not a target architecture by itself.
- **Razor target:** provider normalization/currentness/delivery hot paths—specifically as a lesson in reducing indirection, not co-locating everything.
- **Expected value:** faster debugging and smaller read-set if execution paths become explicit.
- **Decision:** **ADAPT principles**.

### H06 — `tinygrad/tinygrad`

- **Problem solved:** deep-learning computation/compiler/runtime behavior with a small set of composable primitives.
- **Core shape:** a minimal tensor/graph core with aggressive lowering and explicit transformations.
- **Key idea:** a small intermediate representation can replace many special-case paths when the semantics are truly shared.
- **Why it stays small:** complexity is concentrated in reusable transformations instead of duplicated frontend cases.
- **Not transferable:** a compiler-style IR is overkill unless Stock Razor first proves repeated provider/gate/state patterns share one stable semantic model.
- **Razor target:** repeated normalization/mapping and research calculation pipelines.
- **Expected value:** possible branch reduction and more testable transformations.
- **Decision:** **ADAPT / SHADOW**. Study first; do not create a new generic framework.

### H07 — `pytransitions/transitions`

- **Problem solved:** explicit finite-state behavior in Python.
- **Core shape:** declared states/transitions with conditions/callbacks rather than scattered state mutation.
- **Key idea:** when a concept is genuinely a state machine, declare the legal graph once.
- **Why it stays small:** transition vocabulary replaces repeated `if status == ...` logic.
- **Not transferable:** adding a dependency is not automatically simpler. A tiny local enum/table may be superior for a small stable graph. Callbacks can also hide important side effects if overused.
- **Razor target:** Currentness, Delivery/Entitlement/Subscription, possibly trade/research lifecycle states.
- **Expected value:** one state owner, explicit illegal transitions, easier adversarial tests.
- **Decision:** **SHADOW**. Compare a library-backed prototype with a local table-driven implementation before choosing.

### H08 — `jd/tenacity`

- **Problem solved:** retry/backoff/stop/retry-condition composition.
- **Core shape:** one retry decorator/policy vocabulary instead of handwritten loops.
- **Key idea:** retry policy is a contract and should be centralized rather than duplicated across provider call sites.
- **Why it stays small:** policy composition replaces custom counters/sleeps/exception ladders.
- **Not transferable:** retries must never turn semantic invalidity, entitlement failure, stale data, or `UNKNOWN` into apparent success.
- **Razor target:** transport/transient provider/API failures only.
- **Current repo note:** `tenacity` is already a dependency; the first question is whether custom retry glue duplicates it.
- **Expected value:** deletion of bespoke retry loops and more consistent observability.
- **Decision:** **ADOPT existing dependency where semantics match**; audit before changing code.

### H09 — `dbader/schedule`

- **Problem solved:** small human-readable in-process job scheduling.
- **Core shape:** direct job registration and polling loop.
- **Key idea:** simple scheduling should stay simple when durability is not required.
- **Why it stays small:** no distributed scheduler semantics are pretended where none are needed.
- **Not transferable:** cannot replace restart-aware continuity, durable reconciliation, market-calendar/currentness semantics, or authoritative runtime state.
- **Razor target:** non-critical/simple periodic chores only.
- **Current repo note:** `schedule` is already a dependency; prefer consolidation over another scheduler.
- **Decision:** **KEEP/ADOPT narrowly**; **REJECT** as a replacement for durable/runtime-critical scheduling.

### H10 — `cachetools/cachetools`

- **Problem solved:** bounded and TTL caching using standard mapping-like primitives.
- **Core shape:** explicit cache policy attached to a small container/decorator abstraction.
- **Key idea:** cache policy should be visible and reusable rather than custom timestamp dictionaries scattered through code.
- **Why it stays small:** eviction/TTL behavior is delegated to a proven primitive.
- **Not transferable:** caches must never become a second source of truth for Portfolio, Currentness, Delivery, Lifecycle, or continuity state.
- **Razor target:** non-authoritative API/reference/cacheable computation paths.
- **Current repo note:** `cachetools` is already a dependency.
- **Decision:** **ADOPT narrowly** after locating duplicate cache glue.

### H11 — `simonw/llm`

- **Problem solved:** a compact CLI/library boundary across multiple LLM providers and plugins.
- **Core shape:** a stable user-facing invocation model with provider/plugin extensions kept at the edge.
- **Key idea:** keep the central orchestration contract small; provider peculiarities stay in adapters/plugins.
- **Why it stays small:** a narrow core interface avoids leaking provider-specific options everywhere.
- **Not transferable:** Stock Razor requires stronger runtime evidence, reproducibility, cost/risk controls, and model-output governance than a general CLI.
- **Razor target:** AI invocation/provider boundary and model adapter read-set.
- **Expected value:** fewer provider conditionals in orchestration and a clearer mock/test seam.
- **Decision:** **ADAPT**.

### H12 — `kernc/backtesting.py`

- **Problem solved:** approachable strategy backtesting with a compact user model.
- **Core shape:** data + strategy callbacks + broker/backtest loop.
- **Key idea:** deterministic research loops benefit from a small explicit state surface and reproducible inputs.
- **Why it stays small:** user strategy semantics are narrow; execution is centralized.
- **Not transferable:** must not become a second Stock Razor runtime or override existing Strategy Lab / lifecycle governance. Simplified broker assumptions may be unsuitable for production trading semantics.
- **Razor target:** Radar Replay/OOS/Strategy Lab research only.
- **Expected value:** cleaner research seam, less mutable orchestration, easier differential evaluation.
- **Decision:** **SHADOW**.

## First-wave promotion order

1. **Promote research/inspection immediately:** existing-dependency consolidation (`tenacity`, `schedule`, `cachetools`) because it can remove duplicate glue without introducing another dependency.
2. **Promote design comparison:** explicit Currentness/Delivery state modeling (`pytransitions` vs local table-driven graph), but keep it Shadow until adversarial fixtures pass.
3. **Promote workflow principles:** small-core/pure-function/read-set ideas from Karpathy/tinygrad into code review and baseline analysis—not into production refactors yet.
4. **Keep Headroom in Shadow:** measure after workflow and code read-set reductions so compression does not hide architecture debt.
5. **Keep backtesting reference research-only:** useful for Replay/OOS design, never as a parallel production runtime.

## Next harvest questions

- Which existing retry loops bypass or duplicate `tenacity`?
- Which timestamp/TTL dictionaries duplicate `cachetools` and which are actually authoritative state that must *not* be cached?
- Can Currentness and Delivery states be enumerated into small transition tables with illegal transitions made explicit?
- How many files must an agent currently read to change one provider/currentness path safely?
- Which Radar replay/gate calculations can become pure, fixture-driven functions without changing governance semantics?
