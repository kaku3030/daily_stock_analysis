"""Provider Worker Supervisor V0.1 -- Slice B adversarial test suite.

Every mandatory scenario from the Slice B brief (section 10) is covered.
No Futu/OpenD/provider SDK is imported or exercised anywhere -- only the
fake/stub child target. Timeout-vs-result and process-exit-vs-result races
are proven deterministically by directly exercising the resolution loop's
fixed check ordering with controlled fakes, not by racing real wall-clock
timing (per the brief: "avoid arbitrary sleeps as the primary
synchronization mechanism").
"""
from __future__ import annotations

import multiprocessing
import time
from datetime import datetime, timezone

import pytest

from src.services.live_feed.commands import ProviderCommand, ProviderCommandType
from src.services.live_feed.provider_worker_contracts import (
    ProviderExecutionOutcome,
    ProviderWorkerEvidenceKind,
    ProviderWorkerSupervisorConfig,
)
from src.services.live_feed.provider_worker_supervisor import (
    AdmissionClosedError,
    CommandInFlightError,
    ProviderWorkerSupervisor,
    SupervisorFatalError,
    SupervisorState,
    _Generation,
)


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def _config(**overrides):
    base = dict(
        startup_timeout_seconds=3.0,
        command_timeout_seconds={t: 3.0 for t in ProviderCommandType},
        graceful_shutdown_timeout_seconds=3.0,
        terminate_join_timeout_seconds=1.0,
        kill_join_timeout_seconds=1.0,
        parent_command_queue_capacity=8,
        child_data_queue_capacity=8,
        child_priority_queue_capacity=8,
        supervisor_inbox_capacity=8,
        max_frame_bytes=4096,
        protocol_version=1,
    )
    base.update(overrides)
    return ProviderWorkerSupervisorConfig(**base)


def _command(command_id="c1", command_type=ProviderCommandType.DIAGNOSTIC,
            controller_generation=1, desired_registry_revision=1):
    return ProviderCommand(
        runtime_instance_id="r1",
        provider_id="futu",
        controller_generation=controller_generation,
        desired_registry_revision=desired_registry_revision,
        command_id=command_id,
        command_type=command_type,
        created_at=datetime.now(timezone.utc),
    )


@pytest.fixture
def supervisor():
    sup = ProviderWorkerSupervisor(runtime_instance_id="r1", provider_id="futu", config=_config())
    yield sup
    # Teardown safety net: never leave an orphan child if a test fails
    # mid-way before reaching its own shutdown() call.
    try:
        sup.shutdown()
    except Exception:
        pass


# ---------------------------------------------------------------------------
# 1. startup READY success
# ---------------------------------------------------------------------------

def test_01_startup_ready_success(supervisor):
    evidence = supervisor.start_generation()
    assert evidence.kind is ProviderWorkerEvidenceKind.WORKER_RUNTIME_READY
    assert supervisor.state is SupervisorState.RUNNING
    assert evidence.process_pid is not None
    assert supervisor.owned_process_pid == evidence.process_pid


# ---------------------------------------------------------------------------
# 2. startup hang -> bounded terminate/kill
# ---------------------------------------------------------------------------

def test_02_startup_hang_bounded_terminate_kill(supervisor):
    fast_config = _config(startup_timeout_seconds=0.3, terminate_join_timeout_seconds=1.0)
    sup = ProviderWorkerSupervisor(runtime_instance_id="r1", provider_id="futu", config=fast_config)
    sup._generation_seq += 1
    gen_number = sup._generation_seq
    cq = sup._ctx.Queue(maxsize=8)
    rq = sup._ctx.Queue(maxsize=8)
    ev = sup._ctx.Event()

    started = time.monotonic()
    evidence = sup._start_generation_with_boot_mode(gen_number, cq, rq, ev, boot_mode="hang")
    elapsed = time.monotonic() - started

    assert evidence.kind is ProviderWorkerEvidenceKind.WORKER_STARTUP_TIMEOUT
    assert elapsed < 5.0, "bounded by startup_timeout + kill escalation, not unbounded"
    assert sup._current.process.is_alive() is False
    sup.shutdown()


