# Project Status

This file is the durable checkpoint for the personal research-platform work in this repository. Restore context in this order: this file, recent `main` commits, relevant Actions runs, then active implementation/tests/docs.

## Current phase

**News / catalyst change radar — implemented on `feat/news-catalyst-change-radar`, pending CI/review and merge.**

The implementation adds point-in-time event snapshots, deterministic normalization/fingerprints, conservative change detection, research-priority fusion, focused tests, documentation, and `us_research_news_change_radar.json/.md` outputs.

States: `baseline`, `new_catalyst`, `new_risk`, `unchanged`. Missing evidence is deliberately not treated as confirmed resolution.

## Completed research-platform capabilities

- Persistent US candidate pool with `active` / `watching` / `retired` lifecycle.
- Industry radar with market-backed heat when available.
- Earnings / valuation snapshots and point-in-time financial history.
- Financial change detection.
- Research-priority events: re-research urgency, never a trade signal.
- Priority transition gate / deduplication.
- Notification adapter through existing `NotificationService`.
- Stateful US workflow with SQLite cache persistence, `quick_check`, WAL checkpoint and cache roundtrip validation.
- Telegram connectivity manually verified.
- News / catalyst change radar implemented on the current feature branch; merge status must be verified before treating it as production.

## Research invariants

- The platform screens, tracks, explains, and reviews; trading decisions remain manual.
- No automated buy price, stop-loss, take-profit, or actual position-size instructions.
- Compatibility fields remain neutral: `operation_advice="观望"`, `decision_type="hold"`, `action="watch"`.
- Research priority means urgency to investigate, not directional conviction.
- Technical analysis remains 5% of the automated research score; tactical multi-timeframe analysis is separate.

Research score: quality/moat 20%, growth 20%, earnings/guidance 15%, industry cycle 15%, valuation 10%, relative strength 10%, technical structure 5%, news/catalysts 5%. Grades: A 80–100, B 65–79, C 50–64, D <50.

## Operational status

- Workflow: `.github/workflows/01-us-research-stateful.yml`
- `US_RESEARCH_STATEFUL_ENABLED = true`
- `US_RESEARCH_SCAN_ENABLED = false`
- Telegram test received successfully.
- First manual real stateful scan completed successfully with checkpoint, validation, cache save and report upload.
- `US_RESEARCH_ALERTS_ENABLED` remains disabled until several real stateful scans establish a useful history baseline.
- GitHub Actions cache is operational persistence, not a permanent backup.

## Active implementation details

News-change persistence table: `research_candidate_event_snapshots`, unique by `market + code + run_id`.

Evidence reuses candidate `catalysts` and `risks`; the design does not create a parallel news-fetching system. Deterministic fingerprints suppress exact repeated evidence and trivial formatting/case changes. First observations establish a baseline and do not alert. A new risk raises re-research urgency and becomes notification-ready; a new catalyst receives a smaller priority boost. The existing transition gate still controls downstream alert transitions.

Downstream path:

`news/catalyst change -> research priority -> transition gate -> NotificationService -> Telegram when enabled`

## Next

1. Let CI validate the feature branch and fix any integration failures.
2. Merge only after tests/review are green.
3. Run at least two real stateful scans so event comparisons have cross-run history.
4. Inspect generated news-change artifacts before enabling automated Telegram research alerts.
5. Then start the multi-timeframe technical-state layer: Daily MA/SuperTrend/MACD/RSI/Volume; 1H same; 15m VWAP/SuperTrend/MACD/RSI/ATR/Volume.

## Known risks / follow-ups

- Current first-version dedupe is deterministic, not full semantic paraphrase matching; semantic matching can be added later only if false-repeat evidence warrants it.
- Missing news/evidence must never be interpreted as risk resolution without explicit supporting evidence.
- Actions cache can be evicted after inactivity.
- Scheduled scan time still needs review against US market close and daylight-saving time.
- Work/chat history is not the completion source of truth; repository state, commits, tests and Actions are authoritative.
