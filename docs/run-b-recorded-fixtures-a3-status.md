# Run B Recorded Market Fixtures A3 — Status

Authoritative implementation branch: `harvest/run-b-recorded-fixtures-a3`.

This slice is DATA/TEST/SHADOW-DESIGN infrastructure only. It preserves point-in-time provider/source authority with each recorded fixture so historical replay does not silently consult only the current provider registry.

Current head lineage starts from accepted A2 replay substrate `ae044adf4acb5bbb1174c810bc7c51f0d37697a4`.

## Frozen boundaries
- Embedded capture-time authority snapshot + canonical digest.
- Distinct timezone-aware `available_at` and `observed_at`.
- Immutable source commit/blob and license provenance for the included public fixture.
- Current authority is diagnostic-only; drift cannot rewrite historical truth.
- Missing/tampered/unresolvable authority evidence fails closed.
- Materialized recorded events retain authority digest/reference lineage.
- Replay remains side-effect free and does not promote example pattern thresholds.

## Non-scope
No Currentness, Continuity, routing/fallback, SHADOW_ACTIVE, CORE, LIVE, notifications, strategy execution, AI-trader, broker or BUY/SELL authority.

Any exact-head CI/review evidence must bind the current A3 head; older-head results are Historical Record only.
