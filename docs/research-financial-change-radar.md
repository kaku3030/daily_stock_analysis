# Research financial change radar

The US research scan keeps point-in-time financial snapshots for selected candidates and compares adjacent valid snapshots. The comparison is deterministic and is intended to change research priority, not to create trading instructions.

## Signals

- Earnings trend compares revenue growth, EPS growth, net-income growth, gross margin, operating margin, and free cash flow when both snapshots contain comparable numeric evidence.
- Valuation trend compares PE, forward PE, PEG, and price-to-sales when available.
- Guidance is only marked as changed or unchanged. Free-text guidance is not automatically classified as an upgrade or downgrade.
- Missing fields remain missing. A degraded scan does not invent values or erase the previous valid financial snapshot.

To reduce provider noise, a numeric field must change by at least 5% relative to its previous magnitude before it affects the headline trend. Raw values remain available in the financial snapshot history.

## Output

The daily US research scan emits:

- `reports/screening/us_research_earnings_valuation_radar.json`
- `reports/screening/us_research_earnings_valuation_radar.md`
- `reports/screening/us_research_financial_changes.json`
- `reports/screening/us_research_financial_changes.md`

The long-lived candidate-pool JSON also includes each symbol's latest `financial_change` sidecar when a persisted comparison exists.

## Interpretation

`attention=high` currently means deterministic earnings deterioration was detected. `medium` covers mixed earnings evidence, earnings improvement accompanied by valuation expansion, or a guidance text change. `low` covers improvement or valuation-only changes. `none` is used for stable observations or the first snapshot where no historical comparison exists.

These states are research alerts only. They do not generate entry prices, stops, targets, or position sizes.
