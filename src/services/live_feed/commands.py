"""Provider command execution boundary (frozen contract §15, Blocking
Execution Model doc LANE 3).

The controller writer must never directly call a potentially-blocking
provider SDK method. This module defines the command/result vocabulary and
a `ProviderCommandExecutor` Protocol; it contains NO real Futu execution.

`FakeProviderCommandExecutor` is a deterministic test double only -- it
runs its handler in-line on the caller's thread with no isolation or
timeout mechanism of any kind, and must never be mistaken for a
production answer to the isolation-mechanism question that
LIVE_FEED_BLOCKING_EXECUTION_MODEL_V0_1.md leaves explicitly open (thread
timeout vs. process isolation). Do not reuse it, or the semantics
research harness's `bounded_probe.py`, as production code.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Mapping, Protocol

from data_provider.live_feed_types import SemanticStreamKey


class ProviderCommandType(str, Enum):
    CONNECT = "CONNECT"
    SUBSCRIBE = "SUBSCRIBE"
    UNSUBSCRIBE = "UNSUBSCRIBE"
    CLOSE = "CLOSE"
    QUERY_SUBSCRIPTION = "QUERY_SUBSCRIPTION"
    DIAGNOSTIC = "DIAGNOSTIC"


@dataclass(frozen=True)
class ProviderCommand:
    """One issued command, carrying the exact identity it was issued
    under so a late result can be checked for relevance before being
    applied (frozen contract's worked example: a SUBSCRIBE issued under
    revision 12 whose result arrives after the registry moved to 13 must
    not overwrite current desired truth).
    """

    runtime_instance_id: str
    provider_id: str
    controller_generation: int
    desired_registry_revision: int
    command_id: str
    command_type: ProviderCommandType
    created_at: datetime
    stream_subscription_epoch: int | None = None
    semantic_stream_key: SemanticStreamKey | None = None


@dataclass(frozen=True)
class ProviderCommandResult:
    """``succeeded``/``error`` are legacy, non-authoritative projections
    kept for backward compatibility only -- new code must read
    ``provider_execution_outcome`` (and, for its two structured failure
    kinds, ``provider_error_code``/``provider_error_message``/
    ``diagnostic_reason``) as the record of truth.

    ``provider_execution_outcome`` holds the exact
    ``ProviderExecutionOutcome`` member *value* (a plain ``str``, never
    the enum type itself -- importing the enum here would create a
    circular import with ``provider_worker_contracts.py``, which already
    imports from this module; the same str-value-over-boundary pattern is
    already used for the child<->supervisor wire protocol). It is
    ``None`` **if and only if** no Supervisor-authoritative terminal fact
    exists for this command at all (Slice C: an ``AdmissionClosedError``
    or ``SupervisorFatalError`` observed before any
    ``ResolvedProviderCommandOutcome`` could be produced) -- it must never
    be read as UNKNOWN/PROVIDER_REJECTED/PROVIDER_EXCEPTION/TIMEOUT/
    WORKER_EXITED/PROTOCOL_ERROR/generic-failure, and it is never ``None``
    for a command that genuinely received a Supervisor resolution.
    ``worker_generation`` mirrors ``ResolvedProviderCommandOutcome.
    worker_generation`` verbatim, including its own narrow ``None`` case
    (never-established generation) -- orthogonal to
    ``controller_generation``/``desired_registry_revision`` (frozen
    principle 10: never conflate connection/generation identities), and
    deliberately excluded from ``is_command_result_stale``, which stays
    scoped to the two fields below only.
    """

    command_id: str
    command_type: ProviderCommandType
    succeeded: bool
    controller_generation: int
    desired_registry_revision: int
    completed_at: datetime
    error: str | None = None
    raw_payload: Mapping[str, Any] | None = None
    worker_generation: int | None = None
    provider_execution_outcome: str | None = None
    provider_error_code: str | None = None
    provider_error_message: str | None = None
    diagnostic_reason: str | None = None


def is_command_result_stale(
    result: ProviderCommandResult,
    *,
    current_controller_generation: int,
    current_desired_registry_revision: int,
) -> bool:
    """True if `result` was issued under identity that no longer matches
    current controller truth -- such a result must be recorded as
    historical evidence only, never applied as current state.
    """

    return (
        result.controller_generation != current_controller_generation
        or result.desired_registry_revision != current_desired_registry_revision
    )


class ProviderCommandExecutor(Protocol):
    """LANE 3 boundary. `submit` must return without blocking on any
    provider SDK call -- results are delivered later via the registered
    sink, never as `submit`'s return value.
    """

    def submit(self, command: ProviderCommand) -> None: ...

    def register_result_sink(self, sink: Callable[[ProviderCommandResult], None]) -> None: ...


class FakeProviderCommandExecutor:
    """Deterministic executor for tests. See module docstring: NOT a
    production implementation, and calling `submit` is synchronous
    in-line execution of `handler`, not an isolated/bounded call.
    """

    def __init__(self, handler: Callable[[ProviderCommand], ProviderCommandResult] | None = None) -> None:
        self._handler = handler
        self._sink: Callable[[ProviderCommandResult], None] | None = None
        self.submitted: list[ProviderCommand] = []

    def register_result_sink(self, sink: Callable[[ProviderCommandResult], None]) -> None:
        self._sink = sink

    def submit(self, command: ProviderCommand) -> None:
        self.submitted.append(command)
        if self._handler is None:
            return
        result = self._handler(command)
        if self._sink is not None:
            self._sink(result)
