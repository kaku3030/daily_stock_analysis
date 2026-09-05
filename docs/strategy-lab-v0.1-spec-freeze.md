# Strategy Lab V0.1 Spec Freeze

Status: **FROZEN FOR IMPLEMENTATION**

Spec version: **Strategy Lab V0.1**

Frozen on: **2026-09-02**

This document is the implementation baseline for the first Strategy Lab
validation system used by Stock Radar. V0.1 stops adding concepts here. A V0.2
proposal must be based on a concrete failure found in code, an adversarial
fixture, or real market-data validation.

Strategy Lab validates research evidence. It does not place orders, produce
trade instructions, promote an experimental component automatically, or alter
production signal weights.

## First-page rule

The two questions are deliberately separate:

- **Validation Report:** can this result be trusted?
- **Performance Report:** if it can be trusted, how good is it?

Validation and performance must use separate data structures. A validation
gate must not read CAGR, Sharpe, profit factor, win rate, or another performance
metric to offset a validation failure. Strong performance can never average
away a causality, look-ahead, execution, or other Hard Gate failure.

## Frozen delivery order

Implementation follows this dependency order:

1. stabilize the existing Stock Radar runtime;
2. build shared Strategy Lab validation infrastructure;
3. add the permanent adversarial regression suite;
4. add execution and cost realism;
5. add out-of-sample, walk-forward, benchmark, alpha, and regime checks;
6. add component attribution;
7. allow only manually reviewed, validated components to return to the Signal
   Engine.

Breakout/retest and Chandelier research must not bypass this order. They are
initial test subjects for the validation system, not validated strategies.

## Frozen requirements

| ID | Requirement | Acceptance condition |
| --- | --- | --- |
| `SLV01-001` | Validation/performance isolation | Separate report models; validation code has no dependency on performance metrics. |
| `SLV01-002` | Hard Gate before expensive work | Logic, causality, look-ahead, and execution checks run before parameter scans, stress tests, or walk-forward work. |
| `SLV01-003` | No averaging across Hard Gates | One Hard Gate failure makes the validation result fail regardless of soft scores or performance. |
| `SLV01-004` | Parameter Stability Engine | Evaluates nearby parameter values and exposes cliffs; it is not tied to one strategy. |
| `SLV01-005` | Edge Concentration Engine | Measures contribution by time and trade unconditionally, plus symbol/asset, sector, and market regime when their metadata coverage is sufficient, using trade records rather than strategy-specific logic. |
| `SLV01-006` | Cost and execution realism | Tests fees, slippage/spread assumptions, execution causality, and sensitivity to increased cost. |
| `SLV01-007` | OOS and walk-forward | Separates training/selection data from evaluation data and forbids look-ahead between windows. |
| `SLV01-008` | Benchmark and alpha | Compares with a declared benchmark and exposes beta/exposure so market beta is not presented as alpha. |
| `SLV01-009` | Regime robustness | Reports whether evidence depends on a limited market regime; regime results remain validation evidence, not an automatic production weight. |
| `SLV01-010` | Component attribution | Runs controlled component removal/addition experiments to identify which parts contribute evidence. |
| `SLV01-011` | Configuration governance | Validation thresholds live in a dedicated versioned YAML configuration with reason, evidence, introduced-in, and last-changed metadata. |
| `SLV01-012` | Manual promotion | Passing validation creates review evidence only. Production signal logic or weights change only through a separately reviewed change. |

## Permanent adversarial regression suite

Every Validation Engine version must retain five deliberately bad fixtures:

| Fixture | Expected result |
| --- | --- |
| Look-ahead strategy uses future data or an earlier execution price | Hard failure |
| Parameter-overfit strategy wins at one point and collapses nearby | Parameter-cliff failure |
| Concentrated-edge strategy depends on a tiny set of trades, periods, or assets | High-fragility failure |
| Cost-fragile strategy loses its edge under the configured cost stress | Cost-robustness failure |
| Beta-disguised-as-alpha strategy reproduces benchmark exposure | Alpha validation failure |

