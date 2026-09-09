"""Offline analyzer for Futu K_15M/K_60M timestamp-semantics evidence.

EVIDENCE ANALYSIS ONLY.  It consumes raw files produced by
``kline_timestamp_probe.py`` and/or ``kline_snapshot_probe.py`` and emits
mechanical observations.  It does not promote any fact to VERIFIED.

The analyzer keeps competing hypotheses explicit:

- START_BOUNDARY: first callback for a ``time_key`` should cluster near the
  wall-clock represented by that same key.
- END_BOUNDARY: first callback for a ``time_key`` should cluster roughly one
  interval *before* the wall-clock represented by that key, because the key
  names the upcoming interval end.

For K_60M it also reports whether observed keys fit a 09:30-anchored sequence
or a clock-hour sequence.  These are observations, not provider contracts.
"""

from __future__ import annotations

import argparse
import json
import statistics
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
INTERVAL_MINUTES = {"K_15M": 15, "K_60M": 60}
MATERIAL_FIELDS = ("open", "close", "high", "low", "volume", "turnover")


def _parse_observed_utc(value: str) -> datetime:
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        raise ValueError("observed_at_utc must be timezone-aware")
    return dt.astimezone(ET)


def _parse_time_key_et(value: str) -> datetime:
    # Provider documentation says US time_key is US Eastern by default.  The
    # raw value itself is naive, so timezone attachment is an explicit
    # provider-documented interpretation used only in this analyzer.
    return datetime.strptime(value, "%Y-%m-%d %H:%M:%S").replace(tzinfo=ET)


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _material_signature(payload: dict[str, Any]) -> tuple[Any, ...]:
    return tuple(payload.get(field) for field in MATERIAL_FIELDS)


def analyze_live_events(events: list[dict[str, Any]]) -> dict[str, Any]:
    by_stream_key: dict[str, dict[str, list[dict[str, Any]]]] = {
        stream: defaultdict(list) for stream in INTERVAL_MINUTES
    }
    for event in events:
        stream = str(event.get("stream_type") or "")
        if stream not in INTERVAL_MINUTES:
            continue
        payload = event.get("raw_payload") or {}
        key = payload.get("time_key")
        observed = event.get("observed_at_utc")
        if key and observed:
            by_stream_key[stream][str(key)].append(event)

    result: dict[str, Any] = {}
    for stream, interval_minutes in INTERVAL_MINUTES.items():
        key_map = by_stream_key[stream]
        per_key: list[dict[str, Any]] = []
        first_minus_key_seconds: list[float] = []
        first_minus_end_candidate_start_seconds: list[float] = []

        for key in sorted(key_map):
            samples = sorted(key_map[key], key=lambda item: item.get("monotonic_ns", 0))
            first = samples[0]
            provider_key = _parse_time_key_et(key)
            first_observed = _parse_observed_utc(str(first["observed_at_utc"]))
            delta_start = (first_observed - provider_key).total_seconds()
            candidate_period_start = provider_key - timedelta(minutes=interval_minutes)
            delta_end = (first_observed - candidate_period_start).total_seconds()
            first_minus_key_seconds.append(delta_start)
            first_minus_end_candidate_start_seconds.append(delta_end)

            signatures = {
                _material_signature(sample.get("raw_payload") or {})
                for sample in samples
            }
            per_key.append({
                "time_key": key,
                "first_observed_et": first_observed.isoformat(),
                "callback_count": len(samples),
                "distinct_material_payload_count": len(signatures),
                "forming_mutation_observed": len(signatures) > 1,
                "first_callback_minus_time_key_seconds": delta_start,
                "first_callback_minus_candidate_period_start_if_key_is_end_seconds": delta_end,
            })

        keys = [_parse_time_key_et(key) for key in sorted(key_map)]
        minute_pairs = [(dt.hour, dt.minute) for dt in keys]
        result[stream] = {
            "distinct_time_key_count": len(key_map),
            "time_keys": [dt.isoformat() for dt in keys],
            "wall_clock_hour_minute_pairs": minute_pairs,
            "per_key": per_key,
            "forming_mutation_key_count": sum(1 for row in per_key if row["forming_mutation_observed"]),
            "first_callback_minus_time_key_seconds_summary": _summary(first_minus_key_seconds),
            "first_callback_minus_candidate_period_start_if_key_is_end_seconds_summary": _summary(
                first_minus_end_candidate_start_seconds
            ),
            "alignment_candidates": _alignment_candidates(stream, keys),
            "adjudication": "MECHANICAL_OBSERVATION_ONLY",
        }
    return result


