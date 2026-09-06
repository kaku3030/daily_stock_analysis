import dataclasses
from datetime import datetime, timedelta, timezone, tzinfo as _tzinfo
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from src.services.strategy_lab.temporal_contract import (
    TemporalEvidence,
    TemporalInterval,
    canonical_utc_datetime,
    canonical_utc_text,
    is_available_by,
)


PERMANENT_TEMPORAL_CONTRACT_TEST_IDS = (
    "TEST_NAIVE_DATETIME_REJECTED",
    "TEST_NAIVE_TIME_IS_NOT_ASSUMED_UTC",
    "TEST_NON_DATETIME_TEMPORAL_INPUT_REJECTED",
    "TEST_TZINFO_WITHOUT_OFFSET_REJECTED",
    "TEST_AWARE_DATETIME_ACCEPTED",
    "TEST_ZONEINFO_AWARE_DATETIME_ACCEPTED",
    "TEST_EQUAL_INSTANT_DIFFERENT_OFFSETS_CANONICALIZE_EQUAL",
    "TEST_CANONICAL_TIME_IS_UTC",
    "TEST_CANONICALIZATION_PRESERVES_MICROSECONDS",
    "TEST_CANONICAL_TEXT_HAS_FIXED_MICROSECOND_PRECISION",
    "TEST_CANONICAL_TEXT_ALWAYS_USES_PLUS_00_00",
    "TEST_CANONICAL_TEXT_NEVER_USES_Z",
    "TEST_EQUAL_INSTANTS_HAVE_EQUAL_CANONICAL_TEXT",
    "TEST_INTERVAL_IS_HALF_OPEN",
    "TEST_ZERO_LENGTH_INTERVAL_REJECTED",
    "TEST_REVERSED_INTERVAL_REJECTED",
    "TEST_ADJACENT_INTERVALS_DO_NOT_OVERLAP",
    "TEST_OVERLAPPING_INTERVALS_DETECTED",
    "TEST_INTERVAL_CONTAINS_START",
    "TEST_INTERVAL_EXCLUDES_END",
    "TEST_NAIVE_MOMENT_REJECTED_IN_CONTAINS",
    "TEST_EFFECTIVE_BEFORE_AVAILABLE_IS_LEGAL",
    "TEST_EFFECTIVE_EQUALS_AVAILABLE_IS_LEGAL",
    "TEST_AVAILABLE_BEFORE_EFFECTIVE_IS_LEGAL",
    "TEST_EVIDENCE_AVAILABLE_BEFORE_DECISION",
    "TEST_EVIDENCE_AVAILABLE_EXACTLY_AT_DECISION",
    "TEST_EVIDENCE_AFTER_DECISION_IS_NOT_AVAILABLE",
    "TEST_INVALID_DECISION_TIME_RAISES_NOT_FALSE",
    "TEST_NO_MARKET_CALENDAR_IMPORTS",
    "TEST_NO_DATA_LAYER_IMPORTS",
    "TEST_FROZEN_PUBLIC_CONTRACT_SHAPE",
)

UTC = timezone.utc


def _dt(*args, tz=UTC, **kwargs) -> datetime:
    return datetime(*args, tzinfo=tz, **kwargs)


class _NullOffsetTzinfo(_tzinfo):
    """A degenerate tzinfo whose utcoffset() is None, not a real offset."""

    def utcoffset(self, dt):
        return None

    def tzname(self, dt):
        return "NULL"

    def dst(self, dt):
        return None


# ---- Datetime contract: rejection ----


def test_naive_datetime_rejected() -> None:
    with pytest.raises(ValueError):
        canonical_utc_datetime(datetime(2026, 1, 1, 12, 0, 0))
    with pytest.raises(ValueError):
        TemporalInterval(datetime(2026, 1, 1), datetime(2026, 1, 2))
    with pytest.raises(ValueError):
        TemporalEvidence(datetime(2026, 1, 1), datetime(2026, 1, 2))
    with pytest.raises(ValueError):
        is_available_by(
            TemporalEvidence(_dt(2026, 1, 1), _dt(2026, 1, 1)),
            datetime(2026, 1, 1),
        )


