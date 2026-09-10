from data_provider.live_feed_types import BindingStrength, ControlPlaneState, SemanticStreamKey
from src.services.live_feed.registry import DesiredSubscriptionRegistry

KEY = SemanticStreamKey(provider_id="futu", market="HK", symbol="HK.00700", stream_type="QUOTE")


def test_revision_increments_on_add() -> None:
    registry = DesiredSubscriptionRegistry()
    assert registry.snapshot().revision == 0
    snap = registry.add_desired(KEY)
    assert snap.revision == 1
    assert len(snap.entries) == 1
    assert snap.entries[0].semantic_stream_key == KEY
    assert snap.entries[0].control_plane_state is ControlPlaneState.DESIRED
    assert snap.entries[0].binding_strength is BindingStrength.UNVERIFIED


def test_revision_increments_on_remove() -> None:
    registry = DesiredSubscriptionRegistry()
    registry.add_desired(KEY)
    snap = registry.remove_desired(KEY)
    assert snap.revision == 2
    assert snap.entries == ()


def test_noop_mutation_does_not_bump_revision() -> None:
    registry = DesiredSubscriptionRegistry()
    # removing something never added is a no-op
    snap = registry.remove_desired(KEY)
    assert snap.revision == 0

    registry.add_desired(KEY)
    revision_after_add = registry.snapshot().revision
    # adding the same key again is a no-op
    snap2 = registry.add_desired(KEY)
    assert snap2.revision == revision_after_add


def test_readd_new_incarnation_bumps_epoch_and_revision() -> None:
    registry = DesiredSubscriptionRegistry()
    snap1 = registry.add_desired(KEY)
    assert snap1.entries[0].stream_subscription_epoch == 1

    registry.remove_desired(KEY)
    snap3 = registry.readd_new_incarnation(KEY)
    assert snap3.entries[0].stream_subscription_epoch == 2
    assert snap3.revision == 3  # add(1) + remove(1) + readd(1)


def test_readd_new_incarnation_resets_binding_strength() -> None:
    registry = DesiredSubscriptionRegistry()
    registry.add_desired(KEY)
    registry.set_control_plane_state(KEY, ControlPlaneState.ACKED, binding_strength=BindingStrength.VERIFIED)
    snap = registry.readd_new_incarnation(KEY)
    assert snap.entries[0].binding_strength is BindingStrength.UNVERIFIED
    assert snap.entries[0].control_plane_state is ControlPlaneState.DESIRED


def test_snapshot_ordering_is_deterministic() -> None:
    registry = DesiredSubscriptionRegistry()
    key_b = SemanticStreamKey(provider_id="futu", market="HK", symbol="HK.09988", stream_type="QUOTE")
    key_a = SemanticStreamKey(provider_id="futu", market="HK", symbol="HK.00700", stream_type="K_1M")
    registry.add_desired(key_b)
    registry.add_desired(key_a)
    snap1 = registry.snapshot()
    # rebuild independently in the opposite insertion order -- ordering must
    # be a deterministic function of the keys, not insertion order
    registry2 = DesiredSubscriptionRegistry()
    registry2.add_desired(key_a)
    registry2.add_desired(key_b)
    snap2 = registry2.snapshot()
    assert [e.semantic_stream_key for e in snap1.entries] == [e.semantic_stream_key for e in snap2.entries]


def test_set_control_plane_state_requires_existing_entry() -> None:
    registry = DesiredSubscriptionRegistry()
    import pytest

    with pytest.raises(KeyError):
        registry.set_control_plane_state(KEY, ControlPlaneState.ACKED)


def test_snapshot_is_immutable_and_not_affected_by_further_mutation() -> None:
    registry = DesiredSubscriptionRegistry()
    registry.add_desired(KEY)
    snap = registry.snapshot()
    registry.remove_desired(KEY)
    assert len(snap.entries) == 1  # the earlier snapshot is untouched


def test_control_plane_observation_never_advances_desired_revision() -> None:
    registry = DesiredSubscriptionRegistry()
    registry.add_desired(KEY)
    assert registry.snapshot().revision == 1

    for state in (
        ControlPlaneState.REQUESTED,
        ControlPlaneState.ACKED,
        ControlPlaneState.INCARNATION_UNVERIFIED,
        ControlPlaneState.INCARNATION_BOUND,
        ControlPlaneState.REJECTED,
    ):
        snap = registry.set_control_plane_state(KEY, state)
        assert snap.revision == 1
        assert snap.entries[0].control_plane_state is state


