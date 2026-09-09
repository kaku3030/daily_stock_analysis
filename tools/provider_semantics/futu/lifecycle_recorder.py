"""Wave 2 lifecycle evidence recorder.

Extends the Wave 1 ``EvidenceRecorder`` (recorder.py) with a fourth
append-only stream, ``lifecycle.jsonl``, carrying connection/subscription
lifecycle events with the exact field set the Wave 2 brief requires:
observed_at_utc, monotonic_ns, local_event_seq, thread_id, runtime_run_id,
connection_attempt_id, quote_context_id, event_type, symbol, stream_type,
raw provider timestamp, raw payload, raw ret_code, raw error text, and an
explicit ``origin`` (HARNESS vs PROVIDER_SDK) so a harness-manufactured
event (e.g. "we are about to close the context now") is never confused with
something the SDK itself actually emitted.

Only the lifecycle event types the SDK genuinely exposes or that the
harness itself genuinely performs are used -- see LIFECYCLE_EVENT_TYPES.
Nothing is invented.
"""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Any

from recorder import EvidenceRecorder, utc_now_iso

LIFECYCLE_EVENT_TYPES = frozenset(
    {
        "CONTEXT_CREATE_BEGIN",
        "CONTEXT_CREATE_OK",
        "CONTEXT_CREATE_ERROR",
        "SUBSCRIBE_CALL_BEGIN",
        "SUBSCRIBE_CALL_RETURN",
        "UNSUBSCRIBE_CALL_BEGIN",
        "UNSUBSCRIBE_CALL_RETURN",
        "DATA_CALLBACK",
        "CONNECTION_ERROR",
        "PROVIDER_EVENT",
        "CONTEXT_CLOSE_BEGIN",
        "CONTEXT_CLOSE_END",
        "OPEND_STOP_BEGIN",
        "OPEND_STOP_CONFIRMED",
        "OPEND_START_BEGIN",
        "OPEND_READY",
        # Harness-only bookkeeping, not claimed to be SDK-exposed events:
        "QUERY_SUBSCRIPTION_CALL",
        "BASELINE_CHECKPOINT",
        "FAULT_INJECTION_BEGIN",
        "FAULT_INJECTION_END",
    }
)


class LifecycleRecorder(EvidenceRecorder):
    def __init__(self, run_dir: Path, runtime_run_id: str) -> None:
        super().__init__(run_dir)
        self.runtime_run_id = runtime_run_id
        self._lifecycle_path = self.run_dir / "lifecycle.jsonl"
        self._lifecycle_path.touch(exist_ok=False)

    def record_lifecycle(
        self,
        *,
        event_type: str,
        origin: str,
        connection_attempt_id: str | None = None,
        quote_context_id: str | None = None,
        symbol: str | None = None,
        stream_type: str | None = None,
        raw_provider_timestamp: Any = None,
        raw_payload: Any = None,
        raw_ret_code: Any = None,
        raw_error_text: str | None = None,
    ) -> dict:
        if event_type not in LIFECYCLE_EVENT_TYPES:
            raise ValueError(f"unrecognized lifecycle event_type {event_type!r} -- do not invent event types")
        if origin not in ("HARNESS", "PROVIDER_SDK"):
            raise ValueError(f"origin must be HARNESS or PROVIDER_SDK, got {origin!r}")

        record = {
            "observed_at_utc": utc_now_iso(),
            "monotonic_ns": time.monotonic_ns(),
            "local_event_seq": self.next_seq(),
            "thread_id": threading.get_ident(),
            "runtime_run_id": self.runtime_run_id,
            "connection_attempt_id": connection_attempt_id,
            "quote_context_id": quote_context_id,
            "event_type": event_type,
            "origin": origin,
            "symbol": symbol,
            "stream_type": stream_type,
            "raw_provider_timestamp": raw_provider_timestamp,
            "raw_payload": raw_payload,
            "raw_ret_code": raw_ret_code,
            "raw_error_text": raw_error_text,
        }
        from models import scrub_secrets  # local import to avoid a cycle at module load

        record["raw_payload"] = scrub_secrets(record["raw_payload"])
        self._append_jsonl(self._lifecycle_path, record)
        return record

    def read_lifecycle(self) -> list[dict]:
        if not self._lifecycle_path.exists():
            return []
        import json

        records = []
        with self._lifecycle_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if line:
                    records.append(json.loads(line))
        return records
