"""Provider Worker Supervisor V0.1 -- Slice B: process-isolated fake-child
supervisor runtime.

Reuses the Slice A frozen contracts (``provider_worker_contracts.py``)
verbatim: no enums, dataclasses, or config shape are redeclared here.
This module supplies the runtime machinery Slice A deliberately excluded:
``multiprocessing`` process launch, generation-local IPC, monotonic
deadlines, the hard-kill/death-confirmation sequence, first-terminal-wins
resolution, and shutdown/admission handling.

Scope (frozen, see task brief "STRICT NON-SCOPE"): a pure process-isolated
FAKE/STUB child supervisor only. No Futu/OpenD/provider SDK import
anywhere in this module or in the child target. No controller lifecycle
authority, no market/portfolio semantics, no Currentness/Continuity/
RecoveryCandidate, no AI/trading/notification behavior.

Ownership model (frozen): the parent-side ``ProviderWorkerSupervisor``
instance owns ALL authoritative state (worker generation, process handle,
in-flight command identity, command deadlines, terminal resolution,
replacement decision, shutdown/admission state, fatal state). The child
process owns none of this; it is a disposable, replaceable executor.
"""

from __future__ import annotations

import multiprocessing
import os
import queue as _queue_module
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Mapping

from .commands import ProviderCommand, ProviderCommandType
from .provider_worker_contracts import (
    ProviderExecutionOutcome,
    ProviderWorkerEvidenceKind,
    ProviderWorkerLifecycleEvidence,
    ProviderWorkerSupervisorConfig,
    ResolvedProviderCommandOutcome,
)
from .provider_worker_child_boundary import execute_fake_command_in_child

__all__ = [
    "AdmissionClosedError",
    "CommandInFlightError",
    "ProviderWorkerSupervisor",
    "SupervisorFatalError",
    "SupervisorState",
]

CHILD_REPORTABLE_TERMINAL_SET = frozenset(
    {
        ProviderExecutionOutcome.SUCCEEDED,
        ProviderExecutionOutcome.PROVIDER_REJECTED,
        ProviderExecutionOutcome.PROVIDER_EXCEPTION,
    }
)


# ---------------------------------------------------------------------------
# Supervisor-level (not Slice A) exceptions and state.
# ---------------------------------------------------------------------------


class SupervisorFatalError(RuntimeError):
    """Raised when an operation is attempted while the supervisor is FATAL
    (a kill could not be confirmed). No replacement generation may ever be
    created after this; the supervisor is permanently unusable."""


class AdmissionClosedError(RuntimeError):
    """Raised by submit_command() once shutdown has begun."""


class CommandInFlightError(RuntimeError):
    """Raised if a caller submits a second command while one is still
    in flight for the current generation (one-RUNNING-command-max rule)."""


class SupervisorState(str, Enum):
    CREATED = "CREATED"
    RUNNING = "RUNNING"
    SHUTDOWN = "SHUTDOWN"
    FATAL = "FATAL"


# ---------------------------------------------------------------------------
# Fake/stub child process target. Spawn-safe: module-level, no closures over
# unpicklable state, no Futu/OpenD/provider SDK import anywhere below.
# ---------------------------------------------------------------------------


