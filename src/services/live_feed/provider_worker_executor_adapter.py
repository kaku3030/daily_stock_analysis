"""Provider Worker Supervisor V0.1 -- Slice C: Executor Adapter.

Frozen design (this repository's own design-freeze session, "Provider
Worker Supervisor V0.1 / Slice C -- Executor Adapter"): the narrow
nonblocking bridge between LANE 2 (``LiveFeedController``, command
production / command result consumption) and LANE 3
(``ProviderWorkerSupervisor``, process-isolated execution authority).

``ProviderWorkerSupervisor`` remains the ONLY execution/terminal-outcome
authority. This module owns exactly three things and nothing else:

- its own dispatcher-thread lifecycle (``start``/``stop``);
- mechanical, lossless translation of a Supervisor-authoritative
  ``ResolvedProviderCommandOutcome`` into the controller-facing
  ``ProviderCommandResult`` shape;
- delivering each translated result, once, to the sink the controller
  registered.

It must NEVER: mint a Supervisor terminal outcome itself, filter or judge
result staleness (that remains ``LiveFeedController``/LANE 2's job via
``is_command_result_stale``, untouched here), trigger worker-generation
replacement/restart, retry or replay a command, or reach into
``ProviderWorkerSupervisor`` internals beyond its public API.

Two-phase binding is required because ``LiveFeedController.__init__``
calls ``command_executor.register_result_sink(...)`` during its own
construction -- before a controller instance exists for this adapter to
pull commands from. Composition order:

    supervisor = ProviderWorkerSupervisor(...)
    adapter = ExecutorAdapter(supervisor=supervisor)
    controller = LiveFeedController(command_executor=adapter, ...)
    adapter.attach_controller(controller)
    adapter.start()

No production composition root wires this in this Slice. No Futu/OpenD.
No replacement/retry/replay. No Currentness/Continuity/Health mutation.
"""

from __future__ import annotations

import threading
import logging
from datetime import datetime, timezone
from typing import Callable

from .commands import ProviderCommand, ProviderCommandResult
from .controller import LiveFeedController
from .provider_worker_contracts import ProviderExecutionOutcome, ResolvedProviderCommandOutcome
from .provider_worker_supervisor import (
    AdmissionClosedError,
    CommandInFlightError,
    ProviderWorkerSupervisor,
    SupervisorFatalError,
)

__all__ = [
    "AdapterAlreadyStartedError",
    "AdapterDeadError",
    "AdapterNotAttachedError",
    "AdapterStopTimeout",
    "ExecutorAdapter",
]

# Diagnostic labels for the two legitimate "no Supervisor terminal fact"
# cases (frozen NONE semantics -- see module docstring / design freeze
# "CRITICAL NONE SEMANTICS"). These are never ProviderExecutionOutcome
# values and must never be confused with one.
ADAPTER_ADMISSION_CLOSED = "ADAPTER_ADMISSION_CLOSED"
ADAPTER_SUPERVISOR_FATAL = "ADAPTER_SUPERVISOR_FATAL"

# Bounded, deterministic idle-poll interval for the dispatcher loop while
# the controller's queue is empty. Bounded by threading.Event.wait, not an
# arbitrary sleep -- stop() is observed with at most this much latency,
# and immediately if the event is already set.
_IDLE_POLL_SECONDS = 0.02
_LOGGER = logging.getLogger(__name__)


def _default_now_utc() -> datetime:
    return datetime.now(timezone.utc)


class AdapterNotAttachedError(RuntimeError):
    """Raised by start() if attach_controller() was never called."""


class AdapterAlreadyStartedError(RuntimeError):
    """Raised by start() if the dispatcher thread is currently running."""


class AdapterDeadError(RuntimeError):
    """Raised by start() if this instance already transitioned to
    is_dead=True. An Adapter never resurrects itself -- construct a new
    instance instead (no auto-restart, by design)."""


class AdapterStopTimeout(RuntimeError):
    """Raised by stop() if the dispatcher thread did not confirm
    termination within join_timeout_seconds. Fail loud: never pretend a
    clean shutdown that did not actually happen."""