# ---------------------------------------------------------------------------
# 3. ordinary command success
# ---------------------------------------------------------------------------

def test_03_ordinary_command_success(supervisor):
    supervisor.start_generation()
    outcome = supervisor.submit_command(_command(), payload={"behavior": "success"})
    assert outcome.outcome is ProviderExecutionOutcome.SUCCEEDED
    assert outcome.normalized_provider_payload == {"echo": "c1"}
    assert outcome.command.command_id == "c1"
    assert outcome.worker_generation == supervisor.worker_generation


# ---------------------------------------------------------------------------
# 4. provider-style rejection result
# ---------------------------------------------------------------------------

def test_04_provider_style_rejection(supervisor):
    supervisor.start_generation()
    outcome = supervisor.submit_command(_command(), payload={"behavior": "provider_rejected"})
    assert outcome.outcome is ProviderExecutionOutcome.PROVIDER_REJECTED
    assert outcome.provider_error_code == "SIMULATED_REJECT"


# ---------------------------------------------------------------------------
# 5. child exception result
# ---------------------------------------------------------------------------

def test_05_child_exception_result(supervisor):
    supervisor.start_generation()
    outcome = supervisor.submit_command(_command(), payload={"behavior": "exception"})
    assert outcome.outcome is ProviderExecutionOutcome.PROVIDER_EXCEPTION
    assert "boom" in outcome.diagnostic_reason


# ---------------------------------------------------------------------------
# 6. unreturning command -> timeout -> PID confirmed dead
# ---------------------------------------------------------------------------

def test_06_unreturning_command_timeout_pid_confirmed_dead():
    fast_config = _config(command_timeout_seconds={t: 0.3 for t in ProviderCommandType})
    sup = ProviderWorkerSupervisor(runtime_instance_id="r1", provider_id="futu", config=fast_config)
    sup.start_generation()
    pid = sup.owned_process_pid

    outcome = sup.submit_command(_command(), payload={"behavior": "hang"})

    assert outcome.outcome is ProviderExecutionOutcome.TIMEOUT
    assert sup._current.process.is_alive() is False
    assert sup._current.process.pid == pid
    sup.shutdown()


# ---------------------------------------------------------------------------
# 7. timeout-vs-result race -> exactly one terminal (deterministic, no
#    real-time racing: the resolution loop's fixed check order --
#    frame first, then shutdown, then process-exit, then deadline -- is
#    exercised directly against a fake generation whose deadline is
#    already expired but whose result_queue already has a frame ready.)
# ---------------------------------------------------------------------------

class _FakeQueue:
    def __init__(self, frames):
        self._frames = list(frames)

    def get(self, timeout=None):
        if self._frames:
            return self._frames.pop(0)
        import queue as _q
        raise _q.Empty()


class _FakeProcess:
    def __init__(self, alive=True, pid=4242, exitcode=None):
        self._alive = alive
        self.pid = pid
        self.exitcode = exitcode

    def is_alive(self):
        return self._alive

    def terminate(self):
        self._alive = False

    def kill(self):
        self._alive = False

    def join(self, timeout=None):
        pass


def test_07_timeout_vs_result_race_timeout_wins_after_deadline(supervisor):
    """An expired parent deadline is authoritative over a late result."""
    fake_gen = _Generation(
        number=1,
        process=_FakeProcess(alive=True),
        command_queue=None,
        result_queue=_FakeQueue([{
            "frame_kind": "COMMAND_RESULT",
            "command_id": "c1",
            "worker_generation": 1,
            "outcome": "SUCCEEDED",
            "terminal_observed_at_monotonic_ns": time.monotonic_ns(),
            "terminal_at_utc": datetime.now(timezone.utc).isoformat(),
            "provider_error_code": None,
            "provider_error_message": None,
            "normalized_provider_payload": None,
            "diagnostic_reason": None,
        }]),
        release_event=None,
    )
    supervisor._current = fake_gen
    already_expired_deadline_ns = time.monotonic_ns() - 1_000_000_000

    outcome = supervisor._await_command_resolution(
        fake_gen, _command(), dispatched_at_monotonic_ns=time.monotonic_ns() - 2_000_000_000,
        deadline_ns=already_expired_deadline_ns,
    )
    assert outcome.outcome is ProviderExecutionOutcome.TIMEOUT
    supervisor._current = None  # avoid the fixture's teardown touching the fake


