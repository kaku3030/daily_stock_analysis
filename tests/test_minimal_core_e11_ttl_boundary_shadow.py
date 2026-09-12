"""E11 Shadow differential for ordinary positive snapshot-cache boundaries.

This intentionally models the existing predicate instead of importing or
changing provider state.  It proves the boundary contract before any helper
is considered; HK failure memoization remains out of scope.
"""

from __future__ import annotations


def _legacy_fresh(data: object, stored_at: float, ttl: float, now: float) -> bool:
    return data is not None and now - stored_at < ttl


def _shadow_fresh(data: object, stored_at: float, ttl: float, now: float) -> bool:
    age = now - stored_at
    return data is not None and age < ttl


def test_positive_snapshot_cache_ttl_boundary_is_strict() -> None:
    data = object()
    stored_at = 100.0
    ttl = 600.0

    for delta, expected in ((-0.000001, True), (0.0, False), (0.000001, False)):
        now = stored_at + ttl + delta
        assert _legacy_fresh(data, stored_at, ttl, now) is expected
        assert _shadow_fresh(data, stored_at, ttl, now) is expected


def test_positive_snapshot_cache_miss_and_empty_value_semantics_are_preserved() -> None:
    for data in (None, "", [], 0):
        assert _legacy_fresh(data, 100.0, 600.0, 100.0) == (data is not None)
        assert _shadow_fresh(data, 100.0, 600.0, 100.0) == (data is not None)


def test_negative_age_does_not_create_a_new_cache_semantic() -> None:
    data = object()
    assert _legacy_fresh(data, 101.0, 600.0, 100.0)
    assert _shadow_fresh(data, 101.0, 600.0, 100.0)