def test_naive_time_is_not_assumed_utc() -> None:
    """A naive datetime must be rejected outright, never silently treated
    as UTC (or any other zone).
    """

    naive_noon = datetime(2026, 1, 1, 12, 0, 0)
    with pytest.raises(ValueError):
        canonical_utc_datetime(naive_noon)
    with pytest.raises(ValueError):
        TemporalEvidence(effective_at=naive_noon, available_at=_dt(2026, 1, 1))
    with pytest.raises(ValueError):
        TemporalInterval(naive_noon, _dt(2026, 1, 2))


def test_non_datetime_temporal_input_rejected() -> None:
    for bad in ("2026-01-01T12:00:00+00:00", 1767268800, 1767268800.0, None, object()):
        with pytest.raises(ValueError):
            canonical_utc_datetime(bad)  # type: ignore[arg-type]


def test_tzinfo_without_offset_rejected() -> None:
    broken = datetime(2026, 1, 1, 12, 0, 0, tzinfo=_NullOffsetTzinfo())
    assert broken.tzinfo is not None
    assert broken.utcoffset() is None
    with pytest.raises(ValueError):
        canonical_utc_datetime(broken)


# ---- Datetime contract: acceptance ----


def test_aware_datetime_accepted() -> None:
    value = _dt(2026, 3, 15, 9, 30, 0)
    result = canonical_utc_datetime(value)
    assert result == value
    assert result.tzinfo is timezone.utc


def test_zoneinfo_aware_datetime_accepted() -> None:
    tokyo_noon = datetime(2026, 6, 1, 12, 0, 0, tzinfo=ZoneInfo("Asia/Tokyo"))
    result = canonical_utc_datetime(tokyo_noon)
    assert result.tzinfo is timezone.utc
    assert result == tokyo_noon


def test_equal_instant_different_offsets_canonicalize_equal() -> None:
    plus_eight = timezone(timedelta(hours=8))
    utc_value = _dt(2026, 1, 10, 12, 0, 0)
    shifted_value = datetime(2026, 1, 10, 20, 0, 0, tzinfo=plus_eight)

    assert canonical_utc_datetime(utc_value) == canonical_utc_datetime(shifted_value)


def test_canonical_time_is_utc() -> None:
    plus_eight = timezone(timedelta(hours=8))
    value = datetime(2026, 1, 10, 20, 0, 0, tzinfo=plus_eight)
    result = canonical_utc_datetime(value)
    assert result.tzinfo is timezone.utc
    assert result == _dt(2026, 1, 10, 12, 0, 0)


def test_canonicalization_uses_astimezone_not_replace() -> None:
    """Canonicalization must convert the instant, not reinterpret the
    wall-clock reading -- proves astimezone semantics, not replace().
    """

    plus_eight = timezone(timedelta(hours=8))
    value = datetime(2026, 1, 10, 20, 0, 0, tzinfo=plus_eight)
    result = canonical_utc_datetime(value)

    # replace(tzinfo=utc) would have kept the 20:00 wall-clock reading.
    assert result.hour != 20
    assert result.hour == 12


def test_canonicalization_preserves_microseconds() -> None:
    value = _dt(2026, 1, 1, 0, 0, 0, microsecond=123456)
    assert canonical_utc_datetime(value).microsecond == 123456

    plus_eight = timezone(timedelta(hours=8))
    shifted = datetime(2026, 1, 1, 8, 0, 0, 123456, tzinfo=plus_eight)
    assert canonical_utc_datetime(shifted).microsecond == 123456


# ---- Canonical text ----


def test_canonical_text_has_fixed_microsecond_precision() -> None:
    value = _dt(2026, 1, 1, 0, 0, 0, microsecond=5)
    text = canonical_utc_text(value)
    fractional = text.split(".")[1].split("+")[0]
    assert len(fractional) == 6
    assert fractional == "000005"


