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
| Soft Gate pipeline | Planned |
| Parameter Stability Engine | Implemented — Foundation |
| Edge Concentration Engine | Implemented — Foundation |
| Permanent five-fixture adversarial suite | Implemented |
| Cost/execution stress, OOS/walk-forward, benchmark/alpha, and regime checks | Planned |
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
