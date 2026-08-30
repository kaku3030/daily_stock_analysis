# Stateful US research workflow

`US Research Stateful Scan` is the GitHub Actions entrypoint for long-lived US research state. It exists because GitHub-hosted runners are ephemeral: files written to `data/` disappear when a normal job ends unless they are explicitly persisted.

## What is persisted

The workflow persists only the SQLite research database and its WAL sidecars:

- `data/stock_analysis.db`
- `data/stock_analysis.db-wal`
- `data/stock_analysis.db-shm`

It deliberately does **not** cache the entire `data/` directory, so provider caches and temporary market-data files do not become part of the long-lived research state.

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

The real `scan` job is explicitly skipped on `push` events, so workflow validation cannot accidentally consume provider quotas.

## Enabling scheduled stateful scans

The scheduled job runs at 10:20 UTC, Monday through Friday. It is disabled by default.

To enable it, create this Repository Variable in GitHub Actions settings:

```text
US_RESEARCH_STATEFUL_ENABLED=true
```

`workflow_dispatch` always allows a manual run regardless of that variable, which is useful for the first production-state test.

The workflow internally sets `US_RESEARCH_SCAN_ENABLED=true` only for the stateful scan process. Therefore, for cloud use, keep the legacy optional US research scan in `00-daily-analysis.yml` disabled (`US_RESEARCH_SCAN_ENABLED=false`) to avoid running the same research scan twice on separate ephemeral runners.

## Operational note

GitHub Actions cache is operational state, not a permanent backup system. Scheduled weekday runs continuously refresh the cache, including around normal weekends and market holidays. If Actions are disabled for a long period or GitHub evicts the cache, the workflow safely starts a fresh research history.

Research reports remain separate Actions artifacts; the SQLite database is not uploaded with public report artifacts.