def _alignment_candidates(stream: str, keys: list[datetime]) -> dict[str, Any]:
    if not keys:
        return {
            "rth_0930_anchor_matches_all": None,
            "clock_hour_anchor_matches_all": None,
            "note": "no keys observed",
        }

    if stream == "K_15M":
        # 09:30 is itself on a quarter-hour grid, so minute residue alone
        # cannot distinguish a RTH anchor from a generic clock-quarter anchor.
        quarter = all(dt.minute in {0, 15, 30, 45} for dt in keys)
        return {
            "quarter_hour_grid_matches_all": quarter,
            "rth_0930_vs_clock_quarter_discriminating": False,
            "note": "K15 minute residue cannot distinguish 09:30 anchor from clock-quarter grid",
        }

    # K60 is discriminating: 09:30 anchor -> every key minute == 30;
    # clock-hour anchor -> every key minute == 00.
    return {
        "rth_0930_anchor_minute_30_matches_all": all(dt.minute == 30 for dt in keys),
        "clock_hour_anchor_minute_00_matches_all": all(dt.minute == 0 for dt in keys),
        "other_minute_values": sorted({dt.minute for dt in keys if dt.minute not in {0, 30}}),
    }


def _summary(values: list[float]) -> dict[str, Any] | None:
    if not values:
        return None
    return {
        "n": len(values),
        "min": min(values),
        "max": max(values),
        "median": statistics.median(values),
        "mean": statistics.mean(values),
    }


def analyze_snapshot_document(document: dict[str, Any]) -> dict[str, Any]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for observation in document.get("observations", []):
        op = observation.get("requested_operation")
        ktype = observation.get("requested_ktype")
        result = observation.get("result") or {}
        child = result.get("child_result") or {}
        if not result.get("completed") or result.get("timed_out") or child.get("status") != "OK":
            continue
        grouped[(str(op), str(ktype))].append(child)

    output: dict[str, Any] = {}
    for (operation, ktype), samples in sorted(grouped.items()):
        latest_rows = []
        for sample in samples:
            rows = sample.get("raw_rows") or []
            if isinstance(rows, list) and rows:
                # request_history_kline may return a tuple-adapted shape only
                # if SDK signature changes; keep this conservative.
                row_candidates = [row for row in rows if isinstance(row, dict)]
                if row_candidates:
                    latest_rows.append(row_candidates[-1])

        by_key: dict[str, list[tuple[Any, ...]]] = defaultdict(list)
        for row in latest_rows:
            key = row.get("time_key")
            if key:
                by_key[str(key)].append(_material_signature(row))

        output[f"{operation}:{ktype}"] = {
            "successful_sample_count": len(samples),
            "latest_rows": latest_rows,
            "same_time_key_material_mutation": {
                key: len(set(signatures)) > 1
                for key, signatures in sorted(by_key.items())
            },
            "forming_bar_evidence_candidate": (
                "PRESENT_IF_HISTORY_SAME_KEY_MUTATES"
                if operation == "history"
                else "PRESENT_IF_CURRENT_SAME_KEY_MUTATES"
            ),
            "adjudication": "MECHANICAL_OBSERVATION_ONLY",
        }
    return output


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Offline Futu K15/K60 timestamp evidence analyzer")
    parser.add_argument("--events", type=Path, help="events.jsonl from kline_timestamp_probe.py")
    parser.add_argument("--snapshots", type=Path, help="JSON from kline_snapshot_probe.py")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if not args.events and not args.snapshots:
        parser.error("at least one of --events or --snapshots is required")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    report: dict[str, Any] = {
        "analysis": "futu_k15_k60_timestamp_semantics",
        "generated_at_utc": datetime.now(tz=ZoneInfo("UTC")).isoformat(),
        "semantic_promotion": "NONE_AUTOMATIC",
    }
    if args.events:
        report["live"] = analyze_live_events(_load_jsonl(args.events))
    if args.snapshots:
        report["snapshots"] = analyze_snapshot_document(
            json.loads(args.snapshots.read_text(encoding="utf-8"))
        )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.output.exists():
        raise FileExistsError(args.output)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
