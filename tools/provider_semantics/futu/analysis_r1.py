"""Revision R1 re-adjudication of F02 / F28 from EXISTING raw evidence.

Reads ONLY an already-completed run's ``events.jsonl`` (never rewritten).
Writes a NEW, separately-named derived artifact under that run's
``derived/`` subdirectory -- it never overwrites ``observations.json`` or
``results.json`` from the original run.

This is deliberately a standalone script, not a change to
``wave1_runner.py``'s own ``analyze_events`` -- Part A of this task is a
sharper, transition-edge-focused re-adjudication, not a fix to the original
per-push delay computation (which stays as it was, superseded but not
deleted).

Definitions (per the task brief):

    first_callback_at(K)              -- observed_at_utc of the first K_1M
                                          push carrying time_key == K
    last_callback_at(K)               -- observed_at_utc of the last such push
    callback_count(K)                 -- how many pushes carried time_key == K
    next_time_key(K)                  -- the time_key immediately following K
                                          in the order distinct keys were
                                          first observed
    first_callback_for_next_time_key  -- first_callback_at(next_time_key(K))

Transition metrics, computed under two EXPLICITLY LABELED, mutually
exclusive interpretation candidates for what a raw ``time_key`` string
denotes:

    time_key_is_interval_start: interval K spans [time_key(K), time_key(K)+60s)
        -> interpreted_boundary(K) = time_key(K) + 60s
    time_key_is_interval_end:   interval K spans [time_key(K)-60s, time_key(K))
        -> interpreted_boundary(K) = time_key(K)

For each candidate:
    last_callback(K)      - interpreted_boundary(K)
    first_callback(K+1)   - interpreted_boundary(K)

These are reported as TRANSITION metrics, never called "publication delay"
(that term described a different, coarser per-push measure in the
superseded observations.json and is not reused here).

Discriminating logic: under the TRUE interpretation, the moment a NEW
time_key first appears (first_callback(K+1)) should sit very close to (at or
just after) interval K's real closing boundary -- a tight, near-zero,
one-sided distribution. Under the FALSE interpretation, that same quantity
is offset by a full interval width (~60s) because interpreted_boundary(K)
was computed 60s away from where the real close actually is. Whichever
candidate produces the tighter, more nearly-zero, non-negative-skewed
first_callback(K+1)-boundary(K) distribution is the one the raw evidence
favors -- this script computes and reports both distributions but does not
by itself elevate that favor to VERIFIED.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent))

from recorder import utc_now_iso  # noqa: E402

# Same explicit-assumption pattern as wave1_runner.py's F28 computation --
# never silently attached, always recorded in the output alongside the
# numbers it produced.
_MARKET_TZ_INTERPRETATION_CANDIDATE = {
    "HK": "Asia/Hong_Kong",
    "US": "America/New_York",
    "CN": "Asia/Shanghai",
    "SH": "Asia/Shanghai",
    "SZ": "Asia/Shanghai",
}


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def _load_events(events_path: Path) -> list[dict]:
    records = []
    with events_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def _dist(samples: list[float]) -> dict:
    if not samples:
        return {"count": 0}
    ordered = sorted(samples)
    out = {
        "count": len(ordered),
        "min": ordered[0],
        "p50": statistics.median(ordered),
        "max": ordered[-1],
    }
    if len(ordered) >= 20:
        out["p95"] = ordered[int(len(ordered) * 0.95) - 1]
    if len(ordered) >= 100:
        out["p99"] = ordered[int(len(ordered) * 0.99) - 1]
    return out


def build_per_time_key_records(kline_events: list[dict]) -> dict[str, list[dict]]:
    """Group by symbol, then by time_key, preserving local sequence order."""

    by_symbol: dict[str, list[dict]] = {}
    for e in kline_events:
        by_symbol.setdefault(e["symbol"], []).append(e)

    result: dict[str, list[dict]] = {}
    for symbol, events in by_symbol.items():
        ordered = sorted(events, key=lambda r: r["event_seq_local"])

        # Distinct time_key values, in the order first observed.
        key_order: list[str] = []
        seen = set()
        pushes_by_key: dict[str, list[dict]] = {}
        for e in ordered:
            time_key = e["raw_payload"].get("time_key")
            if time_key is None:
                continue
            if time_key not in seen:
                seen.add(time_key)
                key_order.append(time_key)
            pushes_by_key.setdefault(time_key, []).append(e)

        records = []
        for i, time_key in enumerate(key_order):
            pushes = pushes_by_key[time_key]
            next_time_key = key_order[i + 1] if i + 1 < len(key_order) else None
            first_callback_for_next = (
                pushes_by_key[next_time_key][0]["observed_at_utc"] if next_time_key else None
            )
            records.append(
                {
                    "time_key": time_key,
                    "first_callback_at": pushes[0]["observed_at_utc"],
                    "last_callback_at": pushes[-1]["observed_at_utc"],
                    "callback_count": len(pushes),
                    "next_time_key": next_time_key,
                    "first_callback_for_next_time_key": first_callback_for_next,
                    # Raw OHLCV of the LAST push for this key, for audit --
                    # not used in the transition computation itself.
                    "last_push_raw_payload": pushes[-1]["raw_payload"],
                }
            )
        result[symbol] = records
    return result


def compute_transition_metrics(per_key_records: dict[str, list[dict]], tz_name: str | None) -> dict:
    if tz_name is None:
        return {
            "assumed_timezone_interpretation_candidate": None,
            "error": "no timezone interpretation candidate registered for this market; "
            "refusing to silently assume one",
            "per_symbol": {},
        }

    tz = ZoneInfo(tz_name)

    def to_naive_local(observed_at_utc: str) -> datetime:
        return datetime.fromisoformat(observed_at_utc).astimezone(tz).replace(tzinfo=None)

    per_symbol: dict[str, dict] = {}
    for symbol, records in per_key_records.items():
        last_minus_boundary_end: list[float] = []
        last_minus_boundary_start: list[float] = []
        firstnext_minus_boundary_end: list[float] = []
        firstnext_minus_boundary_start: list[float] = []

        for rec in records:
            if rec["next_time_key"] is None:
                continue  # no transition to measure for the final observed key
            try:
                time_key_naive = datetime.fromisoformat(rec["time_key"])
            except Exception:
                continue

            boundary_if_end = time_key_naive
            boundary_if_start = time_key_naive + timedelta(seconds=60)

            last_local = to_naive_local(rec["last_callback_at"])
            last_minus_boundary_end.append((last_local - boundary_if_end).total_seconds())
            last_minus_boundary_start.append((last_local - boundary_if_start).total_seconds())

            if rec["first_callback_for_next_time_key"] is not None:
                first_next_local = to_naive_local(rec["first_callback_for_next_time_key"])
                firstnext_minus_boundary_end.append((first_next_local - boundary_if_end).total_seconds())
                firstnext_minus_boundary_start.append((first_next_local - boundary_if_start).total_seconds())

        per_symbol[symbol] = {
            "transitions_measured": len(last_minus_boundary_end),
            "time_key_is_interval_end_candidate": {
                "last_callback(K)_minus_interpreted_boundary(K)": _dist(last_minus_boundary_end),
                "first_callback(K+1)_minus_interpreted_boundary(K)": _dist(firstnext_minus_boundary_end),
            },
            "time_key_is_interval_start_candidate": {
                "last_callback(K)_minus_interpreted_boundary(K)": _dist(last_minus_boundary_start),
                "first_callback(K+1)_minus_interpreted_boundary(K)": _dist(firstnext_minus_boundary_start),
            },
        }

    return {
        "assumed_timezone_interpretation_candidate": tz_name,
        "per_symbol": per_symbol,
    }


def _discrimination_note(transition_metrics: dict) -> list[str]:
    """Plain-language, non-overclaiming summary of which candidate's
    transition-edge distribution is tighter/closer to zero -- observation
    only, not an automatic VERIFIED declaration.
    """

    notes = []
    for symbol, metrics in transition_metrics.get("per_symbol", {}).items():
        end_dist = metrics["time_key_is_interval_end_candidate"]["first_callback(K+1)_minus_interpreted_boundary(K)"]
        start_dist = metrics["time_key_is_interval_start_candidate"]["first_callback(K+1)_minus_interpreted_boundary(K)"]
        if end_dist.get("count", 0) == 0:
            notes.append(f"{symbol}: no transitions measured.")
            continue
        notes.append(
            f"{symbol}: first_callback(K+1) - boundary(K) under 'time_key_is_interval_end' has "
            f"p50={end_dist.get('p50')}, min={end_dist.get('min')}, max={end_dist.get('max')} "
            f"(n={end_dist.get('count')}); under 'time_key_is_interval_start' has "
            f"p50={start_dist.get('p50')}, min={start_dist.get('min')}, max={start_dist.get('max')} "
            f"(n={start_dist.get('count')}). The candidate whose distribution clusters tightly near "
            f"(and slightly above) zero is the one this raw evidence favors as the moment a new "
            f"time_key first appears relative to that key's own interpreted boundary; a full "
            f"~60s-offset distribution favors the other candidate instead."
        )
    return notes


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="F02/F28 revision-R1 transition-edge re-adjudication")
    parser.add_argument(
        "--run-dir",
        default=str(Path(__file__).resolve().parent / "runs" / "2026-09-08T06-32-20-832577Z"),
    )
    parser.add_argument("--market", default="HK")
    args = parser.parse_args(argv)

    run_dir = Path(args.run_dir)
    events_path = run_dir / "events.jsonl"
    if not events_path.exists():
        print(f"EXECUTION BLOCKED: raw evidence file not found: {events_path}")
        return 2

    raw_sha256 = _sha256_file(events_path)
    events = _load_events(events_path)
    kline_events = [e for e in events if e["stream_type"].startswith("K_") and e["event_type"] == "push"]

    per_key_records = build_per_time_key_records(kline_events)
    tz_name = _MARKET_TZ_INTERPRETATION_CANDIDATE.get(args.market.upper())
    transition_metrics = compute_transition_metrics(per_key_records, tz_name)
    discrimination_notes = _discrimination_note(transition_metrics)

    derived_dir = run_dir / "derived"
    derived_dir.mkdir(exist_ok=True)

    artifact = {
        "analysis_revision": "r1",
        "supersedes": {
            "note": "Does not delete or modify prior outputs. The original run's observations.json "
            "F02/F28 fields used a coarser per-push delay measure (there called 'publication delay'); "
            "this artifact supersedes that F02/F28 interpretation with transition-edge metrics and "
            "does not reuse the term 'publication delay'.",
            "prior_files_left_untouched": ["../observations.json", "../results.json"],
        },
        "derived_from_raw": {
            "path": str(events_path),
            "sha256": raw_sha256,
        },
        "created_at": utc_now_iso(),
        "market": args.market,
        "per_time_key_records_by_symbol": per_key_records,
        "transition_metrics": transition_metrics,
        "discrimination_notes": discrimination_notes,
    }

    out_path = derived_dir / "r1_f02_f28_transition_analysis.json"
    if out_path.exists():
        # Never overwrite a prior derived artifact either -- if this script
        # is re-run, a new revision file is created instead.
        existing_revisions = sorted(derived_dir.glob("r*_f02_f28_transition_analysis.json"))
        next_n = len(existing_revisions) + 1
        out_path = derived_dir / f"r{next_n}_f02_f28_transition_analysis.json"

    out_path.write_text(json.dumps(artifact, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote derived artifact: {out_path}")
    print(f"Raw evidence sha256: {raw_sha256}")
    for note in discrimination_notes:
        print(note)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
