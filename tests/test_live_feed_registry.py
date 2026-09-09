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