def _fake_child_main(
    command_queue: "multiprocessing.Queue",
    result_queue: "multiprocessing.Queue",
    release_event: "multiprocessing.synchronize.Event",
    boot_mode: str,
    runtime_instance_id: str,
    provider_id: str,
    worker_generation: int,
) -> None:
    """Deterministic fake provider child. NOT a production provider
    integration -- test/harness double only, per Slice B scope.

    boot_mode controls startup behavior:
      "ready"          -> announce WORKER_RUNTIME_READY immediately
      "hang"           -> never announce readiness (blocks on release_event
                          forever unless the test sets it)
      "init_failed"    -> announce WORKER_INIT_FAILED and exit
      "exit_immediately" -> exit before announcing anything

    Each command dict on command_queue carries payload["behavior"], which
    selects one of the deterministic response modes below.
    """

    def _now_utc_iso() -> str:
        return datetime.now(timezone.utc).isoformat()

    if boot_mode == "exit_immediately":
        os._exit(7)

    if boot_mode == "init_failed":
        result_queue.put(
            {
                "frame_kind": "LIFECYCLE",
                "kind": ProviderWorkerEvidenceKind.WORKER_INIT_FAILED.value,
                "worker_generation": worker_generation,
                "observed_at_monotonic_ns": time.monotonic_ns(),
                "observed_at_utc": _now_utc_iso(),
                "pid": os.getpid(),
                "diagnostic_reason": "simulated init failure",
            }
        )
        os._exit(1)

    if boot_mode == "hang":
        # Deliberately never announces readiness. Only unblocks if a test
        # sets release_event (used by teardown-of-hung-child tests), and
        # even then only exits -- it still never claims READY.
        release_event.wait()
        os._exit(9)

    # boot_mode == "ready" (default path)
    result_queue.put(
        {
            "frame_kind": "LIFECYCLE",
            "kind": ProviderWorkerEvidenceKind.WORKER_RUNTIME_READY.value,
            "worker_generation": worker_generation,
            "observed_at_monotonic_ns": time.monotonic_ns(),
            "observed_at_utc": _now_utc_iso(),
            "pid": os.getpid(),
            "diagnostic_reason": None,
        }
    )

    while True:
        try:
            command = command_queue.get(timeout=3600)
        except _queue_module.Empty:
            continue
        if command is None:
            # Cooperative stop signal (graceful shutdown path only; the
            # parent NEVER relies on this alone for hard-kill semantics).
            os._exit(0)

        # PBLC-S1: all fake execution crosses this single provider-neutral
        # child-only seam.
        execute_fake_command_in_child(
            command,
            result_queue=result_queue,
            release_event=release_event,
            worker_generation=worker_generation,
        )

# ---------------------------------------------------------------------------
# Internal per-generation bookkeeping (parent-owned, never authoritative on
# the child side).
# ---------------------------------------------------------------------------


@dataclass
class _Generation:
    number: int
    process: "multiprocessing.Process"
    command_queue: "multiprocessing.Queue"
    result_queue: "multiprocessing.Queue"
    release_event: "multiprocessing.synchronize.Event"
    ready: bool = False
    dead: bool = False
    invalid: bool = False


# ---------------------------------------------------------------------------
# Parent-side supervisor: the sole authority.
# ---------------------------------------------------------------------------


