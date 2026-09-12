"""E11 Shadow lifecycle differential for provider-local caches.

This is a deliberately local model: it does not import or mutate provider
cache state.  The provider-specific policies are explicit so a shared helper
cannot accidentally erase empty-result, failure, lock, or observability
semantics.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from threading import Barrier, Lock, Thread
from typing import Any


@dataclass
class _PositiveSnapshot:
    ttl: float
    data: Any = None
    stored_at: float = 0.0
    events: list[str] = field(default_factory=list)

    def read(self, now: float) -> tuple[bool, Any]:
        if self.data is not None and now - self.stored_at < self.ttl:
            self.events.append("hit")
            return True, self.data
        self.events.append("miss")
        return False, None

    def write(self, value: Any, now: float) -> None:
        self.data = value
        self.stored_at = now
        self.events.append("write")

    def clear(self) -> None:
        self.data = None
        self.events.append("clear")


def test_positive_snapshot_lifecycle_preserves_empty_and_replacement_semantics() -> None:
    cache = _PositiveSnapshot(ttl=10.0)

    assert cache.read(100.0) == (False, None)
    cache.write([], 100.0)
    assert cache.read(109.999) == (True, [])
    assert cache.read(110.0) == (False, None)

    cache.write({"version": 2}, 111.0)
    assert cache.read(111.0) == (True, {"version": 2})
    cache.clear()
    assert cache.read(111.0) == (False, None)
    assert cache.events == ["miss", "write", "hit", "miss", "write", "hit", "clear", "miss"]


def test_positive_snapshot_preserves_negative_age_and_none_miss() -> None:
    cache = _PositiveSnapshot(ttl=10.0, data="value", stored_at=101.0)

    assert cache.read(100.0) == (True, "value")
    cache.data = None
    assert cache.read(100.0) == (False, None)


def test_exception_during_population_does_not_write_positive_snapshot() -> None:
    cache = _PositiveSnapshot(ttl=10.0)

    try:
        raise RuntimeError("provider failure")
    except RuntimeError:
        pass

    assert cache.read(100.0) == (False, None)
    assert cache.events == ["miss"]


def test_lock_serializes_hk_style_double_checked_population() -> None:
    cache = _PositiveSnapshot(ttl=10.0)
    lock = Lock()
    barrier = Barrier(2)
    writes: list[int] = []

    def reader(value: int) -> None:
        barrier.wait()
        with lock:
            hit, _ = cache.read(100.0)
            if not hit:
                cache.write(value, 100.0)
                writes.append(value)

    threads = [Thread(target=reader, args=(value,)) for value in (1, 2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert len(writes) == 1
    assert cache.read(100.0)[0]


def test_failure_ttl_is_not_equivalent_to_positive_snapshot_cache() -> None:
    cache = {"data": None, "timestamp": 100.0, "last_result": "failure"}
    failure_ttl = 30.0
    positive_ttl = 1200.0

    age = 10.0
    failure_hit = cache["last_result"] == "failure" and age < failure_ttl
    positive_hit = cache["data"] is not None and age < positive_ttl
    assert failure_hit is True
    assert positive_hit is False