def test_binding_observation_never_advances_desired_revision() -> None:
    registry = DesiredSubscriptionRegistry()
    registry.add_desired(KEY)

    snap = registry.set_control_plane_state(
        KEY,
        ControlPlaneState.INCARNATION_BOUND,
        binding_strength=BindingStrength.VERIFIED,
    )

    assert snap.revision == 1
    assert snap.entries[0].binding_strength is BindingStrength.VERIFIED


def test_unknown_control_plane_observation_does_not_mutate_revision() -> None:
    import pytest

    registry = DesiredSubscriptionRegistry()
    registry.add_desired(KEY)
    unknown_key = SemanticStreamKey(
        provider_id="futu",
        market="HK",
        symbol="HK.09988",
        stream_type="QUOTE",
    )
    before = registry.snapshot()

    with pytest.raises(KeyError):
        registry.set_control_plane_state(unknown_key, ControlPlaneState.ACKED)

    after = registry.snapshot()
    assert after.revision == before.revision == 1
    assert after.entries == before.entries


def test_multiple_keys_observations_do_not_mutate_global_desired_revision() -> None:
    registry = DesiredSubscriptionRegistry()
    other_key = SemanticStreamKey(
        provider_id="futu",
        market="HK",
        symbol="HK.09988",
        stream_type="QUOTE",
    )
    registry.add_desired(KEY)
    registry.add_desired(other_key)
    assert registry.snapshot().revision == 2

    registry.set_control_plane_state(KEY, ControlPlaneState.REQUESTED)
    registry.set_control_plane_state(other_key, ControlPlaneState.ACKED)
    registry.set_control_plane_state(KEY, ControlPlaneState.INCARNATION_BOUND)

    assert registry.snapshot().revision == 2


def test_only_intent_mutations_advance_revision_while_observations_preserve_epoch() -> None:
    import pytest

    registry = DesiredSubscriptionRegistry()
    added = registry.add_desired(KEY)
    assert added.revision == 1
    first_epoch = added.entries[0].stream_subscription_epoch

    observed = registry.set_control_plane_state(KEY, ControlPlaneState.ACKED)
    assert observed.revision == 1
    assert observed.entries[0].stream_subscription_epoch == first_epoch

    removed = registry.remove_desired(KEY)
    assert removed.revision == 2

    with pytest.raises(KeyError):
        registry.set_control_plane_state(KEY, ControlPlaneState.REJECTED)
    assert registry.snapshot().revision == 2

    readded = registry.readd_new_incarnation(KEY)
    assert readded.revision == 3
    assert readded.entries[0].stream_subscription_epoch == first_epoch + 1
    assert readded.entries[0].control_plane_state is ControlPlaneState.DESIRED


def test_provider_observation_does_not_make_same_intent_command_result_stale() -> None:
    from datetime import datetime, timezone

    from src.services.live_feed.commands import (
        FakeProviderCommandExecutor,
        ProviderCommandResult,
        ProviderCommandType,
        is_command_result_stale,
    )
    from src.services.live_feed.controller import LiveFeedController

    now = datetime(2026, 9, 10, 0, 0, 0, tzinfo=timezone.utc)
    controller = LiveFeedController(
        runtime_instance_id="runtime-1",
        provider_id="futu",
        command_executor=FakeProviderCommandExecutor(),
        now_utc=lambda: now,
    )
    controller.request_add_desired(KEY)
    controller.process_pending()
    command = controller.submit_command(
        ProviderCommandType.SUBSCRIBE,
        semantic_stream_key=KEY,
        stream_subscription_epoch=1,
    )
    assert command.desired_registry_revision == 1

    controller.request_set_control_plane_state(KEY, ControlPlaneState.REQUESTED)
    controller.process_pending()
    current = controller.snapshot()
    assert current.desired_registry_revision == 1

    result = ProviderCommandResult(
        command_id=command.command_id,
        command_type=command.command_type,
        succeeded=True,
        controller_generation=command.controller_generation,
        desired_registry_revision=command.desired_registry_revision,
        completed_at=now,
    )
    assert not is_command_result_stale(
        result,
        current_controller_generation=current.controller_generation,
        current_desired_registry_revision=current.desired_registry_revision,
    )
