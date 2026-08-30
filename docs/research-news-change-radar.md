# US Research News / Catalyst Change Radar

## Purpose

The news / catalyst change radar turns per-run research evidence into a point-in-time history so the US research workflow can distinguish genuinely new signals from repeated wording.

It is a research-attention layer, not a trading system. It does not produce buy prices, stop losses, targets, or position sizes.

## Evidence sources

The radar reuses evidence already produced by the screening pipeline:

- `Pick.dsa_news`
- `Pick.llm_catalysts`
- `Pick.llm_risks`
- compatibility fallbacks `catalysts` / `risks` when present

No parallel news-fetching path is introduced.

## Persistence

Each selected candidate receives a point-in-time row in:

`research_candidate_event_snapshots`

The logical key is `market + code + run_id`. Each row stores:

- current catalysts, risks, and compact news evidence
- deterministic event fingerprints
- the previous run id used for comparison
- the resulting change state and attention level

The table is additive and is persisted together with the existing research SQLite database in the stateful GitHub Actions workflow.

## Change states

The first observation establishes a baseline and is reported as `unchanged`.

Subsequent adjacent snapshots can produce:

- `new_catalyst`: a catalyst is not equivalent to prior catalyst/news evidence
- `new_risk`: a risk is not equivalent to prior risk/news evidence
- `resolved_or_missing`: prior evidence is absent from the current snapshot
- `unchanged`: no material evidence transition is detected

`resolved_or_missing` is intentionally non-material. Missing evidence is **not** proof that a risk has been resolved, so `resolution_confirmed` remains false in this first version.

## Deterministic deduplication

The radar deliberately avoids asking an LLM whether two events are the same. It uses a deterministic, conservative comparison:

1. Unicode/case normalization and removal of common filler words.
2. Stable token fingerprints.
3. Token overlap / containment checks.
4. A high-threshold sequence-similarity fallback for wording drift.

This is intended to suppress common paraphrases such as repeated “demand remains strong” headlines without claiming full semantic understanding.

Deep paraphrases can still be missed and unrelated short phrases can occasionally collide. The radar therefore affects research attention only and remains behind the existing transition/dedup notification gate.

## Research-priority integration

For each candidate, the latest event change is attached as `news_change` before research-priority fusion.

- `new_risk` becomes a `news_risk` / `risk_review` event and is notification-ready.
- `new_catalyst` becomes a `new_catalyst` / `positive_watch` event.
- `resolved_or_missing` does not create a positive recovery notification by itself.
- repeated/unchanged evidence does not receive a new-event bonus.

Downstream flow:

`event snapshot -> news change radar -> research priority -> transition gate -> NotificationService`

Real notification sending still requires the existing explicit research-alert enablement.

## Outputs

Each US research scan writes:

- `reports/screening/us_research_news_change_radar.json`
- `reports/screening/us_research_news_change_radar.md`

The JSON output contains the current run's point-in-time event snapshots and change detail.

## Failure and rollback behavior

The layer is fail-open inside the existing candidate-pool synchronization guard. If the radar fails, the primary daily research candidate report remains available.

Removing the integration does not require destructive database migration. The additive `research_candidate_event_snapshots` table can remain unused or be removed separately after normal backup/retention review.
