# Stock Razor migration audit

## Decision

Use one repository with explicit product boundaries. This first change adds `shared/`, `radar/`, `realtime_monitor/`, `strategy_lab/`, and `infra/` while leaving existing Radar, Strategy Lab, API, Web, desktop, deployment, and test paths intact. Moving established packages in the same change would create broad import, workflow, packaging, and user-data migration risk without improving behavior.

The public product name becomes **Stock Razor**. Internal identifiers such as Python imports, `DSA_*` environment variables, the desktop `appId`, old installer discovery, and database paths stay compatible. The repository slug should become `stock-razor` after the PR is reviewable; GitHub redirects the previous URL, but local remotes, badges, external deployments, package metadata, and integrations still need an audit.

## Inventory and ownership

| Boundary | Current implementation | Decision |
| --- | --- | --- |
| Radar | `src/services/screening/`, `src/services/stock_radar_v2/` | Keep paths; expose the intended boundary in `radar/README.md`. |
| Realtime Monitor | Local `moomoo_mcp/server.py` candidate, validated at SHA-256 `A6569FCD92F5A4B7FCF1AB98A29BC0EFDE6E54361A60911DDD45B1D768105379` before sanitization | Import into `realtime_monitor/`; remove the account identifier and machine-specific launcher paths. |
| Shared | Data providers, data health, repositories, schemas, logging are currently distributed across established packages | Do not duplicate or extract yet. Extract only when both products have contract tests. |
| Strategy Lab | `src/services/strategy_lab/` | Keep path to preserve imports and tests. |
| Infra | `.github/workflows/`, `docker/`, `scripts/` | Keep paths to preserve CI and deployment contracts. |

The imported monitor remains a monolith because its E1–E4 pipeline was validated as one candidate. This is technical debt, but splitting it while migrating would invalidate the strongest available regression evidence.

## Boundary audit

- Radar owns discovery and ranking. It must not treat candidates as positions.
- Realtime Monitor owns observation of existing positions, portfolio-derived evidence, state-change triggers, alert policy, cooldown/deduplication, and journaling.
- Shared will own only stable, product-neutral contracts. It must not own portfolio decisions or candidate ranking.
- Strategy Lab evaluates strategies and parameters; it does not publish live decisions.
- Infra schedules and observes services without redefining strategy semantics.

Runtime state, journals, credentials, account identifiers, generated reports, and validation fixtures are excluded from the migration. The imported source reads its account identifier from `STOCK_RAZOR_PRIMARY_US_ACCOUNT_ID`; host and port are configurable without committing machine-specific values.

## Build vs borrow

| Capability | Choice | Reason |
| --- | --- | --- |
| Portfolio State and holding re-underwrite | Build/retain | Portfolio truth, position scope, and decision authority are product semantics. |
| Trigger, cooldown, and deduplication semantics | Build/retain | These define when a state change becomes actionable. |
| Market/Risk State, RS, price structure, VWAP/AVWAP/SuperTrend | Retain, then consolidate | Existing deterministic logic and data-health gates have regression value. |
| Evidence → Gate → Narrative and Decision Journal | Build/retain | Auditability, authority, redaction, and fail-closed behavior are core contracts. |
| Ownership/Exposure/Add Right and Edge/Risk Budget | Build next | These planned concepts are not yet complete formal contracts in the imported candidate; they should not be represented as finished. |
| Broker and market transport | Borrow | Continue using the Futu/Moomoo SDK behind a thin adapter. Do not rebuild transport. |
| LLM clients | Borrow | Continue using official Anthropic/OpenAI clients; keep schemas, routing gates, and fallback policy in-house. |
| Workflow orchestration and observability | Evaluate later | Prefect and Prometheus/Grafana may help after process and deployment boundaries stabilize. Adding them now would expand the migration without closing a current blocker. |
| Research/backtesting | Borrow selectively | vectorbt/Qlib can accelerate experiments, but do not give them portfolio or risk authority. |

## Preserved core logic

The imported candidate preserves Portfolio State, Market/Risk State, deterministic relative strength, multi-timeframe structure, trigger comparison and suppression, AI invocation gates, decision-envelope redaction, notification intent and rendering, delivery outcomes, and append-only Decision Journal semantics.

The current candidate uses `ADD_CANDIDATE` and `REDUCE_CANDIDATE` as non-trading decision states. They are not a complete implementation of Add Right or Exposure Right. Leadership is currently represented mainly by relative-strength evidence and does not yet include the planned multi-session leadership persistence contract.

## Risks and follow-up

1. The monitor is a large single module. Split it only behind characterization tests for Portfolio, rights, state, trigger, notification, and journal contracts.
2. The live transport, AI providers, notification delivery, production runtime path, and real Decision Journal path are not exercised by repository CI. Keep external side effects disabled in tests.
3. The journal lock is process-local. Production deployment must enforce a single writer or add an inter-process/storage transaction boundary.
4. Renaming the desktop product changes new artifact names. The stable `appId` and legacy install discovery remain to preserve upgrades and existing user data.
5. Add formal Ownership Right, Exposure Right, Add Right, Leadership persistence, and Edge/Risk Budget schemas with fail-closed data-health gates.
6. After both Radar and Monitor consume shared normalized facts, extract those contracts into `shared/` and delete the old implementation in the same reviewed change.

## Rollback

Revert this change. Existing application paths and internal identifiers remain intact, so the pre-migration Radar application can resume without a data conversion.