Missing any one of these known bad cases is a merge blocker for changes to the
Validation Engine. Other passing checks and attractive performance results do
not compensate for that false negative.

Each validation module must also include at least one failing fixture. Tests
must prove both that valid input can proceed and that the relevant defect is
rejected.

## Data and causality invariants

- A signal using a closed bar can be executed no earlier than the next
  executable observation unless the input explicitly proves an intrabar event.
- A T-day close-confirmed signal cannot use the T-day open as its fill.
- A closed 15-minute bar cannot produce an execution timestamp before that bar
  closes.
- Dataset splits, parameter selection, benchmark selection, and regime labels
  must not read evaluation-period outcomes.
- Metric definitions and leverage/exposure units must be declared. An unknown
  annual-return or leverage definition is a validation warning, not an assumed
  fact.
- Strategy edge and position sizing or leverage are assessed separately.

## Initial experiment boundary

The first planned experiment may study a breakout lifecycle:

`WATCH -> BREAKOUT_TRIGGERED -> RETEST_PENDING -> RETEST_HELD -> BREAKOUT_CONFIRMED -> TREND_RUNNING -> PROFIT_PROTECTION -> EXIT/FAILED`

This state sequence is not part of the production Signal Engine in V0.1. The
20-period boundary, 7-period volume average, ATR(14), and 4-ATR Chandelier
values are unvalidated candidate parameters and must not be hard-coded as
production defaults. Volume confirmation and Chandelier protection are
research components until Strategy Lab evidence supports a separate promotion
change.

## Relationship to the existing Stock Radar

The current Stock Radar reliability work is a prerequisite, not an
implementation of Strategy Lab:

| Existing prerequisite | Evidence | Status |
| --- | --- | --- |
| Provider fallback and Critical health transitions | `src/services/stock_radar_v2/health.py`, `tests/test_stock_radar_v2_health.py` | Implemented |
| Independent signal and portfolio confidence | `src/services/stock_radar_v2/confidence.py`, `tests/test_stock_radar_v2_confidence.py` | Implemented |
| Portfolio L3 research gate without signal mutation | `src/services/stock_radar_v2/confidence.py`, `tests/test_stock_radar_v2_confidence.py` | Implemented |
| Validation Queue, Daily QA, Weekly Calibration, manual weight boundary | `src/services/stock_radar_v2/validation.py`, `tests/test_stock_radar_v2_validation.py` | Implemented foundation |
| Read-only provider runtime and technical-state history | `src/services/stock_radar_v2/provider_runtime.py`, `tests/test_stock_radar_v2_provider_runtime.py` | Implemented |

Strategy Lab delivery status:

| Frozen item | Status |
| --- | --- |
| Separate `ValidationReport` and `PerformanceReport` contracts | Implemented foundation |
| Ordered, fail-closed Hard Gate pipeline | Implemented foundation |
| Soft Gate pipeline | Implemented — Foundation |
| Parameter Stability Engine | Implemented — Foundation |
| Edge Concentration Engine | Implemented — Foundation |
| Permanent five-fixture adversarial suite | Implemented |
| Cost/execution stress | Implemented — Foundation |
| Experiment governance (manifest, parameter origin, lineage audit) | Implemented — Foundation |
| OOS/walk-forward, benchmark/alpha, and regime checks | Planned |
| Component attribution | Planned |
| Breakout/retest/Chandelier experiment | Deferred until validation infrastructure exists |

The implemented foundation lives in `src/services/strategy_lab/`. Its Hard
Gate pipeline has no dependency on `PerformanceReport`, evaluates the frozen
gate set in order, and exposes eligibility for expensive validation only after
all Hard Gates pass. It does not yet implement the full production validation
engines or any strategy experiment.

