#!/usr/bin/env python3
"""Run a deterministic, research-only baseline counterfactual experiment."""
from __future__ import annotations

import argparse
import csv
import json
import random
from pathlib import Path


def _returns(csv_path: Path) -> list[float]:
    rows = list(csv.DictReader(csv_path.open(encoding="utf-8")))
    closes = [float(row["close"]) for row in rows]
    return [(closes[i] / closes[i - 1]) - 1.0 for i in range(1, len(closes))]


def _metrics(returns: list[float], signals: list[bool], friction_bps: float) -> dict[str, float]:
    selected = [value for value, signal in zip(returns, signals) if signal]
    gross = _gross_return(selected)
    trade_count = sum(signal != previous for previous, signal in zip([False] + signals[:-1], signals))
    # Charge friction on position transitions (entry/exit), not every held bar.
    equity = (1.0 + gross) * (1.0 - friction_bps / 10000.0) ** trade_count
    return {"observations": float(len(returns)), "coverage": len(selected) / len(returns) if returns else 0.0,
            "cumulative_return_net": equity - 1.0, "cumulative_return_gross": gross,
            "trade_count": float(trade_count),
            "friction_bps_per_side": friction_bps,
            "hit_rate": sum(value > 0 for value in selected) / len(selected) if selected else 0.0}


def _gross_return(selected: list[float]) -> float:
    equity = 1.0
    for value in selected:
        equity *= 1.0 + value
    return equity - 1.0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=20260913)
    parser.add_argument("--cost-bps", type=float, default=10.0)
    parser.add_argument("--slippage-bps", type=float, default=5.0)
    args = parser.parse_args()
    returns = _returns(args.csv)
    # PIT-safe signal: yesterday's return may only select today's return.
    base = [False] + [returns[i - 1] > 0 for i in range(1, len(returns))]
    placebo = base[:]
    random.Random(args.seed).shuffle(placebo)
    variants = {"without_rule": [False] * len(returns), "with_rule": base,
                "delayed_rule": [False] + base[:-1], "shuffled_placebo": placebo,
                "regime_conditioned": [signal and returns[i - 1] >= 0 for i, signal in enumerate(base)]}
    friction_bps = args.cost_bps + args.slippage_bps
    print(json.dumps({"schema": "radar-baseline-counterfactual-v0.1", "source": str(args.csv),
                      "seed": args.seed, "variants": {name: _metrics(returns, signals, friction_bps) for name, signals in variants.items()}}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
