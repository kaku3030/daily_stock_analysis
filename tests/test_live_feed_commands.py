from datetime import datetime, timezone

from src.services.live_feed.commands import (
    FakeProviderCommandExecutor,
    ProviderCommand,
    ProviderCommandResult,
    ProviderCommandType,
    is_command_result_stale,
)


def _command(**overrides) -> ProviderCommand:
    fields = dict(
        runtime_instance_id="r1",
        provider_id="futu",
        controller_generation=1,
        desired_registry_revision=12,
        command_id="c1",
        command_type=ProviderCommandType.SUBSCRIBE,
        created_at=datetime.now(timezone.utc),
    )
    fields.update(overrides)
    return ProviderCommand(**fields)


def test_command_identity_captures_generation_and_revision() -> None:
    command = _command()
    assert command.controller_generation == 1
    assert command.desired_registry_revision == 12


def test_late_result_detected_as_stale_by_identity_comparison() -> None:
    # Frozen contract's own worked example: SUBSCRIBE issued under revision
    # 12, desired registry later mutates to 13, then the revision-12 result
    # arrives late.
    result = ProviderCommandResult(
        command_id="c1",
        command_type=ProviderCommandType.SUBSCRIBE,
        succeeded=True,
        controller_generation=1,
        desired_registry_revision=12,
        completed_at=datetime.now(timezone.utc),
    )
    assert is_command_result_stale(result, current_controller_generation=1, current_desired_registry_revision=13)
    assert not is_command_result_stale(result, current_controller_generation=1, current_desired_registry_revision=12)
    assert is_command_result_stale(result, current_controller_generation=2, current_desired_registry_revision=12)


def test_fake_executor_submit_does_not_block_and_delivers_via_sink() -> None:
    received: list[ProviderCommandResult] = []

    def handler(command: ProviderCommand) -> ProviderCommandResult:
        return ProviderCommandResult(
            command_id=command.command_id,
            command_type=command.command_type,
            succeeded=True,
            controller_generation=command.controller_generation,
            desired_registry_revision=command.desired_registry_revision,
            completed_at=datetime.now(timezone.utc),
        )

    executor = FakeProviderCommandExecutor(handler=handler)
    executor.register_result_sink(received.append)
    command = _command()
    executor.submit(command)
    assert executor.submitted == [command]
    assert len(received) == 1
    assert received[0].command_id == "c1"
