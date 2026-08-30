# Stateful US research workflow

`US Research Stateful Scan` is the GitHub Actions entrypoint for long-lived US research state. It exists because GitHub-hosted runners are ephemeral: files written to `data/` disappear when a normal job ends unless they are explicitly persisted.

## What is persisted

The workflow persists the SQLite research database, its WAL sidecars, and the
last known complete US index universe:

- `data/stock_analysis.db`
- `data/stock_analysis.db-wal`
- `data/stock_analysis.db-shm`
- `data/us_universe.last_good.json`

It deliberately does **not** cache the entire `data/` directory, so unrelated
provider caches and temporary market-data files do not become part of the
long-lived research state. The universe cache is source-labelled and expires
after seven days by default.

The database contains the candidate pool and the research history needed by the US research pipeline, including candidate lifecycle state, financial snapshots, financial-change comparisons, and research-priority event history.

## Restore and save lifecycle

Each scheduled or manually dispatched stateful scan performs the following sequence:

1. Restore the newest cache with prefix `us-research-state-v1-<runner-os>-`.
2. Run `PRAGMA quick_check` on the restored SQLite database.
3. If the restored database is invalid, remove the database/WAL/SHM files and continue from a clean state rather than poisoning the current run.
4. Run `scripts/run_us_research_scan.py` against `./data/stock_analysis.db`.
5. Run `PRAGMA wal_checkpoint(TRUNCATE)` and a second `PRAGMA quick_check`.
6. Save a new cache using the current GitHub `run_id` as the immutable cache-key suffix.

Using a unique key per run avoids GitHub Actions cache's immutable-key behavior. The next run uses `restore-keys` to select the newest matching state.

## Verification

Changes to `.github/workflows/01-us-research-stateful.yml` trigger a cache roundtrip test that does **not** call market data or LLM APIs. One job creates a synthetic SQLite database and saves it to GitHub Cache; a second independent job restores the cache and verifies both `PRAGMA quick_check=ok` and the expected probe row.

The real `scan` job and Telegram test job are explicitly skipped on `push` events, so workflow validation cannot accidentally consume provider quotas or send messages.

## Telegram setup and manual test

Store these values as GitHub Actions Repository Secrets:

```text
TELEGRAM_BOT_TOKEN
TELEGRAM_CHAT_ID
```

Do not commit either value to the repository.

To test Telegram without running the stock scan:

1. Open GitHub → Actions → `US Research Stateful Scan`.
2. Click `Run workflow`.
3. Select `action = telegram-test`.
4. Run the workflow.

A successful test sends:

```text
✅ daily_stock_analysis Telegram 通知测试成功

研究提醒通道已经连接。
```

The test uses Telegram directly and does not call market-data or LLM providers.

## Manual research scan

For a manual production scan, choose:

```text
action = scan
```

`send_alerts=false` runs the scan, persists state, and only generates alert candidates.

`send_alerts=true` additionally allows material research transitions to pass through the existing `NotificationService` alert route. The scan still applies the transition gate, deduplication, cooldown, and the per-run alert cap before any message is sent.

## Enabling scheduled stateful scans

The scheduled job runs at 10:20 UTC, Monday through Friday. It is disabled by default.

To enable scheduled research scans, create this Repository Variable:

```text
US_RESEARCH_STATEFUL_ENABLED=true
```

Automatic real research alerts are controlled independently. To allow scheduled transition alerts, create:

```text
US_RESEARCH_ALERTS_ENABLED=true
```

If `US_RESEARCH_STATEFUL_ENABLED=true` but `US_RESEARCH_ALERTS_ENABLED` is absent or false, the workflow still scans and persists state but does not send real research alerts.

The workflow passes the configured Telegram secrets into the existing notification layer and defaults the alert route to `telegram` when no `NOTIFICATION_ALERT_CHANNELS` override is configured. Default research-alert noise controls are 24-hour deduplication and a 6-hour per-symbol/severity cooldown; repository notification variables can override them.

The workflow internally sets `US_RESEARCH_SCAN_ENABLED=true` only for the stateful scan process. Therefore, for cloud use, keep the legacy optional US research scan in `00-daily-analysis.yml` disabled (`US_RESEARCH_SCAN_ENABLED=false`) to avoid running the same research scan twice on separate ephemeral runners.

## Universe coverage guard

The research workflow targets the deduplicated `S&P 500 + Nasdaq 100`
universe. Live constituent pages are fetched with bounded retries and an
explicit user agent. A successful full-universe resolution is saved in the
state cache and can be reused during a temporary constituent-source outage.

Every report exposes the requested universe source, resolved source, planned
ticker count, successful snapshot count, and snapshot coverage ratio. The
default publication requirements are:

```text
US_RESEARCH_REQUIRED_UNIVERSE_SOURCE=sp500_nasdaq100
US_RESEARCH_MIN_UNIVERSE_SIZE=400
US_RESEARCH_MIN_UNIVERSE_COVERAGE=0.80
SCREENING_US_UNIVERSE_CACHE_MAX_AGE_HOURS=168
```

If the resolved source is a smaller fallback, the universe contains fewer
than 400 tickers, or fewer than 80% of planned tickers produce valid snapshots,
the run still uploads a diagnostic report but suppresses its candidate list.
It does not update candidate lifecycle/history and does not dispatch Telegram
research alerts. This prevents a partial universe from being presented as a
complete market ranking.

## Operational note

GitHub Actions cache is operational state, not a permanent backup system. Scheduled weekday runs continuously refresh the cache, including around normal weekends and market holidays. If Actions are disabled for a long period or GitHub evicts the cache, the workflow safely starts a fresh research history.

Research reports remain separate Actions artifacts; the SQLite database is not uploaded with public report artifacts.
