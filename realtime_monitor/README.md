# Realtime Monitor

The Realtime Monitor watches existing positions and emits state-change evidence. It is isolated from Radar candidate discovery and contains no trade execution workflow.

The initial import preserves the validated single-file MCP service in `server.py`. It includes portfolio snapshots, data health, market regime, relative strength, price structure, VWAP/AVWAP/SuperTrend, trigger and cooldown semantics, AI review, Evidence → Gate → Narrative notification handling, and the append-only Decision Journal.

## Run

Install the monitor-specific packages, configure the account in the environment, start Moomoo OpenD on the configured endpoint, then run the launcher:

```powershell
python -m pip install -r realtime_monitor/requirements.txt
$env:STOCK_RAZOR_PRIMARY_US_ACCOUNT_ID = "your-account-id"
python realtime_monitor/start.py
```

Optional settings are `STOCK_RAZOR_MOOMOO_HOST` (default `127.0.0.1`) and `STOCK_RAZOR_MOOMOO_PORT` (default `11111`). AI keys and notification settings retain their existing environment-variable contracts.

Runtime state and the Decision Journal are written below `realtime_monitor/runtime/`, which is ignored by Git. The v0.1 journal assumes a single process writer; its in-process lock does not coordinate multiple service processes.

## Migration boundary

This import does not claim that every planned domain is already implemented. Portfolio State, Risk/Market State, trigger semantics, RS, and Evidence → Gate → Narrative are present. Formal Ownership Right, Exposure Right, Add Right, Leadership persistence, and Edge/Risk Budget contracts remain follow-up work and are recorded in the migration audit.