The permanent suite lives in `tests/test_strategy_lab_adversarial.py` and is
explicitly included in the Research Radar CI workflow. Its fixed manifest
contains look-ahead, parameter overfit, concentrated edge, cost fragility, and
beta-disguised-as-alpha cases plus matching valid controls. The deterministic
checks live in `src/services/strategy_lab/adversarial_checks.py`; thresholds
requiring later calibration are explicit inputs, so fixture values do not
become production defaults.

The Parameter Stability Engine foundation lives in
`src/services/strategy_lab/parameter_stability.py`, with its thresholds in
the sibling `strategy_lab_validation.yaml` (loaded through `config.py`,
mirroring the `stock_radar_v2` configuration pattern). It evaluates a
caller-supplied parameter neighborhood and reports plateau width, an
adjacent-neighbor parameter-cliff ratio, and a `stability_label`; it never
reads `PerformanceReport` fields and makes no claim about whether a stable
surface is profitable. It is a standalone, reusable analysis module today —
it is not yet wired into `HardGatePipeline` as a Soft Gate, and the existing
`assess_parameter_stability` adversarial-suite check in
`adversarial_checks.py` is unchanged and remains the permanent regression
fixture for the `parameter_overfit` case.

The Edge Concentration Engine foundation lives in
`src/services/strategy_lab/edge_concentration.py`, with its thresholds in
the same `strategy_lab_validation.yaml` (an `edge_concentration` section
alongside `parameter_stability`). It evaluates a caller-supplied sequence of
trade records and reports concentration across the trade, month, symbol,
sector, and regime dimensions. The frozen minimal input is only
`timestamp` + `pnl` per trade -- `symbol`, `sector`, and `regime` are all
optional dimension metadata, not required fields. Every ratio is measured
against Gross Positive PnL (winning trades only, never net PnL), and every
"Top N%" population is sized off the winning-trade count alone, so padding
the input with zero- or negative-PnL trades cannot dilute a reported
concentration. Fragility Score is the max of normalized HHI across the
always-computed trade/month dimensions and the metadata-coverage-eligible
symbol/sector/regime dimensions -- a weakest-link aggregation; the named
Top-1%/Top-5%/Top-month/Top-3-months/Top-symbol/Top-5-symbols/Top-sector/
Top-regime contribution ratios remain explanatory evidence only and never
feed the score. Missing symbol/sector/regime metadata is never folded into
a synthetic scored bucket or treated as zero risk: it is reported
separately (`symbol_missing_positive_pnl_share` /
`sector_missing_positive_pnl_share` / `regime_missing_positive_pnl_share`),
and when positive-PnL-weighted coverage for that dimension falls below the
configured minimum, only that dimension's official contribution/HHI
figures come back `None` ("unavailable") with an explicit warning -- never
a falsely reassuring low number computed from a handful of known trades --
and trade/month concentration (and any other dimension that does clear its
coverage gate) keeps scoring normally rather than being blocked. It never
reads `PerformanceReport` fields and makes no claim about whether a
diversified edge is profitable. It is a standalone, reusable analysis
module today -- it is not yet wired into `HardGatePipeline` as a Soft Gate,
and the existing `assess_edge_concentration` adversarial-suite check in
`adversarial_checks.py` (a simpler net-PnL-denominated gate) is unchanged
and remains the permanent regression fixture for the `concentrated_edge`
case.