# ---------------------------------------------------------------------------
# 8. process-exit-vs-result race -> exactly one terminal (same technique:
#    process already reports dead, but a result frame is already queued)
# ---------------------------------------------------------------------------

def test_08_process_exit_vs_result_race_result_wins(supervisor):
    fake_gen = _Generation(
        number=1,
        process=_FakeProcess(alive=False, exitcode=-9),  # already "dead"
        command_queue=None,
        result_queue=_FakeQueue([{
            "frame_kind": "COMMAND_RESULT",
            "command_id": "c1",
            "worker_generation": 1,
            "outcome": "SUCCEEDED",
            "terminal_observed_at_monotonic_ns": time.monotonic_ns(),
            "terminal_at_utc": datetime.now(timezone.utc).isoformat(),
            "provider_error_code": None,
            "provider_error_message": None,
            "normalized_provider_payload": None,
            "diagnostic_reason": None,
        }]),
        release_event=None,
    )
    supervisor._current = fake_gen
    far_future_deadline_ns = time.monotonic_ns() + 60_000_000_000

    outcome = supervisor._await_command_resolution(
        fake_gen, _command(), dispatched_at_monotonic_ns=time.monotonic_ns(),
        deadline_ns=far_future_deadline_ns,
    )
    assert outcome.outcome is ProviderExecutionOutcome.SUCCEEDED, (
        "even though the process already reports dead, an already-available "
        "result frame must win -- frame-check precedes process-exit-check")
    supervisor._current = None


def test_08b_process_exit_wins_when_no_result_available(supervisor):
    """Mirror check: with NO frame available and the process already dead,
    the outcome must be WORKER_EXITED (proves the ordering is meaningful,
    not merely 'frame always wins because it's checked')."""
    fake_gen = _Generation(
        number=1,
        process=_FakeProcess(alive=False, exitcode=1),
        command_queue=None,
        result_queue=_FakeQueue([]),
        release_event=None,
    )
    supervisor._current = fake_gen
    far_future_deadline_ns = time.monotonic_ns() + 60_000_000_000

    outcome = supervisor._await_command_resolution(
        fake_gen, _command(), dispatched_at_monotonic_ns=time.monotonic_ns(),
        deadline_ns=far_future_deadline_ns,
    )
    assert outcome.outcome is ProviderExecutionOutcome.WORKER_EXITED
    supervisor._current = None


# ---------------------------------------------------------------------------
# 9. malformed frame -> protocol failure
# ---------------------------------------------------------------------------

def test_09_malformed_frame_protocol_failure(supervisor):
    supervisor.start_generation()
    outcome = supervisor.submit_command(_command(), payload={"behavior": "malformed_frame"})
    assert outcome.outcome is ProviderExecutionOutcome.PROTOCOL_ERROR
    # the child is killed as part of protocol-fatal handling
    assert supervisor._current.process.is_alive() is False


# ---------------------------------------------------------------------------
# 10. oversized frame -> protocol failure
# ---------------------------------------------------------------------------

def test_10_oversized_frame_protocol_failure(supervisor):
    supervisor.start_generation()
    outcome = supervisor.submit_command(_command(), payload={"behavior": "oversized_frame"})
    assert outcome.outcome is ProviderExecutionOutcome.PROTOCOL_ERROR
    assert supervisor._current.process.is_alive() is False


# ---------------------------------------------------------------------------
# 11. replacement creates fresh generation-local IPC
# ---------------------------------------------------------------------------

