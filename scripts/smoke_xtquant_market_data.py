# -*- coding: utf-8 -*-
"""Local, read-only QMT smoke test. No order or trading APIs are imported."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from data_provider.xtquant_market_data_adapter import XtquantMarketDataAdapter


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify local QMT market-data connectivity")
    parser.add_argument("--symbol", default="600519", help="Mainland China stock code")
    args = parser.parse_args()

    try:
        from xtquant import xtdata
    except ImportError as exc:
        raise SystemExit("xtquant is not installed in this Python environment") from exc

    adapter = XtquantMarketDataAdapter(xtdata)
    quote = adapter.get_latest_quote(args.symbol)
    bars = adapter.get_bars(args.symbol, "1m", limit=5)
    print(
        json.dumps(
            {
                "symbol": args.symbol,
                "quote_provider": quote.provider,
                "quote_source_timestamp": quote.source_timestamp.isoformat(),
                "quote_health": quote.health.score if quote.health else None,
                "bar_count": len(bars),
                "latest_bar_start": bars[-1].bar_start.isoformat() if bars else None,
                "latest_bar_closed": bars[-1].is_closed if bars else None,
                "latest_bar_health": bars[-1].health.score if bars and bars[-1].health else None,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
