"""Small, deterministic recorder/validator for E06 benchmark JSONL rows."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "e06-v0.1"
LAYERS = ("A_repository_read_set", "B_tool_output", "C_conversation_history")
METRICS = (
    "files_opened_to_understand", "files_opened_to_modify", "bytes_read",
    "estimated_or_measured_input_tokens", "semantic_owners_touched",
    "private_attributes_crossed", "provider_specific_contracts_seen",
    "decision_branches_relevant", "tests_needed_for_confidence",
    "time_to_identify_authoritative_owner_seconds", "wrong_path_count",
    "reopen_count",
)


def count_tokens(text: str, encoding: str = "cl100k_base") -> int:
    """Count with a named tiktoken encoding; no byte-to-token approximation."""
    import tiktoken

    return len(tiktoken.get_encoding(encoding).encode(text))


def make_row(*, task_id: str, run_id: str, context: str, contamination: bool = True,
             layer_text: dict[str, str] | None = None, **metrics: Any) -> dict[str, Any]:
    unknown = set(metrics) - set(METRICS)
    if unknown:
        raise ValueError(f"unknown metrics: {sorted(unknown)}")
    layer_text = layer_text or {layer: "" for layer in LAYERS}
    if set(layer_text) != set(LAYERS):
        raise ValueError("layer_text must contain exactly Layers A, B, and C")
    measured = {name: metrics.get(name, None) for name in METRICS}
    measured["estimated_or_measured_input_tokens"] = {
        "value": metrics.get("estimated_or_measured_input_tokens"),
        "encoding": "cl100k_base" if metrics.get("estimated_or_measured_input_tokens") is not None else None,
        "source": "tiktoken" if metrics.get("estimated_or_measured_input_tokens") is not None else None,
    }
    return {
        "schema_version": SCHEMA_VERSION, "task_id": task_id, "run_id": run_id,
        "context": context, "contamination": contamination, "official_status": "PENDING_FRESH_CONTEXT",
        "layers": {layer: {"text_bytes": len(layer_text[layer].encode("utf-8")),
                           "tokens": count_tokens(layer_text[layer])} for layer in LAYERS},
        "metrics": measured,
        "correctness_gate": {"result": "PENDING", "protected_governance": []},
    }


def validate_row(row: dict[str, Any]) -> None:
    if row.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported schema_version")
    if set(row.get("layers", {})) != set(LAYERS):
        raise ValueError("layers A/B/C are required and must remain separate")
    if row.get("contamination") is not True and row.get("official_status") == "PENDING_FRESH_CONTEXT":
        raise ValueError("fresh-context rows must explicitly set contamination=true until reviewed")
    if row.get("correctness_gate", {}).get("result") == "PASS" and row.get("contamination"):
        raise ValueError("contaminated rows cannot pass the official correctness gate")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--validate", type=Path)
    args = parser.parse_args()
    if args.self_test:
        row = make_row(task_id="T5", run_id="smoke", context="current-chat")
        validate_row(row)
        print(json.dumps(row, ensure_ascii=False, sort_keys=True))
    elif args.validate:
        for line in args.validate.read_text(encoding="utf-8").splitlines():
            if line.strip():
                validate_row(json.loads(line))


if __name__ == "__main__":
    main()