class ExecutorAdapter:
    """LANE2<->LANE3 nonblocking bridge. See module docstring."""

    def __init__(
        self,
        *,
        supervisor: ProviderWorkerSupervisor,
        now_utc: Callable[[], datetime] = _default_now_utc,
    ) -> None:
        self._supervisor = supervisor
        self._now_utc = now_utc
        self._controller: LiveFeedController | None = None
        self._sink: Callable[[ProviderCommandResult], None] | None = None

        self._state_lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._dead = False

    # ---- ProviderCommandExecutor Protocol conformance ----------------

    def register_result_sink(self, sink: Callable[[ProviderCommandResult], None]) -> None:
        self._sink = sink

    def submit(self, command: ProviderCommand) -> None:
        """Protocol conformance only -- NOT the production dispatch path.

        The frozen Slice C command flow is pull-based: the dispatcher
        thread calls the attached controller's ``drain_commands_for_worker``
        itself. Nothing in this Slice's composition ever calls ``submit``;
        it exists solely so this class structurally satisfies
        ``ProviderCommandExecutor`` for type-checking purposes.
        """

        raise NotImplementedError(
            "ExecutorAdapter.submit() is not the production dispatch path -- "
            "the dispatcher thread pulls from the attached controller instead"
        )

    # ---- two-phase binding --------------------------------------------

    def attach_controller(self, controller: LiveFeedController) -> None:
        self._controller = controller

    # ---- lifecycle ------------------------------------------------------

    def start(self) -> None:
        with self._state_lock:
            if self._controller is None:
                raise AdapterNotAttachedError("attach_controller() must be called before start()")
            if self._dead:
                raise AdapterDeadError("this ExecutorAdapter is dead; construct a new instance")
            if self._thread is not None and self._thread.is_alive():
                raise AdapterAlreadyStartedError("ExecutorAdapter is already running")
            self._stop_event.clear()
            thread = threading.Thread(
                target=self._dispatch_loop,
                name="live-feed-executor-adapter",
                daemon=True,
            )
            self._thread = thread
            thread.start()

    def stop(self, *, join_timeout_seconds: float | None = None) -> None:
        with self._state_lock:
            thread = self._thread
            if thread is None:
                return  # idempotent: never started, or already fully stopped
            self._stop_event.set()
        thread.join(join_timeout_seconds)
        if thread.is_alive():
            raise AdapterStopTimeout(
                f"dispatcher thread did not terminate within {join_timeout_seconds!r} seconds"
            )
        with self._state_lock:
            if self._thread is thread:
                self._thread = None

    @property
    def is_running(self) -> bool:
        with self._state_lock:
            thread = self._thread
            return thread is not None and thread.is_alive() and not self._dead

    @property
    def is_dead(self) -> bool:
        with self._state_lock:
            return self._dead

    def _mark_dead(self) -> None:
        with self._state_lock:
            self._dead = True

    # ---- dispatcher loop (the sole thread ever calling the Supervisor) ---

    def _dispatch_loop(self) -> None:
        controller = self._controller
        assert controller is not None  # guaranteed by start()'s own check
        while not self._stop_event.is_set():
            command = controller.peek_command_for_worker()
            if command is None:
                self._stop_event.wait(_IDLE_POLL_SECONDS)
                continue
            if not self._dispatch_one(command):
                return

    def _dispatch_one(self, command: ProviderCommand) -> bool:
        """Handles exactly one dequeued command. Returns False if the
        dispatcher loop must terminate (fatal/dead); True to continue."""

        try:
            outcome = self._supervisor.submit_command(command)
        except AdmissionClosedError:
            # Admission was never accepted: retain the queue head.  The
            # Supervisor remains the sole authority for terminal facts.
            _LOGGER.error("ExecutorAdapter admission closed for command_id=%s", command.command_id)
            self._mark_dead()
            return False
        except SupervisorFatalError:
            _LOGGER.error("ExecutorAdapter supervisor fatal before acceptance for command_id=%s", command.command_id)
            self._mark_dead()
            return False
        except CommandInFlightError:
            # Structurally unreachable given the single-dispatcher design
            # (this thread never calls submit_command a second time before
            # the first returns) -- if observed, it is an Adapter bug, not
            # operational evidence. Never converted into a command result.
            self._mark_dead()
            return False
        except ValueError:
            # command_id reused with a different immutable identity, or an
            # invalid command type -- a caller/programmer bug, never
            # converted into a command result.
            self._mark_dead()
            return False
        except Exception:
            # Any other unexpected exception is a genuine internal fault.
            # It is never converted to a result and never replayed, but it
            # must remain observable to operators.
            _LOGGER.exception("ExecutorAdapter dispatcher fault for command_id=%s", command.command_id)
            self._mark_dead()
            return False
        controller = self._controller
        assert controller is not None
        controller.ack_command_for_worker(command.command_id)
        return self._deliver(self._translate(outcome))

    # ---- translation (mechanical only -- no judgment) --------------------

    def _admission_result(self, command: ProviderCommand, label: str) -> ProviderCommandResult:
        """Builds the result for the two legitimate no-terminal-fact cases
        (AdmissionClosedError / SupervisorFatalError). provider_execution_
        outcome stays None -- it must never be confused with a genuine
        Supervisor outcome value. succeeded=False here is legacy/non-
        authoritative only; consumers must read the diagnostic label, not
        infer "provider execution failed" from this flag.
        """

        return ProviderCommandResult(
            command_id=command.command_id,
            command_type=command.command_type,
            succeeded=False,
            controller_generation=command.controller_generation,
            desired_registry_revision=command.desired_registry_revision,
            completed_at=self._now_utc(),
            error=label,
            raw_payload=None,
            worker_generation=None,
            provider_execution_outcome=None,
            provider_error_code=None,
            provider_error_message=None,
            diagnostic_reason=label,
        )

    def _translate(self, outcome: ResolvedProviderCommandOutcome) -> ProviderCommandResult:
        """Pure, mechanical 1:1 translation of a Supervisor-authoritative
        outcome. Never synthesizes a provider_execution_outcome string
        except by reading outcome.outcome.value directly."""

        command = outcome.command
        kind = outcome.outcome
        succeeded = kind is ProviderExecutionOutcome.SUCCEEDED
        if succeeded:
            legacy_error: str | None = None
        elif kind is ProviderExecutionOutcome.PROVIDER_REJECTED:
            legacy_error = outcome.provider_error_message
        elif kind is ProviderExecutionOutcome.PROVIDER_EXCEPTION:
            legacy_error = outcome.diagnostic_reason
        else:
            # TIMEOUT / WORKER_EXITED / PROTOCOL_ERROR / CANCELLED_SHUTDOWN /
            # CANCELLED_GENERATION_INVALIDATED -- fixed label, real detail
            # lives in diagnostic_reason (preserved separately, unaltered).
            legacy_error = kind.value

        return ProviderCommandResult(
            command_id=command.command_id,
            command_type=command.command_type,
            succeeded=succeeded,
            controller_generation=command.controller_generation,
            desired_registry_revision=command.desired_registry_revision,
            completed_at=self._now_utc(),
            error=legacy_error,
            raw_payload=outcome.normalized_provider_payload,
            worker_generation=outcome.worker_generation,
            provider_execution_outcome=kind.value,
            provider_error_code=outcome.provider_error_code,
            provider_error_message=outcome.provider_error_message,
            diagnostic_reason=outcome.diagnostic_reason,
        )

    # ---- delivery (fail-closed on sink failure) ---------------------------

    def _deliver(self, result: ProviderCommandResult) -> bool:
        """Delivers exactly once. Returns False (and marks this Adapter
        dead) if delivery itself fails -- the Supervisor's terminal ledger
        entry for this command is already authoritative and permanent
        regardless; this method never re-submits, replays, retries, or
        mints a replacement result on failure, it only records that
        delivery did not happen and stops the bridge."""

        sink = self._sink
        if sink is None:
            self._mark_dead()
            return False
        try:
            sink(result)
        except Exception:
            self._mark_dead()
            return False
        return True