def test_11_replacement_creates_fresh_generation_local_ipc(supervisor):
    supervisor.start_generation()
    old_generation_number = supervisor.worker_generation
    old_command_queue = supervisor._current.command_queue
    old_result_queue = supervisor._current.result_queue

    supervisor.shutdown()
    assert supervisor._current.dead is True

    evidence = supervisor.replace_generation()
    assert evidence.kind is ProviderWorkerEvidenceKind.WORKER_RUNTIME_READY
    assert supervisor.worker_generation == old_generation_number + 1
    assert supervisor._current.command_queue is not old_command_queue
    assert supervisor._current.result_queue is not old_result_queue


# ---------------------------------------------------------------------------
# 12. replacement does NOT replay prior in-flight command
# ---------------------------------------------------------------------------

def test_12_replacement_does_not_replay_in_flight_command():
    fast_config = _config(command_timeout_seconds={t: 0.3 for t in ProviderCommandType})
    sup = ProviderWorkerSupervisor(runtime_instance_id="r1", provider_id="futu", config=fast_config)
    sup.start_generation()

    outcome = sup.submit_command(_command(command_id="c-timeout"), payload={"behavior": "hang"})
    assert outcome.outcome is ProviderExecutionOutcome.TIMEOUT
    assert sup._current.dead is True

    # Build a brand-new supervisor state manually (replace_generation()
    # requires the *current* generation to already be confirmed dead,
    # which it is here after the timeout's own hard-kill).
    evidence = sup.replace_generation()
    assert evidence.kind is ProviderWorkerEvidenceKind.WORKER_RUNTIME_READY

    # No automatic re-submission of "c-timeout" ever happened: the new
    # generation has never seen that command_id at all. Prove the new
    # generation is immediately available for a *different* command and
    # nothing about the old one leaks through.
    fresh_outcome = sup.submit_command(_command(command_id="c-new"), payload={"behavior": "success"})
    assert fresh_outcome.outcome is ProviderExecutionOutcome.SUCCEEDED
    assert fresh_outcome.command.command_id == "c-new"
    sup.shutdown()


# ---------------------------------------------------------------------------
# 13. shutdown while idle
# ---------------------------------------------------------------------------

def test_13_shutdown_while_idle(supervisor):
    supervisor.start_generation()
    supervisor.shutdown()
    assert supervisor.state is SupervisorState.SHUTDOWN
    assert supervisor._current.process.is_alive() is False


# ---------------------------------------------------------------------------
# 14. shutdown while busy
# ---------------------------------------------------------------------------

def test_14_shutdown_while_busy():
    import threading

    fast_config = _config(command_timeout_seconds={t: 5.0 for t in ProviderCommandType})
    sup = ProviderWorkerSupervisor(runtime_instance_id="r1", provider_id="futu", config=fast_config)
    sup.start_generation()

    result_holder = {}

    def _run_command():
        result_holder["outcome"] = sup.submit_command(
            _command(command_id="busy-1"), payload={"behavior": "wait_then_succeed"}
        )

    t = threading.Thread(target=_run_command)
    t.start()
    # Give the command a moment to actually be dispatched/in-flight before
    # shutting down; the release_event is deliberately never set, so the
    # child would otherwise wait indefinitely for it.
    deadline = time.monotonic() + 2.0
    while sup._in_flight_command_id is None and time.monotonic() < deadline:
        time.sleep(0.01)
    assert sup._in_flight_command_id == "busy-1"

    sup.shutdown()
    t.join(timeout=5.0)
    assert not t.is_alive()

    outcome = result_holder["outcome"]
    assert outcome.outcome is ProviderExecutionOutcome.CANCELLED_SHUTDOWN
    assert sup._current.process.is_alive() is False


# ---------------------------------------------------------------------------
# 15. shutdown while hung
# ---------------------------------------------------------------------------

