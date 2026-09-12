"""Slice C bounded asynchronous bridge to the Slice B supervisor.

This module contains no provider SDK integration.  The one-slot handoff is
deliberately not a durable backlog: the Controller remains the sole backlog
owner until local acceptance succeeds.
"""

from __future__ import annotations

import queue
import threading
import time
from typing import Callable

from .commands import ProviderCommand, ProviderCommandExecutor, ProviderCommandResult
from .provider_worker_contracts import ProviderExecutionOutcome, ResolvedProviderCommandOutcome
from .provider_worker_supervisor import ProviderWorkerSupervisor


class AdapterBusyError(RuntimeError):
    """The bounded local handoff cannot accept another command."""


class AdapterClosedError(RuntimeError):
    """The adapter is closed to new local acceptance."""


class ProviderWorkerExecutorAdapter(ProviderCommandExecutor):
    """Single-dispatcher, capacity-one, nonblocking executor bridge."""

    def __init__(
        self,
        supervisor: ProviderWorkerSupervisor,
        *,
        result_sink: Callable[[ProviderCommandResult], None],
    ) -> None:
        self._supervisor = supervisor
        self._result_sink = result_sink
        self._handoff: queue.Queue[ProviderCommand] = queue.Queue(maxsize=1)
        self._closed = threading.Event()
        self._accept_lock = threading.Lock()
        self._accepted = threading.Event()
        self._diagnostics: list[str] = []
        self._diagnostic_lock = threading.Lock()
        self._thread = threading.Thread(target=self._dispatch_loop, name="provider-worker-dispatcher", daemon=True)
        self._thread.start()

    @property
    def diagnostics(self) -> tuple[str, ...]:
        with self._diagnostic_lock:
            return tuple(self._diagnostics)

    def register_result_sink(self, sink: Callable[[ProviderCommandResult], None]) -> None:
        self._result_sink = sink

    def submit(self, command: ProviderCommand) -> None:
        with self._accept_lock:
            if self._closed.is_set():
                raise AdapterClosedError("adapter is closed")
            try:
                self._handoff.put_nowait(command)
            except queue.Full as exc:
                raise AdapterBusyError("adapter handoff capacity is one") from exc
        self._accepted.set()

    def _dispatch_loop(self) -> None:
        while True:
            if self._closed.is_set() and self._handoff.empty():
                return
            try:
                command = self._handoff.get(timeout=0.05)
            except queue.Empty:
                continue
            try:
                outcome = self._supervisor.submit_command(command)
                self._deliver(outcome)
            finally:
                self._accepted.clear()
                self._handoff.task_done()

    def _deliver(self, outcome: ResolvedProviderCommandOutcome) -> None:
        result = ProviderCommandResult(
            command_id=outcome.command.command_id,
            command_type=outcome.command.command_type,
            succeeded=outcome.outcome is ProviderExecutionOutcome.SUCCEEDED,
            controller_generation=outcome.command.controller_generation,
            desired_registry_revision=outcome.command.desired_registry_revision,
            completed_at=outcome.terminal_at_utc,
            error=outcome.provider_error_message or outcome.diagnostic_reason,
            raw_payload=outcome.normalized_provider_payload,
        )
        try:
            self._result_sink(result)
        except Exception as exc:  # sink failure is diagnostic only
            with self._diagnostic_lock:
                self._diagnostics.append(f"result sink failed for {result.command_id}: {exc!r}")

    def shutdown(self) -> None:
        with self._accept_lock:
            self._closed.set()
        # Let the accepted item leave the adapter queue and enter Supervisor
        # admission before closing Supervisor; this preserves its authority
        # to mint CANCELLED_SHUTDOWN.
        while not self._handoff.empty():
            time.sleep(0.001)
        self._supervisor.shutdown()
        self._handoff.join()
        self._thread.join()


def dispatch_one_command(controller, adapter: ProviderWorkerExecutorAdapter) -> bool:
    """Claim one queue head only after atomic local adapter acceptance."""
    command = controller.peek_command_for_worker()
    if command is None:
        return False
    adapter.submit(command)
    controller.acknowledge_command_for_worker(command)
    return True