def test_canonical_text_always_uses_plus_00_00() -> None:
    assert canonical_utc_text(_dt(2026, 1, 1, 12, 0, 0)).endswith("+00:00")

    plus_eight = timezone(timedelta(hours=8))
    shifted = datetime(2026, 1, 1, 20, 0, 0, tzinfo=plus_eight)
    assert canonical_utc_text(shifted).endswith("+00:00")


def test_canonical_text_never_uses_z() -> None:
    text = canonical_utc_text(_dt(2026, 1, 1, 12, 0, 0))
    assert "Z" not in text


def test_equal_instants_have_equal_canonical_text() -> None:
    plus_eight = timezone(timedelta(hours=8))
    utc_value = _dt(2026, 1, 10, 12, 0, 0, microsecond=250000)
    shifted_value = datetime(2026, 1, 10, 20, 0, 0, 250000, tzinfo=plus_eight)

    assert canonical_utc_text(utc_value) == canonical_utc_text(shifted_value)
    assert canonical_utc_text(utc_value) == "2026-01-10T12:00:00.250000+00:00"


def test_canonical_text_matches_isoformat_microseconds_semantics() -> None:
    value = _dt(2026, 7, 4, 8, 15, 30, microsecond=1)
    expected = value.astimezone(timezone.utc).isoformat(timespec="microseconds")
    assert canonical_utc_text(value) == expected


# ---- Interval: half-open semantics ----


def test_interval_is_half_open() -> None:
    interval = TemporalInterval(_dt(2026, 1, 1), _dt(2026, 1, 2))
    assert interval.contains(interval.start) is True
    assert interval.contains(interval.end) is False


def test_zero_length_interval_rejected() -> None:
    moment = _dt(2026, 1, 1, 12, 0, 0)
    with pytest.raises(ValueError):
        TemporalInterval(moment, moment)


def test_reversed_interval_rejected() -> None:
    with pytest.raises(ValueError):
        TemporalInterval(_dt(2026, 1, 2), _dt(2026, 1, 1))


def test_adjacent_intervals_do_not_overlap() -> None:
    boundary = _dt(2026, 1, 2)
    first = TemporalInterval(_dt(2026, 1, 1), boundary)
    second = TemporalInterval(boundary, _dt(2026, 1, 3))

    assert first.overlaps(second) is False
    assert second.overlaps(first) is False


def test_overlapping_intervals_detected() -> None:
    first = TemporalInterval(_dt(2026, 1, 1), _dt(2026, 1, 10))
    second = TemporalInterval(_dt(2026, 1, 5), _dt(2026, 1, 15))
    disjoint = TemporalInterval(_dt(2026, 2, 1), _dt(2026, 2, 5))

    assert first.overlaps(second) is True
    assert second.overlaps(first) is True
    assert first.overlaps(disjoint) is False


def test_interval_contains_start() -> None:
    interval = TemporalInterval(_dt(2026, 1, 1), _dt(2026, 1, 2))
    assert interval.contains(_dt(2026, 1, 1)) is True


def test_interval_excludes_end() -> None:
    interval = TemporalInterval(_dt(2026, 1, 1), _dt(2026, 1, 2))
    assert interval.contains(_dt(2026, 1, 2)) is False


def test_naive_moment_rejected_in_contains() -> None:
    interval = TemporalInterval(_dt(2026, 1, 1), _dt(2026, 1, 2))
    with pytest.raises(ValueError):
        interval.contains(datetime(2026, 1, 1, 12, 0, 0))


def test_interval_canonicalizes_start_and_end() -> None:
    plus_eight = timezone(timedelta(hours=8))
    interval = TemporalInterval(
        datetime(2026, 1, 1, 8, 0, 0, tzinfo=plus_eight),
        datetime(2026, 1, 2, 8, 0, 0, tzinfo=plus_eight),
    )
    assert interval.start.tzinfo is timezone.utc
    assert interval.end.tzinfo is timezone.utc
    assert interval.start == _dt(2026, 1, 1, 0, 0, 0)


