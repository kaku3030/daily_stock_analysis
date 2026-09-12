from __future__ import annotations

import os

import pytest

from src.services.live_feed.commands import ProviderCommand, ProviderCommandType
from src.services.live_feed.provider_worker_contracts import ProviderExecutionOutcome, ProviderWorkerSupervisorConfig
from src.services.live_feed.provider_worker_supervisor import ProviderWorkerSupervisor


def _config() -> ProviderWorkerSupervisorConfig:
    return ProviderWorkerSupervisorConfig(
        startup_timeout_seconds=2,
        command_timeout_seconds={kind: 2 for kind in ProviderCommandType},
        graceful_shutdown_timeout_seconds=1,
        terminate_join_timeout_seconds=1,
        kill_join_timeout_seconds=1,
        parent_command_queue_capacity=4,
        child_data_queue_capacity=4,
        child_priority_queue_capacity=4,
        supervisor_inbox_capacity=4,
        max_frame_bytes=4096,
        protocol_version=1,
    )


def _command(command_id: str = "pblc-1") -> ProviderCommand:
    from datetime import datetime, timezone
    return ProviderCommand(
        runtime_instance_id="runtime-1", provider_id="fake",
        controller_generation=0, desired_registry_revision=0,
        command_id=command_id, command_type=ProviderCommandType.SUBSCRIBE,
        created_at=datetime.now(timezone.utc),
    )


def test_fake_execution_is_observed_in_spawned_child_pid() -> None:
    supervisor = ProviderWorkerSupervisor(runtime_instance_id="runtime-1", provider_id="fake", config=_config())
    try:
        supervisor.start_generation()
        outcome = supervisor.submit_command(_command())
        assert outcome.outcome is ProviderExecutionOutcome.SUCCEEDED
        assert outcome.normalized_provider_payload["child_pid"] != os.getpid()
        assert outcome.normalized_provider_payload["child_pid"] == supervisor.owned_process_pid
    finally:
        supervisor.shutdown()


def test_boundary_rejects_arbitrary_payload_before_fake_execution() -> None:
    supervisor = ProviderWorkerSupervisor(runtime_instance_id="runtime-1", provider_id="fake", config=_config())
    try:
        supervisor.start_generation()
        outcome = supervisor.submit_command(_command(), payload={"arbitrary": object()})
        assert outcome.outcome is not ProviderExecutionOutcome.SUCCEEDED
    finally:
        supervisor.shutdown()


def test_supervisor_has_no_provider_sdk_imports() -> None:
    from pathlib import Path
    source = Path("src/services/live_feed/provider_worker_supervisor.py").read_text(encoding="utf-8").lower()
    assert "import futu" not in source
    assert "openquotecontext" not in source
    assert "opensectradecontext" not in source.replace(" ", "")
