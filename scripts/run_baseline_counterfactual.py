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


def _metrics(returns: list[float], signals: list[bool]) -> dict[str, float]:
    selected = [value for value, signal in zip(returns, signals) if signal]
    equity = 1.0
    for value in selected:
        equity *= 1.0 + value
    return {"observations": float(len(returns)), "coverage": len(selected) / len(returns) if returns else 0.0,
            "cumulative_return": equity - 1.0, "hit_rate": sum(value > 0 for value in selected) / len(selected) if selected else 0.0}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=20260913)
    args = parser.parse_args()
    returns = _returns(args.csv)
    base = [value > 0 for value in returns]
    placebo = base[:]
    random.Random(args.seed).shuffle(placebo)
    variants = {"without_rule": [False] * len(returns), "with_rule": base,
                "delayed_rule": [False] + base[:-1], "shuffled_placebo": placebo,
                "regime_conditioned": [signal and returns[i - 1] >= 0 for i, signal in enumerate(base)]}
    print(json.dumps({"schema": "radar-baseline-counterfactual-v0.1", "source": str(args.csv),
                      "seed": args.seed, "variants": {name: _metrics(returns, signals) for name, signals in variants.items()}}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
