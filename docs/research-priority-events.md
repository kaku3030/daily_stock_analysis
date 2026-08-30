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

## Transition gate

The persisted event history is also used as a notification gate. The gate suppresses repeated observations and emits a reminder candidate only when the research state changes materially:

- Same priority and same event type: suppressed.
- Priority upgrade such as `normal -> high` or `high -> urgent`: emitted when the current event is notification-ready.
- `positive_watch <-> risk_review`: emitted as a critical tone flip.
- New `guidance_change`: emitted even if the numeric priority did not increase.
- Previous `risk_review` clearing: emitted as an informational recovery event.
- First observation: only a material event is emitted; ordinary candidates merely establish a baseline.

This gate deliberately does not notify on routine priority downgrades or unchanged high-priority states.

## Notification dispatch

The scan can pass material transition alerts to the existing `NotificationService` instead of maintaining a second channel implementation. This reuses the configured alert route, channel routing, Markdown handling, noise control, and per-channel delivery diagnostics already supported by the application.

Real delivery is **explicit opt-in**. The normal scheduled command only writes alert candidates and does not send them. To allow real delivery for a manual or scheduled run, execute:

```bash
python scripts/run_us_research_scan.py --send-research-alerts
```

The dispatch adapter:

- uses `route_type=alert` and preserves `critical` / `warning` / `info` severity;
- passes the stock code to stock-aware email routing when available;
- provides a stable per-run dedup key and a per-symbol/severity cooldown key to the existing notification noise layer;
- sends at most five research alerts in one scan, ordered by severity and priority score;
- contains notification failures so a broken channel never fails the research scan;
- never adds entry prices, stops, targets, position sizes, or execution instructions to the message.

A repeated execution of the same persisted `run_id` does not dispatch again because no new priority-event rows are inserted on the second pass.

## Persistence and outputs

Each run persists one event snapshot per candidate in `research_priority_events`, keyed by market, symbol, and run ID. Re-running the same run is idempotent. Before persisting the current run, the scan reads the latest prior event for each symbol and evaluates the transition.

The daily US research scan emits:

- `reports/screening/us_research_priority_events.json`
- `reports/screening/us_research_priority_events.md`
- `reports/screening/us_research_priority_alerts.json`
- `reports/screening/us_research_priority_alerts.md`
- `reports/screening/us_research_priority_notifications.json`

The notification diagnostics file records whether real dispatch was enabled, how many alerts were eligible, how many attempts were made, and per-channel success/failure diagnostics returned by the existing notification layer.

The long-lived candidate-pool JSON includes the current `research_priority` sidecar and, when a material transition exists, a `research_alert` sidecar.

This layer only ranks research attention and reports research-state transitions. It does not create entry prices, stops, targets, position sizes, or execution instructions.