class ProviderWorkerSupervisor:
    """Owns one worker-process generation at a time.

    NOT thread-safe for concurrent submit_command() calls by design (one
    RUNNING synchronous command maximum per generation is enforced, not
    merely documented). shutdown() may be called concurrently with an
    in-flight submit_command() from another thread; the admission lock
    makes that race deterministic (see shutdown()).
    """

    def __init__(
        self,
        *,
        runtime_instance_id: str,
        provider_id: str,
        config: ProviderWorkerSupervisorConfig,
        child_target: Callable[..., None] | None = None,
    ) -> None:
        if not isinstance(config, ProviderWorkerSupervisorConfig):
            raise ValueError("config must be a ProviderWorkerSupervisorConfig")
        self._runtime_instance_id = runtime_instance_id
        self._provider_id = provider_id
        self._config = config
        # Scope guard: only ever the fake/stub target may be substituted,
        # and only for internal test composition -- never a real provider
        # SDK entrypoint. Production callers must not pass child_target.
        self._child_target = child_target or _fake_child_main
        self._ctx = multiprocessing.get_context("spawn")

        self._admission_lock = threading.RLock()
        self._state_lock = threading.RLock()
        self._state = SupervisorState.CREATED
        self._shutdown_event = threading.Event()
        self._generation_seq = 0
        self._current: _Generation | None = None
        self._in_flight_command_id: str | None = None
        self._evidence_log: list[ProviderWorkerLifecycleEvidence] = []
        self._terminal_ledger: dict[str, tuple[tuple[Any, ...], ResolvedProviderCommandOutcome]] = {}

    # -- introspection -----------------------------------------------------

    @property
    def state(self) -> SupervisorState:
        return self._state

    @property
    def worker_generation(self) -> int | None:
        return self._current.number if self._current is not None else None

    @property
    def evidence_log(self) -> tuple[ProviderWorkerLifecycleEvidence, ...]:
        return tuple(self._evidence_log)

    @property
    def owned_process_pid(self) -> int | None:
        if self._current is not None and self._current.process.pid:
            return self._current.process.pid
        return None

    # -- generation lifecycle ------------------------------------------

    def start_generation(self) -> ProviderWorkerLifecycleEvidence:
        """Spawn a fresh worker generation with fresh, disposable IPC and
        wait (bounded by startup_timeout_seconds) for readiness."""
        if self._state is SupervisorState.FATAL:
            raise SupervisorFatalError("cannot start a generation: supervisor is FATAL")
        if self._state is SupervisorState.SHUTDOWN or self._shutdown_event.is_set():
            raise AdmissionClosedError("cannot start a generation: supervisor shutdown is terminal")
        if self._current is not None and not self._current.dead:
            raise RuntimeError("a live generation already exists; shutdown or replace it first")

        self._generation_seq += 1
        generation_number = self._generation_seq
        command_queue = self._ctx.Queue(maxsize=self._config.parent_command_queue_capacity)
        result_queue = self._ctx.Queue(maxsize=self._config.supervisor_inbox_capacity)
        release_event = self._ctx.Event()

        return self._start_generation_with_boot_mode(
            generation_number, command_queue, result_queue, release_event, boot_mode="ready"
        )

    def _start_generation_with_boot_mode(
        self,
        generation_number: int,
        command_queue,
        result_queue,
        release_event,
        *,
        boot_mode: str,
    ) -> ProviderWorkerLifecycleEvidence:
        process = self._ctx.Process(
            target=self._child_target,
            args=(
                command_queue,
                result_queue,
                release_event,
                boot_mode,
                self._runtime_instance_id,
                self._provider_id,
                generation_number,
            ),
            daemon=True,
        )
        generation = _Generation(
            number=generation_number,
            process=process,
            command_queue=command_queue,
            result_queue=result_queue,
            release_event=release_event,
        )
        self._current = generation
        self._in_flight_command_id = None

        started_at_monotonic_ns = time.monotonic_ns()
        process.start()
        deadline_ns = started_at_monotonic_ns + int(
            self._config.startup_timeout_seconds * 1_000_000_000
        )

        evidence = self._await_startup(generation, deadline_ns)
        self._record_evidence(evidence)
        return evidence

    def _await_startup(self, generation: _Generation, deadline_ns: int) -> ProviderWorkerLifecycleEvidence:
        while True:
            remaining_ns = deadline_ns - time.monotonic_ns()
            if remaining_ns <= 0:
                return self._handle_startup_timeout(generation)

            if not generation.process.is_alive():
                exit_code = generation.process.exitcode
                self._hard_kill(generation)
                return ProviderWorkerLifecycleEvidence(
                    runtime_instance_id=self._runtime_instance_id,
                    provider_id=self._provider_id,
                    worker_generation=generation.number,
                    kind=ProviderWorkerEvidenceKind.WORKER_EXITED,
                    observed_at_monotonic_ns=time.monotonic_ns(),
                    observed_at_utc=datetime.now(timezone.utc),
                    process_pid=generation.process.pid,
                    exit_code=exit_code,
                    diagnostic_reason="child exited before announcing readiness",
                )

            poll_timeout_s = min(0.05, max(remaining_ns, 0) / 1_000_000_000)
            try:
                frame = generation.result_queue.get(timeout=poll_timeout_s)
            except _queue_module.Empty:
                continue

            if not self._is_wire_safe(frame):
                return self._handle_protocol_failure(generation, frame)

            if frame.get("frame_kind") == "LIFECYCLE" and frame.get("kind") == ProviderWorkerEvidenceKind.WORKER_RUNTIME_READY.value:
                if frame.get("worker_generation") != generation.number:
                    return self._handle_protocol_failure(generation, frame)
                generation.ready = True
                self._state = SupervisorState.RUNNING
                return ProviderWorkerLifecycleEvidence(
                    runtime_instance_id=self._runtime_instance_id,
                    provider_id=self._provider_id,
                    worker_generation=generation.number,
                    kind=ProviderWorkerEvidenceKind.WORKER_RUNTIME_READY,
                    observed_at_monotonic_ns=time.monotonic_ns(),
                    observed_at_utc=datetime.now(timezone.utc),
                    process_pid=generation.process.pid,
                    exit_code=None,
                    diagnostic_reason=None,
                )

            if frame.get("frame_kind") == "LIFECYCLE" and frame.get("kind") == ProviderWorkerEvidenceKind.WORKER_INIT_FAILED.value:
                if frame.get("worker_generation") != generation.number:
                    return self._handle_protocol_failure(generation, frame)
                death_confirmed = self._hard_kill(generation)
                if not death_confirmed:
                    self._state = SupervisorState.FATAL
                    kind = ProviderWorkerEvidenceKind.WORKER_KILL_FAILED
                    reason = "worker init failed; child death could not be confirmed"
                else:
                    kind = ProviderWorkerEvidenceKind.WORKER_INIT_FAILED
                    reason = frame.get("diagnostic_reason")
                return ProviderWorkerLifecycleEvidence(
                    runtime_instance_id=self._runtime_instance_id,
                    provider_id=self._provider_id,
                    worker_generation=generation.number,
                    kind=kind,
                    observed_at_monotonic_ns=time.monotonic_ns(),
                    observed_at_utc=datetime.now(timezone.utc),
                    process_pid=generation.process.pid,
                    exit_code=generation.process.exitcode,
                    diagnostic_reason=reason,
                )
            # Anything else during startup is ignored as noise, not
            # authoritative (defensive only; the fake child never emits
            # extra frames pre-READY).
            if frame.get("frame_kind") == "LIFECYCLE":
                return self._handle_protocol_failure(generation, frame)

    def _handle_startup_timeout(self, generation: _Generation) -> ProviderWorkerLifecycleEvidence:
        death_confirmed = self._hard_kill(generation)
        if not death_confirmed:
            self._state = SupervisorState.FATAL
            return ProviderWorkerLifecycleEvidence(
                runtime_instance_id=self._runtime_instance_id,
                provider_id=self._provider_id,
                worker_generation=generation.number,
                kind=ProviderWorkerEvidenceKind.WORKER_KILL_FAILED,
                observed_at_monotonic_ns=time.monotonic_ns(),
                observed_at_utc=datetime.now(timezone.utc),
                process_pid=generation.process.pid,
                exit_code=None,
                diagnostic_reason="startup timeout; child death could not be confirmed",
            )
        return ProviderWorkerLifecycleEvidence(
            runtime_instance_id=self._runtime_instance_id,
            provider_id=self._provider_id,
            worker_generation=generation.number,
            kind=ProviderWorkerEvidenceKind.WORKER_STARTUP_TIMEOUT,
            observed_at_monotonic_ns=time.monotonic_ns(),
            observed_at_utc=datetime.now(timezone.utc),
            process_pid=generation.process.pid,
            exit_code=generation.process.exitcode,
            diagnostic_reason="startup deadline exceeded; child terminated and death confirmed",
        )

    # -- wire safety --------------------------------------------------------

    _REQUIRED_FRAME_FIELDS = {
        "LIFECYCLE": {"kind", "worker_generation", "observed_at_monotonic_ns", "observed_at_utc"},
        "COMMAND_RESULT": {
            "command_id",
            "worker_generation",
            "outcome",
            "terminal_observed_at_monotonic_ns",
            "terminal_at_utc",
        },
    }

    def _is_wire_safe(self, frame: Any) -> bool:
        if not isinstance(frame, dict):
            return False
        frame_kind = frame.get("frame_kind")
        if frame_kind not in self._REQUIRED_FRAME_FIELDS:
            return False
        required = self._REQUIRED_FRAME_FIELDS[frame_kind]
        if not required.issubset(frame.keys()):
            return False
        try:
            import json

            encoded = json.dumps(frame)
        except Exception:
            return False
        return len(encoded.encode("utf-8")) <= self._config.max_frame_bytes

    def _handle_protocol_failure(self, generation: _Generation, frame: Any) -> ProviderWorkerLifecycleEvidence:
        if not self._hard_kill(generation):
            self._state = SupervisorState.FATAL
            kind = ProviderWorkerEvidenceKind.WORKER_KILL_FAILED
            reason = "protocol failure; child death could not be confirmed"
        else:
            kind = ProviderWorkerEvidenceKind.WORKER_PROTOCOL_FATAL
            reason = "malformed or oversized frame received from child"
        return ProviderWorkerLifecycleEvidence(
            runtime_instance_id=self._runtime_instance_id,
            provider_id=self._provider_id,
            worker_generation=generation.number,
            kind=kind,
            observed_at_monotonic_ns=time.monotonic_ns(),
            observed_at_utc=datetime.now(timezone.utc),
            process_pid=generation.process.pid,
            exit_code=None,
            diagnostic_reason=reason,
        )

    # -- hard kill / death confirmation --------------------------------

    def _hard_kill(self, generation: _Generation) -> bool:
        """Terminate, escalate to kill if needed, and positively confirm
        death. Returns True iff death was confirmed."""
        if not generation.process.is_alive():
            generation.dead = True
            generation.invalid = True
            self._dispose_ipc(generation)
            return True

        generation.process.terminate()
        generation.process.join(self._config.terminate_join_timeout_seconds)
        if self._confirm_process_death(generation):
            generation.dead = True
            generation.invalid = True
            self._dispose_ipc(generation)
            return True

        generation.process.kill()
        generation.process.join(self._config.kill_join_timeout_seconds)
        if self._confirm_process_death(generation):
            generation.dead = True
            generation.invalid = True
            self._dispose_ipc(generation)
            return True

        return False

    @staticmethod
    def _dispose_ipc(generation: _Generation) -> None:
        for channel in (generation.command_queue, generation.result_queue):
            close = getattr(channel, "close", None)
            if close is not None:
                try:
                    close()
                except (OSError, ValueError):
                    pass
                join_thread = getattr(channel, "join_thread", None)
                if join_thread is not None:
                    try:
                        join_thread()
                    except (OSError, ValueError, AssertionError):
                        pass

    def _confirm_process_death(self, generation: _Generation) -> bool:
        """Positive death confirmation seam. Overridable/monkeypatchable
        by tests to simulate an unconfirmable kill without needing to
        construct a genuinely unkillable process."""
        return not generation.process.is_alive()

    # -- command execution -----------------------------------------------

    def submit_command(
        self,
        command: ProviderCommand,
        *,
        payload: Mapping[str, Any] | None = None,
    ) -> ResolvedProviderCommandOutcome:
        if not isinstance(command, ProviderCommand):
            raise ValueError("command must be a ProviderCommand")

        identity = self._command_identity(command)
        with self._admission_lock:
            existing = self._terminal_ledger.get(command.command_id)
            if existing is not None:
                existing_identity, existing_outcome = existing
                if existing_identity != identity:
                    raise ValueError("command_id collision with different immutable command identity")
                return existing_outcome
            if self._state is SupervisorState.FATAL:
                raise SupervisorFatalError("supervisor is FATAL; no commands accepted")
            if self._state is SupervisorState.SHUTDOWN:
                raise AdmissionClosedError("admission closed: shutdown already requested")
            if self._current is None or self._current.dead:
                generation = self._current
                diagnostic_reason = (
                    "previously minted worker generation is no longer usable before dispatch"
                    if generation is not None
                    else "no worker generation has ever been established for dispatch"
                )
                outcome = self._finalize_command(
                    generation, command,
                    ProviderExecutionOutcome.CANCELLED_GENERATION_INVALIDATED,
                    None,
                    diagnostic_reason=diagnostic_reason,
                )
                self._terminal_ledger[command.command_id] = (identity, outcome)
                return outcome
            if self._in_flight_command_id is not None:
                raise CommandInFlightError(
                    f"command {self._in_flight_command_id!r} is still in flight "
                    "(one RUNNING command maximum per generation)"
                )
            self._in_flight_command_id = command.command_id
            generation = self._current

        self._before_dispatch()
        with self._admission_lock:
            if self._shutdown_event.is_set():
                outcome = self._finalize_command(
                    generation, command, ProviderExecutionOutcome.CANCELLED_SHUTDOWN,
                    None, diagnostic_reason="shutdown requested before dispatch",
                )
                self._terminal_ledger[command.command_id] = (identity, outcome)
                self._in_flight_command_id = None
                return outcome

        dispatched_at_monotonic_ns = time.monotonic_ns()
        wire_command = {
            "command_id": command.command_id,
            "command_type": command.command_type.value,
            "payload": dict(payload or {}),
        }
        timeout_seconds = self._config.command_timeout_seconds[command.command_type]
        try:
            generation.command_queue.put(wire_command, timeout=timeout_seconds)
        except (_queue_module.Full, OSError, ValueError):
            outcome = self._finalize_command(
                generation, command, ProviderExecutionOutcome.PROTOCOL_ERROR,
                None, diagnostic_reason="bounded command admission failed",
            )
            with self._admission_lock:
                self._terminal_ledger[command.command_id] = (identity, outcome)
                self._in_flight_command_id = None
            return outcome
        deadline_ns = dispatched_at_monotonic_ns + int(timeout_seconds * 1_000_000_000)

        outcome = self._await_command_resolution(
            generation, command, dispatched_at_monotonic_ns, deadline_ns
        )
        with self._admission_lock:
            self._terminal_ledger[command.command_id] = (identity, outcome)
            self._in_flight_command_id = None
        return outcome

    def _before_dispatch(self) -> None:
        """Deterministic seam for the admission/dispatch shutdown race."""

    @staticmethod
    def _command_identity(command: ProviderCommand) -> tuple[Any, ...]:
        return (
            command.command_id,
            command.command_type,
            command.controller_generation,
            command.desired_registry_revision,
            command.runtime_instance_id,
            command.provider_id,
            command.stream_subscription_epoch,
            command.semantic_stream_key,
        )

    def _await_command_resolution(
        self,
        generation: _Generation,
        command: ProviderCommand,
        dispatched_at_monotonic_ns: int,
        deadline_ns: int,
    ) -> ResolvedProviderCommandOutcome:
        while True:
            remaining_ns = deadline_ns - time.monotonic_ns()
            if remaining_ns <= 0:
                death_confirmed = self._hard_kill(generation)
                if not death_confirmed:
                    self._state = SupervisorState.FATAL
                    raise SupervisorFatalError("command timeout escalation could not confirm child death")
                return self._finalize_command(generation, command, ProviderExecutionOutcome.TIMEOUT,
                    dispatched_at_monotonic_ns, diagnostic_reason="command deadline exceeded")
            # Parent deadline is authoritative; inspect frames only while valid.
            poll_timeout_s = min(0.02, max(remaining_ns, 0) / 1_000_000_000) if remaining_ns > 0 else 0.0
            try:
                frame = generation.result_queue.get(timeout=poll_timeout_s)
            except _queue_module.Empty:
                frame = None

            if frame is not None:
                resolved = self._resolve_from_frame(generation, command, frame, dispatched_at_monotonic_ns)
                if resolved is not None:
                    return resolved
                # frame belonged to a different/unknown command_id or was
                # not a COMMAND_RESULT -- keep waiting for the real one,
                # but still bounded by the same deadline.

            # 2) Shutdown requested concurrently: a subsequent kill of this
            #    generation must resolve as CANCELLED_SHUTDOWN, never be
            #    mislabeled as an unexpected WORKER_EXITED.
            if self._shutdown_event.is_set():
                return self._finalize_command(
                    generation,
                    command,
                    ProviderExecutionOutcome.CANCELLED_SHUTDOWN,
                    dispatched_at_monotonic_ns,
                    diagnostic_reason="shutdown requested while command was in flight",
                )

            # 3) Unexpected process exit (not one we killed ourselves).
            if not generation.process.is_alive():
                self._hard_kill(generation)
                return self._finalize_command(
                    generation,
                    command,
                    ProviderExecutionOutcome.WORKER_EXITED,
                    dispatched_at_monotonic_ns,
                    diagnostic_reason=f"child exited unexpectedly (code={generation.process.exitcode})",
                )


    def _resolve_from_frame(
        self,
        generation: _Generation,
        command: ProviderCommand,
        frame: Any,
        dispatched_at_monotonic_ns: int,
    ) -> ResolvedProviderCommandOutcome | None:
        if not self._is_wire_safe(frame):
            evidence = self._handle_protocol_failure(generation, frame)
            self._record_evidence(evidence)
            return self._finalize_command(
                generation,
                command,
                ProviderExecutionOutcome.PROTOCOL_ERROR,
                dispatched_at_monotonic_ns,
                diagnostic_reason="malformed or oversized frame from child",
            )

        if frame.get("frame_kind") != "COMMAND_RESULT":
            return None
        if frame.get("command_id") != command.command_id:
            # Not this command's result. Under Slice B's generation-local,
            # single-in-flight-command IPC this should not occur from the
            # current generation, but defensively it is never applied.
            return None
        if frame.get("worker_generation") != generation.number:
            # Cannot physically happen (fresh queues per generation), but
            # kept as a defense-in-depth identity check.
            return None

        try:
            outcome = ProviderExecutionOutcome(frame["outcome"])
        except (KeyError, ValueError, TypeError):
            evidence = self._handle_protocol_failure(generation, frame)
            self._record_evidence(evidence)
            return self._finalize_command(generation, command, ProviderExecutionOutcome.PROTOCOL_ERROR,
                dispatched_at_monotonic_ns, diagnostic_reason="invalid command outcome")
        if outcome not in CHILD_REPORTABLE_TERMINAL_SET:
            evidence = self._handle_protocol_failure(generation, frame)
            self._record_evidence(evidence)
            return self._finalize_command(generation, command, ProviderExecutionOutcome.PROTOCOL_ERROR,
                dispatched_at_monotonic_ns, diagnostic_reason="child reported supervisor-owned terminal")
        resolved = self._finalize_command(
            generation,
            command,
            outcome,
            dispatched_at_monotonic_ns,
            provider_error_code=frame.get("provider_error_code"),
            provider_error_message=frame.get("provider_error_message"),
            normalized_provider_payload=frame.get("normalized_provider_payload"),
            diagnostic_reason=frame.get("diagnostic_reason"),
        )
        if outcome is ProviderExecutionOutcome.PROVIDER_EXCEPTION:
            if not self._hard_kill(generation):
                self._state = SupervisorState.FATAL
            else:
                generation.invalid = True
        return resolved

    def _finalize_command(
        self,
        generation: _Generation | None,
        command: ProviderCommand,
        outcome: ProviderExecutionOutcome,
        dispatched_at_monotonic_ns: int,
        *,
        provider_error_code: str | None = None,
        provider_error_message: str | None = None,
        normalized_provider_payload: Mapping[str, Any] | None = None,
        diagnostic_reason: str | None = None,
    ) -> ResolvedProviderCommandOutcome:
        """Build the authoritative ResolvedProviderCommandOutcome for one
        command. First-terminal-wins is a property of the CALLER
        (_await_command_resolution): it checks frame-arrival, then
        unexpected process exit, then deadline, in that fixed order each
        iteration, and returns immediately on the first branch that
        resolves -- so exactly one call to this method ever happens per
        submit_command() invocation. There is no separate "already
        resolved" state to defend against here: the ordering itself, not
        a second bookkeeping layer, is what makes the outcome
        deterministic under a race."""
        return ResolvedProviderCommandOutcome(
            runtime_instance_id=self._runtime_instance_id,
            provider_id=self._provider_id,
            worker_generation=generation.number if generation is not None else None,
            command=command,
            outcome=outcome,
            dispatched_at_monotonic_ns=dispatched_at_monotonic_ns,
            terminal_observed_at_monotonic_ns=time.monotonic_ns(),
            terminal_at_utc=datetime.now(timezone.utc),
            provider_error_code=provider_error_code,
            provider_error_message=provider_error_message,
            normalized_provider_payload=normalized_provider_payload,
            diagnostic_reason=diagnostic_reason,
        )

    def _record_evidence(self, evidence: ProviderWorkerLifecycleEvidence) -> None:
        self._evidence_log.append(evidence)

    # -- shutdown -----------------------------------------------------------

    def shutdown(self) -> None:
        """Close admission, terminalize any command still admitted (in
        flight) as CANCELLED_SHUTDOWN, and tear down the owned child with
        no orphan left behind. Idempotent."""
        with self._admission_lock:
            already_shutdown = self._state in (SupervisorState.SHUTDOWN, SupervisorState.FATAL)
            if not already_shutdown:
                self._state = SupervisorState.SHUTDOWN
            # Set BEFORE releasing the lock and BEFORE killing, so any
            # thread concurrently polling in _await_command_resolution
            # observes "shutdown requested" ahead of noticing the process
            # died -- this is what makes an in-flight command resolve as
            # CANCELLED_SHUTDOWN instead of a mislabeled WORKER_EXITED.
            self._shutdown_event.set()

        if already_shutdown:
            return

        generation = self._current
        if generation is None or generation.dead:
            return

        shutdown_deadline_ns = time.monotonic_ns() + int(
            self._config.graceful_shutdown_timeout_seconds * 1_000_000_000
        )
        try:
            generation.command_queue.put(None, timeout=self._config.graceful_shutdown_timeout_seconds)
        except (_queue_module.Full, OSError, ValueError):
            pass
        while generation.process.is_alive() and time.monotonic_ns() < shutdown_deadline_ns:
            remaining_ns = shutdown_deadline_ns - time.monotonic_ns()
            generation.process.join(min(0.02, remaining_ns / 1_000_000_000))

        if not self._hard_kill(generation):
            self._state = SupervisorState.FATAL

    def replace_generation(self) -> ProviderWorkerLifecycleEvidence:
        """Create a fresh generation after the current one is confirmed
        dead. Never replays the prior generation's in-flight command."""
        if self._state is SupervisorState.FATAL:
            raise SupervisorFatalError("cannot replace: supervisor is FATAL")
        if self._state is SupervisorState.SHUTDOWN or self._shutdown_event.is_set():
            raise AdmissionClosedError("cannot replace: supervisor shutdown is terminal")
        if self._current is not None and not self._current.dead:
            raise RuntimeError("current generation is not confirmed dead; cannot replace yet")
        self._state = SupervisorState.CREATED
        return self.start_generation()