The Cost / Execution Stress Test Foundation lives in
`src/services/strategy_lab/execution_stress.py`, with its thresholds in the
same `strategy_lab_validation.yaml` (an `execution_stress` section). It
answers a Signal-Edge-vs-Execution-Edge question: if commissions are
higher, entry/exit price slippage (including spread) is worse, or fills
are delayed by one or two bars, than assumed, how much of the strategy's
already-realized edge survives? Each trade's minimal input is `side` +
`quantity` + signal timestamps + a mandatory delay-0
`ExecutionPricePoint.reference_price` pair (a causal, executable,
pre-slippage price -- the engine, not the caller, applies slippage on top
of it); the engine computes `gross_pnl = side_sign * (exit_price -
entry_price) * quantity` and `net_pnl = gross_pnl - cost` itself rather
than accepting a caller-supplied PnL, and `quantity` is a required,
explicit, positive unit-conversion input, never inferred from price
movement -- it is used identically across every scenario for a given trade
and never compared or ranked across trades, which is what keeps it out of
Position Sizing Engine territory. Fee (`baseline_fee_cost`, explicit
monetary commission/fees only, full stop -- a PnL-currency amount, scaled
linearly by the cost multiplier) and price slippage (`baseline_entry_slippage_bps`
/ `baseline_exit_slippage_bps` -- two *independently representable* rates,
since entry and exit fills are not guaranteed to face the same friction,
and this is also where bid-ask spread degradation belongs if not already
reflected in `reference_price` -- each a basis-points rate, scaled the
same way but applied to its own side's reference price in the direction
that is actually adverse for the position's side -- LONG: `entry * (1 + k
* entry_slip)` / `exit * (1 - k * exit_slip)`; SHORT: `entry * (1 - k *
entry_slip)` / `exit * (1 + k * exit_slip)`) are modeled separately and
must never double-count the same real-world friction, so a long/short
sign bug in the fee dimension is structurally impossible (pure
subtraction, no price math) and the sign-correctness risk is concentrated
entirely, and deliberately, in the slippage direction formula. The
scenario matrix is `{1.0, 1.5, 2.0}` cost multiplier x `{0, 1, 2}` bar
delay (9 cells); `(1.0x, 0 bars)` is the *one* realistic reference
execution -- delay-0 reference prices, 1x entry/exit slippage, 1x fee --
not a zero-friction fantasy
baseline, and every baseline/reference aggregate net PnL used anywhere in
the module (the top-level eligibility gate, each delay level's own
retention denominator, and the break-even solve) is derived from that same
`(1.0x, 0 bars)` computation path -- never a second, independently
implemented baseline formula. Retention at `(k, d)` is `stressed_net_pnl /
reference_net_pnl`, computed over the *same* eligible cohort `C_d` (trades
with a price point at delay `d`; `C_0` is every trade) on both sides --
denominated only when that cohort's own reference-execution net PnL is
positive; otherwise every scenario cell at that delay level is
`retention=None` with a `delay_{d}_cohort_baseline_not_positive` warning,
the same undefined-ratio reasoning as the top-level
`NO_POSITIVE_BASELINE_EDGE` gate, just scoped to one delay level. A trade
missing a delay-N price point is excluded from that delay level's cohort
entirely -- both numerator and denominator -- never falling back to the
baseline price and never measured against a denominator that still
includes trades the numerator dropped; each non-zero delay level's
*coverage* (a separate, prior gate) is measured as the fraction of
*absolute* baseline gross PnL, over the full trade set, held by trades
that do have a price point there, and below the configured minimum every
scenario cell at that delay level is `retention=None` ("unavailable").
Execution Fragility Score is `1 - clamp(worst_retention, 0, 1)`, where
`worst_retention` is the minimum retention across every eligible scenario
*cell* (the actual joint cost+delay combination, not the max of two
independently-evaluated single axes) -- `worst_retention` itself is
reported unclamped and may be negative. Break-even cost multiplier solves
`A - k*F = 0` along the reference (delay-0) row, where `A` is the raw
zero-friction gross PnL and `F` is total 1x friction (slippage loss plus
fee) -- both derived from two evaluations of the same per-scenario
computation (`cost_multiplier=0.0` and `1.0`) rather than a separately
reimplemented formula, since slippage scales with the cost multiplier
exactly like fee does and an earlier draft's `gross_at_k1 / fee_cost`
implicitly (and incorrectly) held slippage frozen at its k=1 value.
`ExecutionObservation.__post_init__` performs a structural,
input-integrity causality check (an executable timestamp may not precede
its signal timestamp; delay-N timestamps must be non-decreasing with N) --
this is not a substitute for a future Hard Gate. It never reads
`PerformanceReport` fields, is not wired into `HardGatePipeline`, and does
not modify the Parameter Stability Engine, the Edge Concentration Engine,
`adversarial_checks.py`, `hard_gates.py`, the Signal Engine, or the Data
Layer.

The Soft Validation layer lives in
`src/services/strategy_lab/validation_gate.py`. It is a second, independent
evidence system that sits alongside Hard Validation without modifying it:
`ValidationReport` / `HardGatePipeline` are unchanged, and a Hard `PASS`
still means only that the experiment is eligible to continue validation --
not that the strategy is validated. `SoftValidationStatus` has four levels
(`ACCEPTABLE` / `CAUTION` / `FRAGILE` / `INCONCLUSIVE`); three adapters
(`soft_validation_from_parameter_stability` /
`soft_validation_from_edge_concentration` /
`soft_validation_from_execution_stress`) each read *only* the
corresponding Foundation engine's own frozen label field -- never a
numeric score, retention ratio, or other PnL-derived value, so a
contrived mismatch between a result's label and its score cannot change
the mapped status. `SoftValidationReport` requires exactly one result from
each of the three frozen `SoftValidationSource` values and fails closed
(`ValueError`) on a missing, duplicate, or unknown source; its
`overall_status` is re-derived and cross-checked against `results` in
`__post_init__` as an invariant, so even a directly, inconsistently
constructed report fails closed. Aggregation
(`aggregate_soft_validation`) is a precedence pick over the *set* of
per-source statuses -- `FRAGILE > INCONCLUSIVE > CAUTION > ACCEPTABLE`,
deliberately no averaging, weighting, voting, or composite score, matching
the "no averaging across gates" philosophy already frozen for Hard
Validation -- and is therefore structurally order-invariant.
`NO_POSITIVE_EDGE` / `NO_POSITIVE_BASELINE_EDGE` map to `INCONCLUSIVE`,
not a Hard-Gate-style failure, mirroring how the Foundation engines
themselves already separate "no trustworthy edge computable" from "the
edge is bad". This module does not implement `logic_integrity`,
`execution_causality`, or `execution_reality` -- those remain
unimplemented Hard Gates reserved for separate briefs -- and in
particular does not connect `execution_stress` to `execution_reality`:
execution_stress measures robustness to fees/slippage/delay, a
categorically different concern from causal/physical execution validity,
and cost fragility is Soft Validation evidence, never a Hard
execution-reality failure. It introduces no combined Hard+Soft report type
and no higher-level "validated/promotable" promotion decision -- that
remains out of scope for V0.1. It has no dependency on performance: it
does not import `performance_models`, does not accept a
`PerformanceReport`, and reads no CAGR/Sharpe/MaxDD/absolute-return field
-- enforced by a permanent AST-based structural test rather than a raw
string scan, since the module's own docstring explains this same
boundary in prose.

The Experiment Governance Foundation lives in
`src/services/strategy_lab/experiment_governance.py`. It supplies the
experiment identity, parameter provenance, and lineage-audit contracts that
later Strategy Lab work needs in order to say *which* experiment produced a
piece of evidence and *where its parameters came from*. `ExperimentManifest`
carries an open `governed_components` mapping of caller-supplied component
fingerprints, and its `manifest_hash` is
`SHA256(canonical(schema_version + governed_components))`. Identity and
timestamp fields (`experiment_id`, `parent_experiment_id`,
`root_experiment_id`, `created_at`) are excluded **structurally** — the
canonicalizer only ever receives the governed subset, so no future identity
field can be silently swept into the hash the way a denylist would allow.
`RECOGNIZED_GOVERNED_COMPONENTS` is advisory only: unknown component keys
stay valid and are surfaced through `unrecognized_component_keys` purely for
typo visibility, and there is deliberately no anti-shrink test over that key
set, because governance coverage is expected to grow. Canonicalization is
intentionally narrow rather than a general JSON framework — non-string
component keys or fingerprints are rejected outright rather than coerced.
`ParameterOrigin` records FIXED-parameter provenance and enforces that
`PRIOR_EXPERIMENT` requires an `origin_experiment_id` while
`LITERATURE`/`MANUAL_PRIOR` prohibit one, and that
`information_horizon_end <= declared_at`; its fingerprint covers all six
provenance fields. `audit_experiment_lineage` returns an
`ExperimentLineageAudit` whose verdict is `PASS`, `VIOLATION`, or
`INDETERMINATE`, derived and cross-checked from structured
`LineageViolation` records (`code`, `severity`, `message`, `evidence`)
covering root invariants, child/root mismatch, self-parent, lineage cycles,
missing parents, and duplicate experiment identity with a conflicting
definition. Completeness is never inferred from the supplied history: the
caller declares it through `LineageAuditContext.history_complete`, which is
what separates a genuinely missing parent (`VIOLATION`) from one that simply
was not supplied to the audit (`INDETERMINATE`). An `experiment_id` names
exactly one manifest definition permanently, so the same id observed with a
different definition is always a violation, independent of any OOS
consumption state — this Foundation takes no OOS input at all. Governance
datetimes must be timezone-aware and are canonicalized to UTC, with naive
values rejected; this is deliberately stricter than the existing engines,
which are not retrofitted. Its trust boundary is explicit: component
fingerprints are caller-supplied trusted inputs, and `manifest_hash` proves
only that a manifest is a consistent function of the fingerprints it was
handed — never that those fingerprints faithfully represent the external
component contents they describe. The module is pure compute and a leaf
within the package: no persistence, no repository, no OOS ledger, no
Walk-Forward folds, no PIT universe, no `PerformanceReport` dependency, and
no change to the Hard or Soft validation pipelines.

Three further contracts are frozen alongside the above:

- **`governed_components` is stored as a read-only mapping.** Because it is
  definition identity rather than diagnostics, neither mutation of the
  caller's original mapping nor mutation through the manifest attribute may
  change `manifest_hash` after construction. A private defensive copy alone
  is insufficient — the stored mapping itself must reject mutation.
  `manifest_hash` remains a derived read-only property, so it can be neither
  injected at construction nor assigned afterwards.
- **A conflicting duplicate `experiment_id` is an ambiguous, unresolvable
  lineage node.** It must not be arbitrarily selected for parent/root
  comparison, ancestor traversal, or cycle detection, since choosing one of
  its definitions would make those conclusions depend on the order the
  history happened to arrive in. The duplicate identity itself is reported
  as a `VIOLATION`; any lineage claim blocked by that ambiguity is reported
  separately at `INDETERMINATE` severity, so the audit declines to conclude
  rather than guessing. The duplicate-identity evidence carries canonical
  definition descriptors — manifest hash, parent identity, and root identity
  — so a conflict whose definitions share a hash is still distinguishable.
- **`unverifiable_claims` is a deterministic derived view.**
  `ExperimentLineageAudit.unverifiable_claims` exposes exactly the
  structured `INDETERMINATE` violations, derived from the canonically sorted
  `violations` rather than maintained as a second independently updated
  list, so calibrated abstention has one source of truth and inherits the
  report's order invariance.

## Explicit non-goals

V0.1 does not include broker connectivity, order placement, automatic exits,
portfolio rebalancing, autonomous signal confirmation, automatic production
weight changes, or automatic promotion from Strategy Lab to the Signal Engine.
It also does not add Supply Chain/CapEx Radar or other idea-stage modules.

## Change control

Changes to this frozen scope require a recorded proposal containing:

```text
requirement_id:
current_contract:
proposed_change:
failure_case_or_evidence:
adversarial_test_impact:
compatibility_impact:
candidate_spec_version:
approved_by:
changed_at:
```

Ordinary implementation details may evolve without changing the spec only when
all requirement IDs and acceptance conditions remain true.