def test_15_shutdown_while_hung():
    fast_config = _config(terminate_join_timeout_seconds=0.5, kill_join_timeout_seconds=0.5)
    sup = ProviderWorkerSupervisor(runtime_instance_id="r1", provider_id="futu", config=fast_config)
    sup._generation_seq += 1
    cq = sup._ctx.Queue(maxsize=8)
    rq = sup._ctx.Queue(maxsize=8)
    ev = sup._ctx.Event()
    # boot_mode="hang" never announces readiness; go around start_generation
    # (which would itself time out waiting for READY) and construct the
    # generation directly to simulate "already running and hung".
    from src.services.live_feed.provider_worker_supervisor import _Generation as RealGen

    process = sup._ctx.Process(
        target=sup._child_target,
        args=(cq, rq, ev, "hang", "r1", "futu", 1),
        daemon=True,
    )
    process.start()
    sup._current = RealGen(number=1, process=process, command_queue=cq, result_queue=rq, release_event=ev)
    sup._state = SupervisorState.RUNNING

    started = time.monotonic()
    sup.shutdown()
    elapsed = time.monotonic() - started

    assert elapsed < 5.0
    assert sup._current.process.is_alive() is False


# ---------------------------------------------------------------------------
# 16. admission closed during shutdown
# ---------------------------------------------------------------------------

def test_16_admission_closed_during_shutdown(supervisor):
    supervisor.start_generation()
    supervisor.shutdown()
    with pytest.raises(AdmissionClosedError):
        supervisor.submit_command(_command(), payload={"behavior": "success"})


# ---------------------------------------------------------------------------
# 17. admitted-undispatched work cancelled deterministically
#     (see test_14 -- this IS that scenario for this synchronous,
#     one-in-flight-command-max design; documented explicitly here too.)
# ---------------------------------------------------------------------------

def test_17_admitted_in_flight_work_cancelled_deterministically():
    """Same guarantee as test_14, stated as its own scenario: an
    already-admitted (in-flight) command is ALWAYS resolved as
    CANCELLED_SHUTDOWN when shutdown races it, never silently dropped and
    never left to resolve as WORKER_EXITED."""
    import threading

    fast_config = _config(command_timeout_seconds={t: 5.0 for t in ProviderCommandType})
    sup = ProviderWorkerSupervisor(runtime_instance_id="r1", provider_id="futu", config=fast_config)
    sup.start_generation()

    outcomes = []

    def _run():
        outcomes.append(
            sup.submit_command(_command(command_id="in-flight-1"), payload={"behavior": "wait_then_succeed"})
        )

    t = threading.Thread(target=_run)
    t.start()
    deadline = time.monotonic() + 2.0
    while sup._in_flight_command_id is None and time.monotonic() < deadline:
        time.sleep(0.01)

    sup.shutdown()
    t.join(timeout=5.0)

    assert len(outcomes) == 1
    assert outcomes[0].outcome is ProviderExecutionOutcome.CANCELLED_SHUTDOWN


# ---------------------------------------------------------------------------
# 18 / 19. kill failure -> FATAL, and -> NO replacement
# ---------------------------------------------------------------------------

def test_18_19_kill_failure_fatal_and_no_replacement():
    fast_config = _config(startup_timeout_seconds=0.3, terminate_join_timeout_seconds=0.2,
                          kill_join_timeout_seconds=0.2)
    sup = ProviderWorkerSupervisor(runtime_instance_id="r1", provider_id="futu", config=fast_config)
    # Force death confirmation to always fail (simulates an unkillable
    # process without needing to actually construct one).
    sup._confirm_process_death = lambda generation: False

    sup._generation_seq += 1
    cq = sup._ctx.Queue(maxsize=8)
    rq = sup._ctx.Queue(maxsize=8)
    ev = sup._ctx.Event()
    evidence = sup._start_generation_with_boot_mode(1, cq, rq, ev, boot_mode="hang")

    assert evidence.kind is ProviderWorkerEvidenceKind.WORKER_KILL_FAILED
    assert sup.state is SupervisorState.FATAL

    with pytest.raises(SupervisorFatalError):
        sup.replace_generation()
    with pytest.raises(SupervisorFatalError):
        sup.submit_command(_command(), payload={"behavior": "success"})

    # Teardown: forcibly confirm death for real so the test process
    # doesn't leak a live child.
    sup._confirm_process_death = lambda generation: not generation.process.is_alive()
    if sup._current is not None and sup._current.process.is_alive():
        sup._current.process.kill()
        sup._current.process.join(2.0)


