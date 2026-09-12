"""The sole provider-neutral execution seam used by the fake child."""

from __future__ import annotations

import os
import queue
import time
from datetime import datetime, timezone
from typing import Any, Mapping

from .provider_worker_contracts import ProviderExecutionOutcome, ProviderWorkerEvidenceKind

_ALLOWED_BEHAVIORS = frozenset({
    "success", "provider_rejected", "exception", "hang", "wait_then_succeed",
    "exit_before_result", "malformed_frame", "oversized_frame",
})


def execute_fake_command_in_child(
    command: Mapping[str, Any],
    *,
    result_queue: Any,
    release_event: Any,
    worker_generation: int,
) -> bool:
    """Execute one bounded fake command; called only by the spawned child.

    The input is provider-neutral wire data. Unknown keys, non-mapping payloads,
    and arbitrary/callable values fail closed before any provider-style result.
    Returns whether the child should continue its command loop.
    """
    payload = command.get("payload")
    if not isinstance(payload, Mapping) or set(payload) - {"behavior"}:
        raise ValueError("child boundary accepts only the bounded behavior field")
    behavior = payload.get("behavior", "success")
    if not isinstance(behavior, str) or behavior not in _ALLOWED_BEHAVIORS:
        raise ValueError("unsupported fake executor behavior")
    command_id = command.get("command_id")
    if not isinstance(command_id, str) or not command_id:
        raise ValueError("command_id must be a non-blank string")

    def now() -> str:
        return datetime.now(timezone.utc).isoformat()

    if behavior == "exit_before_result":
        os._exit(3)
    if behavior == "hang":
        release_event.wait()
        os._exit(9)
    if behavior == "wait_then_succeed":
        release_event.wait()
    if behavior == "malformed_frame":
        result_queue.put({"frame_kind": "COMMAND_RESULT", "oops": True})
        return True
    result: dict[str, Any] = {
        "frame_kind": "COMMAND_RESULT", "command_id": command_id,
        "worker_generation": worker_generation,
        "outcome": ProviderExecutionOutcome.SUCCEEDED.value,
        "terminal_observed_at_monotonic_ns": time.monotonic_ns(),
        "terminal_at_utc": now(), "provider_error_code": None,
        "provider_error_message": None,
        "normalized_provider_payload": {"echo": command_id, "child_pid": os.getpid()},
        "diagnostic_reason": None,
    }
    if behavior == "provider_rejected":
        result.update(outcome=ProviderExecutionOutcome.PROVIDER_REJECTED.value,
                      provider_error_code="SIMULATED_REJECT",
                      provider_error_message="simulated provider-style rejection",
                      normalized_provider_payload=None)
    elif behavior == "exception":
        result.update(outcome=ProviderExecutionOutcome.PROVIDER_EXCEPTION.value,
                      normalized_provider_payload=None,
                      diagnostic_reason="simulated child exception: boom")
    elif behavior == "oversized_frame":
        result["normalized_provider_payload"] = {"padding": "x" * 10_000_000}
    result_queue.put(result)
    return True
