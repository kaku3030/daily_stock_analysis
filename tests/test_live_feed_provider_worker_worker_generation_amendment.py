"""Narrow regressions for the Slice A worker-generation contract amendment."""

from datetime import datetime, timezone

import pytest

from src.services.live_feed.commands import ProviderCommand, ProviderCommandType
from src.services.live_feed.provider_worker_contracts import (
    ProviderExecutionOutcome,
    ResolvedProviderCommandOutcome,
)


NOW_UTC = datetime(2026, 9, 11, 12, 0, 0, tzinfo=timezone.utc)


def _command() -> ProviderCommand:
    return ProviderCommand(
        runtime_instance_id="runtime-1",
        provider_id="futu",
        controller_generation=0,
        desired_registry_revision=1,
        command_id="cmd-worker-generation-amendment",
        command_type=ProviderCommandType.SUBSCRIBE,
        created_at=NOW_UTC,
    )


def _outcome(**overrides) -> ResolvedProviderCommandOutcome:
    values = dict(
        runtime_instance_id="runtime-1",
        provider_id="futu",
        worker_generation=1,
        command=_command(),
        outcome=ProviderExecutionOutcome.CANCELLED_GENERATION_INVALIDATED,
        dispatched_at_monotonic_ns=None,
        terminal_observed_at_monotonic_ns=2_000,
        terminal_at_utc=NOW_UTC,
    )
    values.update(overrides)
    return ResolvedProviderCommandOutcome(**values)


def test_worker_generation_none_accepted_exactly_for_never_dispatched_generation_invalidation() -> None:
    result = _outcome(worker_generation=None)
    assert result.worker_generation is None
    assert result.outcome is ProviderExecutionOutcome.CANCELLED_GENERATION_INVALIDATED
    assert result.dispatched_at_monotonic_ns is None


@pytest.mark.parametrize(
    "outcome",
    [
        ProviderExecutionOutcome.SUCCEEDED,
        ProviderExecutionOutcome.PROVIDER_REJECTED,
        ProviderExecutionOutcome.PROVIDER_EXCEPTION,
        ProviderExecutionOutcome.TIMEOUT,
        ProviderExecutionOutcome.WORKER_EXITED,
        ProviderExecutionOutcome.PROTOCOL_ERROR,
        ProviderExecutionOutcome.CANCELLED_SHUTDOWN,
    ],
)
def test_worker_generation_none_rejected_for_every_other_outcome(
    outcome: ProviderExecutionOutcome,
) -> None:
    dispatched = None if outcome is ProviderExecutionOutcome.CANCELLED_SHUTDOWN else 1_000
    with pytest.raises(ValueError, match="worker_generation may be None"):
        _outcome(
            worker_generation=None,
            outcome=outcome,
            dispatched_at_monotonic_ns=dispatched,
        )


def test_worker_generation_none_rejected_when_generation_invalidated_was_dispatched() -> None:
    with pytest.raises(ValueError, match="worker_generation may be None"):
        _outcome(worker_generation=None, dispatched_at_monotonic_ns=1_000)


def test_positive_worker_generation_behavior_unchanged_for_generation_invalidation() -> None:
    assert _outcome(worker_generation=1).worker_generation == 1
    for bad in (0, -1, True):
        with pytest.raises(ValueError):
            _outcome(worker_generation=bad)
