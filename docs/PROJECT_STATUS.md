# Project Status

This file is the durable checkpoint for the personal research-platform work in this repository.
When chat or Work context is unavailable, restore project context in this order:

1. `docs/PROJECT_STATUS.md`
2. recent commits on `main`
3. relevant GitHub Actions runs
4. implementation/tests/docs for the active module

Keep this file concise and factual. Update it at the end of each meaningful research-platform phase.

## Current phase

**News / catalyst change radar — design approved, implementation not yet committed.**

Goal: turn existing per-run news/catalyst/risk evidence into point-in-time history and deterministic change detection, then feed only material transitions into the existing research-priority / notification path.

Planned first-version event states:

- `new_catalyst`
- `new_risk`
- `resolved_or_missing`
- `unchanged`

Key constraint: repeated or paraphrased old news must not repeatedly raise research priority or trigger alerts.

## Completed research-platform capabilities

- Persistent US research candidate pool with lifecycle tracking (`active` / `watching` / `retired`).
- Industry radar combining candidate research strength with market-backed industry heat when available.
- Earnings / valuation snapshot extraction and point-in-time financial history.
- Financial change detection across adjacent valid snapshots.
- Research-priority events where priority means **re-research urgency**, not bullishness or a trade signal.
- Priority transition gate / deduplication for material upgrades, tone flips, guidance changes, and recoveries.
- Notification adapter reusing the existing `NotificationService`; no automated buy/sell instructions.
- Dedicated stateful US research workflow with SQLite persistence through GitHub Actions cache.
- SQLite `quick_check`, WAL checkpointing, cache save/restore, and cross-run state validation.
- Telegram connectivity wired into the stateful workflow and manually verified.

## Research philosophy and invariants

- The platform screens, tracks, explains, and reviews; the user makes trading decisions manually.
- Automated research must not emit explicit buy prices, stop-loss levels, take-profit levels, or actual position sizes.
- Compatibility fields remain neutral (`operation_advice="观望"`, `decision_type="hold"`, `action="watch"`).
- Research priority is urgency to investigate, not directional conviction.
- Technical analysis remains a small part of the research score; tactical multi-timeframe analysis is a separate manual layer.

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

Repository workflow state:

- Stateful workflow: `.github/workflows/01-us-research-stateful.yml`
- Legacy optional US research path should remain disabled when using the stateful workflow to avoid duplicate scans on independent ephemeral runners.
- Stateful workflow persists only the research SQLite DB files (`stock_analysis.db`, WAL, SHM), not the whole `data/` directory.
- GitHub Actions cache is operational persistence, not a permanent backup.

User-verified configuration / runtime state as of 2026-08-30:

- `US_RESEARCH_STATEFUL_ENABLED = true`
- `US_RESEARCH_SCAN_ENABLED = false`
- Telegram test message received successfully.
- First manual real stateful `scan` completed successfully with checkpoint, validation, cache save, and report upload.
- `US_RESEARCH_ALERTS_ENABLED` intentionally remains disabled until several real stateful scans establish a useful history baseline.

## Last verified repository checkpoint

Latest known `main` commit before this status document:

- `d27c185f656603d721f6b44cfcabd1db8714169f` — `Document Telegram alert controls`

Related immediately preceding commit:

- `338b50ac2073bd9ba0c34c7b9e97c6f4d6155c7b` — `Wire Telegram research alerts`

## Next implementation

### News / catalyst change radar

Reuse existing evidence instead of creating a parallel news system:

- `Pick.dsa_news`
- `Pick.llm_catalysts`
- `Pick.llm_risks`
- current candidate-pool `catalysts_json` / `risks_json`

Planned durable history should store point-in-time event evidence per `market + code + run_id`, including normalized fingerprints suitable for deterministic dedupe.

Expected outputs:

- `us_research_news_change_radar.json`
- `us_research_news_change_radar.md`

Expected downstream path:

`news/catalyst change -> research priority -> transition gate -> notification adapter -> Telegram (when alerts are enabled)`

Implementation rules:

- Prefer deterministic normalization/fingerprinting before using LLM judgement for change detection.
- Do not infer bullish/bearish trading instructions from event wording.
- Fail open when upstream news evidence is missing; lack of fresh evidence must not be treated as a confirmed resolved risk without sufficient history/evidence.
- Add focused non-network tests and update relevant docs / `docs/CHANGELOG.md` when the feature becomes user-visible.

## Later roadmap

After the news / catalyst change layer is stable:

- Multi-timeframe technical state:
  - Daily: MA + SuperTrend + MACD + RSI + Volume
  - 1H: MA + SuperTrend + MACD + RSI + Volume
  - 15m: VWAP + SuperTrend + MACD + RSI + ATR + Volume
- Manual market-structure layer: SMC, support/resistance, VWAP structure, volume, holding-cost context.
- Immutable full research-score snapshots for unbiased factor review / backtesting.
- Factor validation / post-selection performance review with strict look-ahead and survivorship controls.

## Known risks / follow-ups

- GitHub Actions cache may be evicted after inactivity; it is not a permanent research-history backup.
- The current scheduled stateful scan time should be reviewed against US market close / daylight-saving time before relying on it as an after-close daily research run.
- Cross-day financial/event change detection becomes materially useful only after enough successful real stateful scans have accumulated.
- Work/chat history is not treated as the source of truth for completion; repository state, commits, tests, and Actions are authoritative.
