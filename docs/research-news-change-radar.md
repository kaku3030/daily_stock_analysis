# Research News / Catalyst Change Radar

The US research scan now keeps point-in-time catalyst and risk evidence for each candidate and compares each run with the previous stored observation.

## Purpose

This layer detects **research changes**, not trade signals. It is designed to answer whether a candidate has a genuinely new catalyst or risk that deserves renewed research attention while suppressing repeated evidence.

## Persistence

`research_candidate_event_snapshots` stores one row per `market + code + run_id`. Each row contains the raw candidate catalyst/risk evidence for that run plus the deterministic comparison result.

The stateful US research workflow already persists the SQLite database, so these snapshots survive GitHub-hosted runner replacement as long as the research-state cache is available.

## States

- `baseline`: first observation; establishes history and does not alert by itself.
- `new_catalyst`: at least one new catalyst fingerprint appears.
- `new_risk`: at least one new risk fingerprint appears; this takes precedence when both types are new.
- `unchanged`: no new deterministic event fingerprint was found.

Missing current evidence is deliberately **not** treated as a confirmed resolved risk. `resolved_or_missing` remains empty until a future implementation has enough explicit evidence to distinguish true resolution from data-source absence.

## Deduplication

Event text is normalized and hashed before comparison. Exact repeated evidence and trivial formatting/case differences therefore reuse the same fingerprint. The first version intentionally avoids an LLM-based semantic classifier in the dedup path so that alert behavior remains deterministic and testable.

## Priority integration

A new risk increases re-research urgency and is notification-ready; it does not mean the stock is bearish or should be sold. A new catalyst adds a smaller research-priority boost. Baseline and unchanged observations do not receive a news-change boost.

The downstream path remains:

`news/catalyst change -> research priority -> transition gate -> NotificationService`

Actual notification sending still requires the existing explicit research-alert enablement.

## Outputs

Each successful US research scan writes:

- `reports/screening/us_research_news_change_radar.json`
- `reports/screening/us_research_news_change_radar.md`

These reports are research artifacts only and contain no buy price, stop-loss, take-profit, or position-size instruction.
