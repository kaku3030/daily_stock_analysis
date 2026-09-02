# Project Status

This file is the durable checkpoint for the personal research-platform work in this repository.
When chat or Work context is unavailable, restore project context in this order:

1. `docs/PROJECT_STATUS.md`
2. recent commits on `main`
3. relevant GitHub Actions runs
4. implementation/tests/docs for the active module

Keep this file concise and factual. Update it at the end of each meaningful research-platform phase.

## Current phase

**Stock Radar V2 multi-timeframe state — runtime bridge, point-in-time history,
deterministic adjacent-run comparison, and research-only radar publication are
complete. Real provider scheduling is the next phase.**

The radar stores point-in-time event evidence, deterministically suppresses repeated/paraphrased old events, identifies new catalysts and new risks, and feeds material changes into the existing research-priority / transition-gate path.

Important invariant: missing evidence is not treated as confirmed risk resolution.

The multi-timeframe bridge is research-only. It preserves Data Health signal
permission and cannot create a Confirmed signal or trading instruction.

Technical-state history ignores small numeric indicator drift in its change
fingerprint. It records categorical transitions for later validation but does
not notify, alter weights, or promote a state into a signal.

The technical-state radar writes current-run JSON and Markdown from explicitly
supplied states. It does not fetch market data or run on a schedule yet.

## Completed research-platform capabilities

- Persistent US research candidate pool with `active` / `watching` / `retired` lifecycle tracking.
- Industry radar combining candidate research strength with market-backed industry heat when available.
- Earnings / valuation snapshots and point-in-time financial history.
- Financial change detection across adjacent valid snapshots.
- Point-in-time news / catalyst / risk event snapshots with deterministic change detection.
- News change radar states: `new_catalyst`, `new_risk`, `resolved_or_missing`, `unchanged`.
- Research-priority events where priority means re-research urgency, not bullishness or a trade signal.
- Priority transition gate / deduplication for material upgrades, tone flips, guidance changes, event changes, and recoveries.
- Notification adapter reusing the existing `NotificationService`; no automated buy/sell instructions.
- Dedicated stateful US research workflow with SQLite persistence through GitHub Actions cache.
- SQLite `quick_check`, WAL checkpointing, cache save/restore, and cross-run state validation.
- Telegram connectivity wired into the stateful workflow and manually verified.
- Idempotent multi-timeframe technical-state radar JSON/Markdown publisher.

## Research philosophy and invariants

- The platform screens, tracks, explains, and reviews; the user makes trading decisions manually.
- Automated research must not emit explicit buy prices, stop-loss levels, take-profit levels, or actual position sizes.
- Compatibility fields remain neutral (`operation_advice="观望"`, `decision_type="hold"`, `action="watch"`).
- Research priority is urgency to investigate, not directional conviction.
- Technical analysis remains 5% of the automated research score; tactical multi-timeframe analysis is a separate manual layer.
- Repeated or paraphrased old news must not repeatedly raise research priority or trigger alerts.
- Absence of fresh evidence must not be interpreted as a confirmed risk resolution.

Current research score framework:

1. Company quality / moat — 20%
2. Revenue / profit growth — 20%
3. Latest earnings / guidance — 15%
4. Industry cycle — 15%
5. Valuation — 10%
6. Relative strength — 10%
7. Technical structure — 5%
8. News / catalysts — 5%

Grades: A = 80–100, B = 65–79, C = 50–64, D < 50.

## Operational status

- Stateful workflow: `.github/workflows/01-us-research-stateful.yml`
- `US_RESEARCH_STATEFUL_ENABLED = true`
- `US_RESEARCH_SCAN_ENABLED = false`
- Telegram test message was received successfully.
- The first manual real stateful scan completed successfully with checkpoint, SQLite validation, cache save, and report upload.
- `US_RESEARCH_ALERTS_ENABLED = true`; transition, deduplication, cooldown, and universe-coverage gates still suppress ineligible alerts.
- US research candidates are published only when the resolved universe is the configured `S&P 500 + Nasdaq 100` source (or its fresh matching cache), contains at least 400 tickers, and produces at least 80% valid snapshots.
- The legacy optional US research path should remain disabled while the stateful workflow is active to avoid duplicate independent scans.
- GitHub Actions cache is operational persistence, not a permanent backup.

## Current implementation checkpoint

Base commit before the news / catalyst change implementation:

- `501efec0f055ab374b01ea52fff414ba56cd3205` — `Add project status checkpoint`

This status file is updated in the same implementation commit as the news / catalyst change radar, so the authoritative current commit is the `main` head containing this file.

## News / catalyst change radar

Evidence is reused from:

- `Pick.dsa_news`
- `Pick.llm_catalysts`
- `Pick.llm_risks`
- compatibility catalyst/risk fields already present in candidate data

Durable table:

- `research_candidate_event_snapshots`

Outputs:

- `us_research_news_change_radar.json`
- `us_research_news_change_radar.md`

Downstream path:

`news/catalyst evidence -> event snapshot -> change detection -> research priority -> transition gate -> notification adapter`

Deterministic normalization/fingerprinting is preferred over LLM judgement for deduplication. The comparison is deliberately conservative and is not a semantic truth engine.

## Validation next

- Wire a real QMT or Alpaca runtime caller to provide computed technical states
  and explicit run IDs; do not infer missing bars or silently substitute data.
- Accumulate several real runs before considering any technical-state alert
  policy. The current publisher intentionally emits no Telegram notification.
- Let multiple real stateful scans accumulate so adjacent event comparisons can be observed on real candidates.
- Inspect `new_catalyst` / `new_risk` frequency and false-positive rate before enabling automatic Telegram research alerts.
- Confirm SQLite state/cache remains healthy after the new event table starts accumulating rows.
- Tune deterministic similarity thresholds only from observed false positives/false negatives, not from isolated examples.

## Later roadmap

After news/catalyst validation:

- Multi-timeframe technical state:
  - Daily: MA + SuperTrend + MACD + RSI + Volume
  - 1H: MA + SuperTrend + MACD + RSI + Volume
  - 15m: VWAP + SuperTrend + MACD + RSI + ATR + Volume
- Manual market-structure layer: SMC, support/resistance, VWAP structure, volume, holding-cost context.
- Immutable full research-score snapshots for unbiased factor review / backtesting.
- Factor validation / post-selection performance review with strict look-ahead and survivorship controls.

## Known risks / follow-ups

- Deterministic text similarity can miss deep semantic paraphrases and can occasionally over-match short generic phrases.
- `resolved_or_missing` is intentionally not a confirmed recovery signal.
- GitHub Actions cache may be evicted after inactivity; it is not a permanent research-history backup.
- The scheduled stateful scan time should be reviewed against US market close / daylight-saving time before relying on it as an after-close daily research run.
- Cross-day financial/event change detection becomes materially useful only after enough successful real stateful scans have accumulated.
- Work/chat history is not treated as the source of truth for completion; repository state, commits, tests, and Actions are authoritative.
