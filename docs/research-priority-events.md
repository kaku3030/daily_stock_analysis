# Research priority events

The US research scan fuses candidate quality, industry context, financial changes, and persisted catalyst/risk lines into a deterministic research-priority event stream.

The priority level answers **how quickly a candidate deserves another research pass**. It does not represent a buy/sell recommendation or directional conviction.

## Inputs

- Candidate grade and research score.
- Candidate lifecycle state (`active` / `watching`).
- Industry radar strength. Real market heat data receives materially more weight than candidate-only industry aggregation to avoid double counting the stock score.
- Financial-change attention, earnings trend, valuation trend, and guidance-change state.
- Persisted catalyst and risk lines from the screening research context.

## Event semantics

- `financial_risk`: earnings deterioration; research tone is `risk_review`.
- `guidance_change`: management-guidance text changed; direction is intentionally not guessed.
- `positive_convergence`: A/B candidate with improving earnings and strong market-backed industry support.
- `catalyst_focus`: A/B candidate with active catalyst lines.
- `industry_focus`: strong market-backed industry context.
- `valuation_watch`: valuation expansion without a stronger event above it.
- `priority_refresh`: routine ranking refresh when no material event dominates.

Priority levels are `urgent`, `high`, `normal`, and `low`. `notification_ready` only becomes true for high-attention financial deterioration or for high/urgent candidates supported by at least two material signals. This keeps ordinary high scores from generating noisy alerts.

## Persistence and outputs

Each run persists one event snapshot per candidate in `research_priority_events`, keyed by market, symbol, and run ID. Re-running the same run is idempotent.

The daily US research scan emits:

- `reports/screening/us_research_priority_events.json`
- `reports/screening/us_research_priority_events.md`

The long-lived candidate-pool JSON also includes the current run's `research_priority` sidecar.

This layer only ranks research attention. It does not create entry prices, stops, targets, position sizes, or execution instructions.