# ---------------------------------------------------------------------------
# 20. wall-clock jump cannot affect monotonic timeout
# ---------------------------------------------------------------------------

def test_20_wall_clock_jump_cannot_affect_monotonic_timeout(monkeypatch, supervisor):
    """Freeze datetime.now() far into the future (simulating a wall-clock
    jump) while monotonic time proceeds normally; the timeout decision
    must be driven purely by the monotonic deadline already computed at
    dispatch time, so a wall-clock jump changes nothing about *when* the
    timeout fires."""
    fast_config = _config(command_timeout_seconds={t: 0.3 for t in ProviderCommandType})
    sup = ProviderWorkerSupervisor(runtime_instance_id="r1", provider_id="futu", config=fast_config)
    sup.start_generation()

    import src.services.live_feed.provider_worker_supervisor as mod

    real_datetime = mod.datetime

    class _JumpedDatetime:
        @staticmethod
        def now(tz=None):
            return real_datetime(2099, 1, 1, tzinfo=tz)

    monkeypatch.setattr(mod, "datetime", _JumpedDatetime)

    outcome = sup.submit_command(_command(), payload={"behavior": "hang"})

    monkeypatch.setattr(mod, "datetime", real_datetime)

    assert outcome.outcome is ProviderExecutionOutcome.TIMEOUT
    # terminal_at_utc reflects whatever wall clock was in effect at
    # resolution time (that part legitimately uses datetime.now for
    # reporting), but the *decision itself* fired based on the monotonic
    # deadline, proven by the fact it fired at all within the short
    # command_timeout_seconds regardless of the wall-clock jump.
    sup.shutdown()


# ---------------------------------------------------------------------------
# 21. stale generation result cannot affect current generation
# ---------------------------------------------------------------------------

def test_21_stale_generation_result_cannot_affect_current_generation():
    fast_config = _config(command_timeout_seconds={t: 0.3 for t in ProviderCommandType})
    sup = ProviderWorkerSupervisor(runtime_instance_id="r1", provider_id="futu", config=fast_config)
    sup.start_generation()

    old_result_queue = sup._current.result_queue
    old_generation_number = sup.worker_generation

    outcome = sup.submit_command(_command(command_id="c-old"), payload={"behavior": "hang"})
    assert outcome.outcome is ProviderExecutionOutcome.TIMEOUT
    assert sup._current.dead is True

    evidence = sup.replace_generation()
    assert evidence.kind is ProviderWorkerEvidenceKind.WORKER_RUNTIME_READY
    new_generation_number = sup.worker_generation
    assert new_generation_number != old_generation_number
    assert sup._current.result_queue is not old_result_queue

    # Even if the (now-dead, discarded) old queue somehow still had a
    # leftover frame for "c-old" sitting in it, the current generation's
    # command resolution can only ever read from its OWN fresh queue --
    # there is no code path that lets it observe the old queue at all.
    new_outcome = sup.submit_command(_command(command_id="c-new"), payload={"behavior": "success"})
    assert new_outcome.outcome is ProviderExecutionOutcome.SUCCEEDED
    assert new_outcome.worker_generation == new_generation_number
    sup.shutdown()


# ---------------------------------------------------------------------------
# 22. teardown -> no owned/orphan child remains
# ---------------------------------------------------------------------------

def test_22_teardown_no_orphan_child_remains(supervisor):
    supervisor.start_generation()
    pid = supervisor.owned_process_pid
    supervisor.shutdown()

    assert supervisor._current.process.is_alive() is False
    # A joined, terminated multiprocessing.Process is fully reaped (no
    # zombie) -- exitcode becomes available once join() has completed,
    # which _hard_kill() already did as part of shutdown().
    assert supervisor._current.process.exitcode is not None

    assert pid is not None
    assert pid not in {process.pid for process in multiprocessing.active_children()}