def test_overlaps_rejects_non_interval() -> None:
    interval = TemporalInterval(_dt(2026, 1, 1), _dt(2026, 1, 2))
    with pytest.raises(ValueError):
        interval.overlaps("not an interval")  # type: ignore[arg-type]


# ---- TemporalEvidence: no ordering constraint ----


def test_effective_before_available_is_legal() -> None:
    evidence = TemporalEvidence(
        effective_at=_dt(2026, 1, 1), available_at=_dt(2026, 1, 2)
    )
    assert evidence.effective_at < evidence.available_at


def test_effective_equals_available_is_legal() -> None:
    moment = _dt(2026, 1, 1)
    evidence = TemporalEvidence(effective_at=moment, available_at=moment)
    assert evidence.effective_at == evidence.available_at


def test_available_before_effective_is_legal() -> None:
    """A correction or restatement can be available before its own
    effective instant -- no ordering constraint is enforced.
    """

    evidence = TemporalEvidence(
        effective_at=_dt(2026, 1, 5), available_at=_dt(2026, 1, 1)
    )
    assert evidence.available_at < evidence.effective_at


def test_evidence_canonicalizes_both_fields() -> None:
    plus_eight = timezone(timedelta(hours=8))
    evidence = TemporalEvidence(
        effective_at=datetime(2026, 1, 1, 8, 0, 0, tzinfo=plus_eight),
        available_at=datetime(2026, 1, 2, 8, 0, 0, tzinfo=plus_eight),
    )
    assert evidence.effective_at.tzinfo is timezone.utc
    assert evidence.available_at.tzinfo is timezone.utc


def test_evidence_does_not_carry_provenance_fields() -> None:
    """Producer timestamp honesty/provenance is explicitly out of scope."""

    field_names = {f.name for f in dataclasses.fields(TemporalEvidence)}
    assert field_names == {"effective_at", "available_at"}
    for forbidden in ("published_at", "received_at", "recorded_at"):
        assert forbidden not in field_names


# ---- Availability query ----


def test_evidence_available_before_decision() -> None:
    evidence = TemporalEvidence(effective_at=_dt(2026, 1, 1), available_at=_dt(2026, 1, 1))
    assert is_available_by(evidence, _dt(2026, 1, 2)) is True


def test_evidence_available_exactly_at_decision() -> None:
    moment = _dt(2026, 1, 1, 12, 0, 0)
    evidence = TemporalEvidence(effective_at=moment, available_at=moment)
    assert is_available_by(evidence, moment) is True


def test_evidence_after_decision_is_not_available() -> None:
    evidence = TemporalEvidence(effective_at=_dt(2026, 1, 5), available_at=_dt(2026, 1, 5))
    assert is_available_by(evidence, _dt(2026, 1, 1)) is False


def test_invalid_decision_time_raises_not_false() -> None:
    evidence = TemporalEvidence(effective_at=_dt(2026, 1, 1), available_at=_dt(2026, 1, 1))

    with pytest.raises(ValueError):
        is_available_by(evidence, datetime(2026, 1, 1))  # naive
    with pytest.raises(ValueError):
        is_available_by(evidence, "2026-01-01")  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        is_available_by(evidence, None)  # type: ignore[arg-type]


def test_is_available_by_rejects_non_evidence() -> None:
    with pytest.raises(ValueError):
        is_available_by("not evidence", _dt(2026, 1, 1))  # type: ignore[arg-type]


# ---- Structural boundaries ----


def _module_tree():
    import ast

    from src.services.strategy_lab import temporal_contract

    return ast.parse(Path(temporal_contract.__file__).read_text(encoding="utf-8"))


def test_no_market_calendar_imports() -> None:
    import ast

    forbidden_roots = {"trading_calendar", "zoneinfo", "pytz"}

    for node in ast.walk(_module_tree()):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert not (set(alias.name.split(".")) & forbidden_roots), alias.name
        elif isinstance(node, ast.ImportFrom):
            assert not (set((node.module or "").split(".")) & forbidden_roots), node.module


