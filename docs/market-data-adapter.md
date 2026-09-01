# MarketDataAdapter V1

`MarketDataAdapter V1` is the provider-neutral, read-only market-data boundary
for the research radar. It does not calculate indicators, create trade
instructions, or place orders.

## Implemented scope

| Component | V1 capability | Explicit limitation |
| --- | --- | --- |
| Existing manager bridge | Realtime snapshots and daily bars | Does not emulate intraday streaming |
| PyTDX adapter | Mainland China raw 1m bars and snapshots | Request/response only; snapshots lack a provider timestamp |
| QMT/xtquant adapter | Mainland China raw 1m history, snapshots, and `subscribe_quote` callbacks | Requires an installed and connected QMT/xtquant runtime |
| Alpaca adapter | US raw 1m history, latest bar/quote, `bars` and `updatedBars` callbacks | Requires market-data credentials and an injected stream client |
| Provider router | QMT primary with explicit PyTDX fallback for snapshots and bars | Streaming failure remains visible; it never becomes polling |
| Bar Builder | Session-aware 1m to 15m/1h aggregation | Uses configured sessions; no exchange calendar is embedded |
| Data Health Gate | Deterministic score, grade, quality flags, and signal permission | Cross-provider checks are not yet implemented |
| Realtime Market Data Service | Bounded 1m cache, correction replacement, 15m/1h snapshots, freshness diagnostics | Does not calculate indicators or emit signals |

Higher timeframes are built from normalized 1m facts so providers cannot
silently apply different 15m/1h boundaries. The A-share builder does not span
the midday break.

## Health permissions

| Score / condition | Permission |
| --- | --- |
| 80-100 and no degrading flag | `normal` |
| 70-79, stale, forming, or missing bar | `watch_only` |
| 50-69 | `record_only` |
| Below 50 or severe integrity flag | `blocked` |

Severe integrity flags include invalid OHLC, non-positive price, negative
volume, and timestamp mismatch. Missing provider timestamps, stale values,
forming bars, and missing bars cannot produce normal confirmed signals.

## QMT runtime boundary

The xtquant adapter follows the official `xtdata` contract:

- `get_market_data_ex(..., period="1m")` supplies history.
- `get_full_tick()` supplies a current snapshot.
- `subscribe_quote(..., period="1m", callback=...)` supplies genuine callbacks.
- A partially failed multi-symbol subscription unsubscribes IDs already created.

Unit tests use an injected xtdata-compatible client. Passing those tests does
not prove that a local QMT terminal is installed, licensed, logged in, or
connected. A separate local smoke test is required before enabling live radar
use.

Run that read-only check in the Python environment used by QMT:

```bash
python scripts/smoke_xtquant_market_data.py --symbol 600519
```

The script imports only `xtdata`, reads one snapshot and up to five 1m bars,
and prints timestamps and health diagnostics. It does not import `xttrader`.

Official reference: <https://dict.thinktrader.net/nativeApi/xtdata.html>

Alpaca keeps the configured feed (`iex`, `sip`, or another supported stock
feed) on every fact. The adapter subscribes to both normal minute bars and
updated bars so late trades can replace an earlier minute before higher
timeframes are rebuilt. IEX and SIP coverage must not be treated as equivalent.

Official references:

- <https://docs.alpaca.markets/us/docs/streaming-market-data>
- <https://docs.alpaca.markets/us/v1.1/docs/historical-stock-data-1>

## Research-only boundary

This layer outputs point-in-time facts and data-quality permissions. Feature
calculation, signal interpretation, notifications, portfolio decisions, and
execution remain separate. No adapter method accepts order parameters or
returns a buy/sell instruction.
