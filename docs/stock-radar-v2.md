# Stock Radar V2 MVP

Stock Radar V2 adds reliability, risk gating, and validation around the
read-only MarketDataAdapter V1 facts. It remains a research system: it does not
place orders or turn QA observations into trading instructions.

## Provider stability and Critical health

The primary provider enters fallback after three consecutive failures. It can
return only after a 300-second cooldown and three successful health probes,
spaced at least 60 seconds apart. This prevents rapid provider oscillation.

Critical health is deterministic:

- five consecutive request timeouts longer than five seconds;
- three consecutive empty or unparseable responses;
- an explicit connection, authentication, or subscription error;
- two consecutive closed-bar missing, timestamp mismatch, or session mismatch observations.

Fallback and Critical transitions use the unified notification boundary. A
stream subscription error stays visible and is never disguised as fallback
polling.

## Independent confidence boundaries

`signal_confidence` describes one signal's evidence. `portfolio_confidence`
describes portfolio-level conditions and is scored from 0 to 100:

| Score | Level | Risk gate |
| ---: | --- | --- |
| 80-100 | L0 | `ALLOW_RESEARCH_FLOW` |
| 60-79.99 | L1 | `WATCH_PORTFOLIO_RISK` |
| 40-59.99 | L2 | `RESTRICT_NEW_POSITION` |
| Below 40 | L3 | `BLOCK_NEW_POSITION` |

Portfolio assessment returns a separate immutable result. It never changes an
individual signal state or its confidence.

## Notification and validation flow

All Stock Radar events pass through `notify(event_type, payload)`. The MVP
supports `data_health_alert`, `provider_fallback_alert`, `signal_qa_alert`,
`portfolio_risk_alert`, and `confirmed_signal_alert`.

Only Confirmed signals enter the SQLite Validation Queue. Daily QA summarizes
outcomes. Weekly Calibration raises `signal_qa_alert` and creates a review when
at least seven of the latest ten same-type Confirmed signals fail. QA never
changes production weights. Candidate-weight discussion requires at least 30
resolved samples, a candidate version, separate validation, and manual
promotion.

The stateful US research workflow runs Daily QA against the same
`data/stock_analysis.db` database and runs Weekly Calibration on Mondays. It
writes `stock_radar_daily_qa.{json,md}` and
`stock_radar_weekly_calibration.{json,md}` into the research report artifact.
External alerts remain opt-in and use the existing NotificationService route,
deduplication, cooldown, and Telegram configuration.

The research candidate pipeline does not automatically enqueue Confirmed
signals. The Validation Queue stays empty until an explicit signal engine
provides a genuine `confirmed` state; research-priority changes are not treated
as trading signals.

## Multi-timeframe technical state bridge

The runtime bridge reuses the existing neutral technical analyzer instead of
duplicating indicator formulas. It converts normalized 15-minute and one-hour
bars from `MarketDataSnapshot` and combines them with explicitly supplied daily
bars. Forming, incomplete, or flagged bars remain partial and cap timeframe
confidence. Missing daily data stays `unknown` rather than being inferred from
intraday data.

The bridge preserves the Data Health `signal_permission` exactly and exposes
`research_only=true` and `can_confirm_signal=false`. Its output is technical
evidence for later review; it cannot create a Confirmed signal or a trading
instruction.

## Point-in-time technical state history

Categorical Daily / 1H / 15m state can be stored in
`stock_radar_technical_state_snapshots` under a caller-supplied `run_id`.
Writes are idempotent per market, symbol, and run. Each row keeps the full
point-in-time evidence, a stable categorical fingerprint, the previous run ID,
and deterministic change detail.

The fingerprint deliberately excludes timestamps and small numeric indicator
drift. Recorded changes include provider-permission downgrade or recovery,
daily trend or availability changes, multi-timeframe alignment, lower-timeframe
state, structure, and data quality. Only permission downgrade and a genuine
known-to-known daily trend change are marked material. These are research
review facts: they do not notify, change research weights, or confirm a signal.

## Configuration change control

Critical defaults live in `src/services/stock_radar_v2/stock_radar_v2.yaml`.
Each locked value records its reason, evidence, introduction version, and last
change date. Future changes require a real incident case or backtest evidence.

Use this changelog template when changing a locked value:

```text
parameter:
old_value:
new_value:
reason:
evidence_case_or_backtest:
candidate_version:
validation_result:
approved_by:
changed_at:
```

## Deferred structure work

Chan theory may be evaluated later as an optional Structure Engine enhancement.
It is not part of this MVP and must not reorder the current Data Layer followed
by SMC/Structure delivery sequence.