def test_no_data_layer_imports() -> None:
    import ast

    forbidden_roots = {
        "data_provider",
        "storage",
        "repositories",
        "pandas",
        "numpy",
        "sqlalchemy",
        "experiment_governance",
    }

    for node in ast.walk(_module_tree()):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert not (set(alias.name.split(".")) & forbidden_roots), alias.name
        elif isinstance(node, ast.ImportFrom):
            assert not (set((node.module or "").split(".")) & forbidden_roots), node.module


def test_module_is_a_strategy_lab_leaf() -> None:
    import ast

    for node in ast.walk(_module_tree()):
        if isinstance(node, ast.ImportFrom):
            assert node.level == 0, f"relative import found: {ast.dump(node)}"
            assert not (node.module or "").startswith("src.services.strategy_lab")


def test_no_performance_report_dependency() -> None:
    import ast

    forbidden = {"performance_models", "PerformanceReport"}

    for node in ast.walk(_module_tree()):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name.split(".")[-1] not in forbidden
        elif isinstance(node, ast.ImportFrom):
            assert (node.module or "").split(".")[-1] not in forbidden
            for alias in node.names:
                assert alias.name not in forbidden


# ---- Frozen public contract shape ----


def test_frozen_public_contract_shape() -> None:
    """Mechanical schema-drift guard: field names/order on every frozen
    dataclass and exact positional parameter order on every public callable,
    so a rename, a silently added field, or a parameter reorder fails here
    even when algorithms stay green.
    """

    assert dataclasses.is_dataclass(TemporalInterval)
    assert tuple(f.name for f in dataclasses.fields(TemporalInterval)) == ("start", "end")

    assert dataclasses.is_dataclass(TemporalEvidence)
    assert tuple(f.name for f in dataclasses.fields(TemporalEvidence)) == (
        "effective_at",
        "available_at",
    )

    import inspect

    # Exact ordered tuples, not sets: a positional parameter reorder (e.g.
    # is_available_by(decision_time, evidence)) must fail this test even
    # though the parameter *names* would still match a set comparison.
    assert tuple(inspect.signature(canonical_utc_datetime).parameters) == ("value",)
    assert tuple(inspect.signature(canonical_utc_text).parameters) == ("value",)
    assert tuple(inspect.signature(is_available_by).parameters) == (
        "evidence",
        "decision_time",
    )
    assert tuple(inspect.signature(TemporalInterval.contains).parameters) == (
        "self",
        "moment",
    )
    assert tuple(inspect.signature(TemporalInterval.overlaps).parameters) == (
        "self",
        "other",
    )


def test_frozen_public_export_surface() -> None:
    """The Temporal Contract exports through src.services.strategy_lab are
    exactly the five frozen public symbols -- no more, no less -- and the
    private validator never leaks into the package surface.
    """

    import src.services.strategy_lab as strategy_lab
    from src.services.strategy_lab import temporal_contract as module

    temporal_contract_public_names = {
        name
        for name in dir(module)
        if not name.startswith("_")
        and getattr(module, name) is getattr(strategy_lab, name, object())
    }

    assert temporal_contract_public_names == {
        "TemporalEvidence",
        "TemporalInterval",
        "canonical_utc_datetime",
        "canonical_utc_text",
        "is_available_by",
    }

    assert not hasattr(strategy_lab, "_require_aware_datetime")
    assert "_require_aware_datetime" not in strategy_lab.__all__
    assert "_require_aware_datetime" not in dir(strategy_lab)


# ---- Permanent adversarial manifest ----


def test_permanent_temporal_contract_manifest_cannot_shrink() -> None:
    module_tests = set(globals())
    for test_id in PERMANENT_TEMPORAL_CONTRACT_TEST_IDS:
        assert test_id.lower() in module_tests, f"missing permanent adversarial test: {test_id}"
    assert len(PERMANENT_TEMPORAL_CONTRACT_TEST_IDS) == 31
