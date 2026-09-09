"""Post-hoc, read-only analysis of a completed Wave 2 run's lifecycle.jsonl.

Never rewrites the raw file. Writes a new revision-tagged derived artifact
under <run_dir>/derived/. Opportunistically surfaces F11 (duplicates), F13
(ordering), F14/F15 (progress-identity fields), and F25 (callback
concurrency) -- purely observational, no architecture adjudication.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from recorder import utc_now_iso  # noqa: E402


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _payload_hash(payload: dict) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode("utf-8")).hexdigest()[:16]


def _load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    records = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def analyze_f11_duplicates(callbacks: list[dict]) -> dict:
    """Duplicate = same symbol+stream_type+time_key/data_time AND identical
    raw payload hash. Never deduplicated before this point -- raw evidence
    is untouched; this only counts.
    """

    groups: dict[tuple, list[dict]] = defaultdict(list)
    for e in callbacks:
        payload = e["raw_payload"] or {}
        source_id = payload.get("time_key") or payload.get("data_time")
        key = (e["symbol"], e["stream_type"], source_id, _payload_hash(payload))
        groups[key].append(e)

    duplicate_groups = {str(k): len(v) for k, v in groups.items() if len(v) > 1}
    return {
        "exact_duplicate_group_count": len(duplicate_groups),
        "exact_duplicate_groups": duplicate_groups,
    }


def analyze_f13_ordering(callbacks: list[dict]) -> dict:
    """Compares local callback receive order (event_seq) against the raw
    source identity's own natural order (time_key/data_time string order)
    per symbol+stream_type. Does not assume callback order == causal order.
    """

    by_stream: dict[tuple, list[dict]] = defaultdict(list)
    for e in callbacks:
        by_stream[(e["symbol"], e["stream_type"])].append(e)

    results = {}
    for key, events in by_stream.items():
        ordered_by_seq = sorted(events, key=lambda e: e["local_event_seq"])
        source_ids = [
            (e["raw_payload"] or {}).get("time_key") or (e["raw_payload"] or {}).get("data_time")
            for e in ordered_by_seq
        ]
        non_null = [s for s in source_ids if s is not None]
        is_monotonic_non_decreasing = all(a <= b for a, b in zip(non_null, non_null[1:]))
        inversions = sum(1 for a, b in zip(non_null, non_null[1:]) if a > b)
        results[f"{key[0]}|{key[1]}"] = {
            "callback_count": len(events),
            "source_id_monotonic_non_decreasing_in_receive_order": is_monotonic_non_decreasing,
            "inversion_count": inversions,
        }
    return results


def analyze_f14_f15_progress_identity(callbacks: list[dict]) -> dict:
    """Scan raw payload keys for anything sequence/serial/cursor/packet/
    request/update/version -shaped. Does not assume a field name implies
    progress identity -- just reports what keys exist and whether any
    candidate is present.
    """

    candidate_substrings = ("seq", "serial", "cursor", "packet", "request", "req_id", "update", "version")
    all_keys: set[str] = set()
    candidate_keys: set[str] = set()
    for e in callbacks:
        payload = e["raw_payload"] or {}
        for k in payload.keys():
            all_keys.add(k)
            if any(sub in k.lower() for sub in candidate_substrings):
                candidate_keys.add(k)

    return {
        "all_raw_payload_keys_observed": sorted(all_keys),
        "candidate_progress_identity_keys": sorted(candidate_keys),
        "verdict": "NONE OBSERVED" if not candidate_keys else "CANDIDATE_KEYS_FOUND_NOT_YET_VALIDATED",
    }


def analyze_f25_concurrency(lifecycle_events: list[dict]) -> dict:
    by_event_type: dict[str, set[int]] = defaultdict(set)
    by_stream_type: dict[str, set[int]] = defaultdict(set)
    for e in lifecycle_events:
        by_event_type[e["event_type"]].add(e["thread_id"])
        if e.get("stream_type"):
            by_stream_type[e["stream_type"]].add(e["thread_id"])

    return {
        "thread_ids_per_event_type": {k: sorted(v) for k, v in by_event_type.items()},
        "thread_ids_per_stream_type": {k: sorted(v) for k, v in by_stream_type.items()},
        "quote_and_kline_share_thread": bool(
            by_stream_type.get("QUOTE", set()) & by_stream_type.get("K_1M", set())
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Wave 2 opportunistic post-hoc analysis")
    parser.add_argument("--run-dir", required=True)
    args = parser.parse_args(argv)

    run_dir = Path(args.run_dir)
    lifecycle_path = run_dir / "lifecycle.jsonl"
    if not lifecycle_path.exists():
        print(f"EXECUTION BLOCKED: {lifecycle_path} not found")
        return 2

    raw_sha256_before = _sha256_file(lifecycle_path)
    events = _load_jsonl(lifecycle_path)
    callbacks = [e for e in events if e["event_type"] == "DATA_CALLBACK" and e["raw_payload"]]

    artifact = {
        "analysis_revision": "wave2_r1",
        "created_at": utc_now_iso(),
        "derived_from_raw": {"path": str(lifecycle_path), "sha256_before": raw_sha256_before},
        "f11_duplicates": analyze_f11_duplicates(callbacks),
        "f13_ordering": analyze_f13_ordering(callbacks),
        "f14_f15_progress_identity": analyze_f14_f15_progress_identity(callbacks),
        "f25_concurrency": analyze_f25_concurrency(events),
    }

    raw_sha256_after = _sha256_file(lifecycle_path)
    artifact["derived_from_raw"]["sha256_after"] = raw_sha256_after
    artifact["raw_file_unmodified"] = raw_sha256_before == raw_sha256_after

    derived_dir = run_dir / "derived"
    derived_dir.mkdir(exist_ok=True)
    out_path = derived_dir / "wave2_r1_opportunistic_analysis.json"
    if out_path.exists():
        existing = sorted(derived_dir.glob("wave2_r*_opportunistic_analysis.json"))
        out_path = derived_dir / f"wave2_r{len(existing) + 1}_opportunistic_analysis.json"

    out_path.write_text(json.dumps(artifact, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(f"Wrote: {out_path}")
    print(f"raw_file_unmodified: {artifact['raw_file_unmodified']}")
    print(json.dumps({k: v for k, v in artifact.items() if k not in ("f13_ordering",)}, indent=2, default=str)[:3000])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
