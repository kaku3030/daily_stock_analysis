import dataclasses

from data_provider.live_feed_types import FailureClass, LifecycleState
from src.services.live_feed.health import LiveFeedHealth, StreamFeedHealth, SymbolFeedHealth


def test_live_feed_health_has_no_score_field() -> None:
    field_names = {f.name for f in dataclasses.fields(LiveFeedHealth)}
    assert "score" not in field_names


def test_live_feed_health_does_not_expose_decision_eligibility_authority() -> None:
    for cls in (LiveFeedHealth, SymbolFeedHealth, StreamFeedHealth):
        field_names = {f.name for f in dataclasses.fields(cls)}
        assert not any("decision" in name.lower() or "eligib" in name.lower() for name in field_names)


def test_live_feed_health_minimal_construction() -> None:
    health = LiveFeedHealth(lifecycle_state=LifecycleState.DISCONNECTED, failure_class=FailureClass.UNKNOWN)
    assert health.symbols == ()
    assert health.findings == ()
