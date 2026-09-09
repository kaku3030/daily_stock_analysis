"""Futu-specific `ProviderCommandExecutor` (Slice 2).

Bridges `ProviderCommand`/`ProviderCommandResult` (commands.py, LANE 3 of
the blocking execution model) to `FutuStreamingAdapter`
(data_provider/futu_streaming_adapter.py). `submit()` runs synchronously
and may block on a real Futu SDK call -- that is safe ONLY because the
architecture guarantees `submit()` is ever invoked from a dedicated
provider-command worker thread, never from `LiveFeedController.
process_pending`. Nothing in this module enforces that by itself; see
`run_command_worker_once` / `start_command_worker_loop` in controller.py
for the only sanctioned callers.

This is explicitly NOT a solution to the open PRODUCTION_REQUIRED vs
HARNESS_ONLY isolation-mechanism question in
LIVE_FEED_BLOCKING_EXECUTION_MODEL_V0_1.md: a permanently-stuck Futu call
would stall this worker thread indefinitely (it would never return to
pick up further commands), even though it can never block the writer.
Whether that requires process-level isolation remains open for a later
slice -- this executor makes no cancellation or timeout guarantee.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable

from data_provider.futu_streaming_adapter import FutuStreamingAdapter

from .commands import ProviderCommand, ProviderCommandResult, ProviderCommandType


def _default_now_utc() -> datetime:
    return datetime.now(timezone.utc)


class FutuProviderCommandExecutor:
    """Real (non-fake) `ProviderCommandExecutor` for Futu. Every provider
    exception is caught at this boundary and converted into an explicit
    failed `ProviderCommandResult` -- it is never allowed to propagate
    and kill the worker thread's loop, and it is never swallowed silently
    (callers can inspect `result.error`).
    """

    def __init__(self, adapter: FutuStreamingAdapter, *, now_utc: Callable[[], datetime] = _default_now_utc) -> None:
        self._adapter = adapter
        self._now_utc = now_utc
        self._sink: Callable[[ProviderCommandResult], None] | None = None

    def register_result_sink(self, sink: Callable[[ProviderCommandResult], None]) -> None:
        self._sink = sink

    def submit(self, command: ProviderCommand) -> None:
        error: str | None = None
        try:
            self._dispatch(command)
            succeeded = True
        except Exception as exc:  # boundary: normalize ANY provider failure into evidence
            succeeded = False
            error = f"{type(exc).__name__}: {exc}"
        result = ProviderCommandResult(
            command_id=command.command_id,
            command_type=command.command_type,
            succeeded=succeeded,
            controller_generation=command.controller_generation,
            desired_registry_revision=command.desired_registry_revision,
            completed_at=self._now_utc(),
            error=error,
        )
        if self._sink is not None:
            self._sink(result)

    def _dispatch(self, command: ProviderCommand) -> None:
        if command.command_type is ProviderCommandType.CONNECT:
            self._adapter.set_connect_identity(
                runtime_instance_id=command.runtime_instance_id,
                provider_id=command.provider_id,
                controller_generation=command.controller_generation,
            )
            self._adapter.start()
        elif command.command_type is ProviderCommandType.SUBSCRIBE:
            if command.semantic_stream_key is None:
                raise ValueError("SUBSCRIBE command missing semantic_stream_key")
            self._adapter.subscribe_stream(command.semantic_stream_key, stream_subscription_epoch=command.stream_subscription_epoch)
        elif command.command_type is ProviderCommandType.UNSUBSCRIBE:
            if command.semantic_stream_key is None:
                raise ValueError("UNSUBSCRIBE command missing semantic_stream_key")
            self._adapter.unsubscribe_stream(command.semantic_stream_key, stream_subscription_epoch=command.stream_subscription_epoch)
        elif command.command_type is ProviderCommandType.CLOSE:
            self._adapter.stop()
        elif command.command_type is ProviderCommandType.QUERY_SUBSCRIPTION:
            raise NotImplementedError("QUERY_SUBSCRIPTION diagnostic command not wired to a bounded caller in Slice 2")
        elif command.command_type is ProviderCommandType.DIAGNOSTIC:
            raise NotImplementedError("generic DIAGNOSTIC command has no handler in Slice 2")
        else:
            raise ValueError(f"unrecognized command_type {command.command_type!r}")