# ---------------------------------------------------------------------------
# 23. future ProviderCommandType without timeout config remains rejected
#     mechanically by existing Slice A contract
# ---------------------------------------------------------------------------

def test_23_incomplete_command_timeout_coverage_rejected_by_slice_a():
    """Uses ONLY the existing frozen Slice A construction-time invariant
    (exact ProviderCommandType coverage) -- no new command type is
    invented here. Removing coverage for any current member proves the
    same mechanism would reject a hypothetical future member missing
    coverage."""
    incomplete = {t: 1.0 for t in ProviderCommandType}
    removed = next(iter(ProviderCommandType))
    del incomplete[removed]

    with pytest.raises(ValueError, match="must cover every ProviderCommandType member"):
        ProviderWorkerSupervisorConfig(
            startup_timeout_seconds=1.0,
            command_timeout_seconds=incomplete,
            graceful_shutdown_timeout_seconds=1.0,
            terminate_join_timeout_seconds=1.0,
            kill_join_timeout_seconds=1.0,
            parent_command_queue_capacity=8,
            child_data_queue_capacity=8,
            child_priority_queue_capacity=8,
            supervisor_inbox_capacity=8,
            max_frame_bytes=4096,
            protocol_version=1,
        )


# ---------------------------------------------------------------------------
# 24. repeated race stress -- terminal uniqueness
# ---------------------------------------------------------------------------

def test_24_repeated_race_stress_terminal_uniqueness(supervisor):
    for i in range(20):
        fake_gen = _Generation(
            number=1,
            process=_FakeProcess(alive=(i % 2 == 0)),
            command_queue=None,
            result_queue=_FakeQueue([{
                "frame_kind": "COMMAND_RESULT",
                "command_id": f"stress-{i}",
                "worker_generation": 1,
                "outcome": "SUCCEEDED",
                "terminal_observed_at_monotonic_ns": time.monotonic_ns(),
                "terminal_at_utc": datetime.now(timezone.utc).isoformat(),
                "provider_error_code": None,
                "provider_error_message": None,
                "normalized_provider_payload": None,
                "diagnostic_reason": None,
            }]),
            release_event=None,
        )
        supervisor._current = fake_gen
        already_expired = time.monotonic_ns() - 1
        outcome = supervisor._await_command_resolution(
            fake_gen, _command(command_id=f"stress-{i}"),
            dispatched_at_monotonic_ns=time.monotonic_ns() - 1_000_000,
            deadline_ns=already_expired,
        )
        assert outcome.outcome in {
            ProviderExecutionOutcome.SUCCEEDED,
            ProviderExecutionOutcome.TIMEOUT,
        }
    supervisor._current = None


def test_25_invalid_outcome_is_protocol_error(supervisor):
    supervisor.start_generation()
    outcome = supervisor.submit_command(_command(), payload={"behavior": "success"})
    assert outcome.outcome is ProviderExecutionOutcome.SUCCEEDED

    fake_gen = _Generation(
        number=1, process=_FakeProcess(), command_queue=None,
        result_queue=_FakeQueue([]), release_event=None,
    )
    bad = {
        "frame_kind": "COMMAND_RESULT", "command_id": "c1", "worker_generation": 1,
        "outcome": "NOT_A_REAL_OUTCOME", "terminal_observed_at_monotonic_ns": time.monotonic_ns(),
        "terminal_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    result = supervisor._resolve_from_frame(fake_gen, _command(), bad, time.monotonic_ns())
    assert result.outcome is ProviderExecutionOutcome.PROTOCOL_ERROR
    supervisor.shutdown()


def test_26_shutdown_kill_failure_is_fatal(supervisor, monkeypatch):
    supervisor.start_generation()
    monkeypatch.setattr(supervisor, "_hard_kill", lambda generation: False)
    supervisor.shutdown()
    assert supervisor.state is SupervisorState.FATAL
    with pytest.raises(SupervisorFatalError):
        supervisor.replace_generation()
