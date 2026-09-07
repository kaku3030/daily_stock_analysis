"""Permanent adversarial tests for the OOS Consumption Ledger domain layer.

Covers the frozen state model, resolution model, fingerprints, half-open
overlap semantics, and the no-reset public surface. Persistence-side
behavior (transactions, concurrency, idempotency against SQLite) lives in
``tests/test_oos_consumption_ledger_repo.py``.
"""

import inspect
from datetime import datetime, timezone

import pytest

from src.services.strategy_lab.experiment_governance import ExperimentManifest
from src.services.strategy_lab.oos_consumption import (
    OOSConsumptionAssessment,
    OOSConsumptionEvent,
    OOSConsumptionEventKind,
    OOSConsumptionResolution,
    OOSConsumptionState,
    compute_lineage_binding_fingerprint,
    compute_operation_fingerprint,
    derive_state,
    intervals_overlap,
    parse_aware_utc_text,
    resolve_target_lineage,
)
from src.services.strategy_lab.temporal_contract import TemporalInterval

UTC = timezone.utc


def _dt(s: str) -> datetime:
    return datetime.fromisoformat(s).replace(tzinfo=UTC)


def _interval(start: str, end: str) -> TemporalInterval:
    return TemporalInterval(_dt(start), _dt(end))


def _manifest(experiment_id: str, *, parent: str | None = None, root: str | None = None) -> ExperimentManifest:
    return ExperimentManifest(
        experiment_id=experiment_id,
        schema_version="v1",
        governed_components={"window_configuration": "f" * 64},
        created_at=_dt("2020-01-01T00:00:00"),
        root_experiment_id=root or experiment_id,
        parent_experiment_id=parent,
    )


# --------------------------------------------------------------------------
# Frozen state model
# --------------------------------------------------------------------------


def test_state_severity_is_monotonic() -> None:
    assert OOSConsumptionState.PRISTINE.severity_rank == 0
    assert OOSConsumptionState.CONSUMED.severity_rank == 1
    assert OOSConsumptionState.BURNED.severity_rank == 2
    assert OOSConsumptionState.PRISTINE.severity_rank < OOSConsumptionState.CONSUMED.severity_rank
    assert OOSConsumptionState.CONSUMED.severity_rank < OOSConsumptionState.BURNED.severity_rank


def test_derive_state_is_max_severity_and_order_invariant() -> None:
    kinds = (
        OOSConsumptionEventKind.CLAIMED_FOR_EVALUATION,
        OOSConsumptionEventKind.OUTCOME_USED,
    )
    for order in (kinds, tuple(reversed(kinds))):
        assert derive_state(order) is OOSConsumptionState.BURNED
    assert derive_state((OOSConsumptionEventKind.CLAIMED_FOR_EVALUATION,)) is OOSConsumptionState.CONSUMED
    assert derive_state(()) is OOSConsumptionState.PRISTINE


def test_event_kind_implied_states() -> None:
    assert OOSConsumptionEventKind.CLAIMED_FOR_EVALUATION.implied_state is OOSConsumptionState.CONSUMED
    assert OOSConsumptionEventKind.OUTCOME_USED.implied_state is OOSConsumptionState.BURNED


# --------------------------------------------------------------------------
# Half-open overlap semantics
# --------------------------------------------------------------------------


def test_adjacent_intervals_do_not_overlap() -> None:
    assert not intervals_overlap(
        _dt("2024-01-01"), _dt("2024-02-01"), _dt("2024-02-01"), _dt("2024-03-01")
    )


def test_partial_overlap_detected() -> None:
    assert intervals_overlap(
        _dt("2024-01-01"), _dt("2024-01-31"), _dt("2024-01-15"), _dt("2024-02-15")
    )


# --------------------------------------------------------------------------
# Resolution / assessment invariants
# --------------------------------------------------------------------------


def test_assessment_resolved_requires_state() -> None:
    with pytest.raises(ValueError):
        OOSConsumptionAssessment(OOSConsumptionResolution.RESOLVED, None, (), ())


def test_assessment_unresolved_forbids_state() -> None:
    for resolution in (OOSConsumptionResolution.INDETERMINATE, OOSConsumptionResolution.CONFLICT):
        with pytest.raises(ValueError):
            OOSConsumptionAssessment(resolution, OOSConsumptionState.PRISTINE, (), ())


def test_assessment_orders_and_validates_ids() -> None:
    assessment = OOSConsumptionAssessment(
        OOSConsumptionResolution.RESOLVED,
        OOSConsumptionState.CONSUMED,
        (3, 1, 2),
        ("b", "a"),
    )
    assert assessment.overlapping_event_ids == (1, 2, 3)
    assert assessment.lineage_experiment_ids == ("a", "b")


# --------------------------------------------------------------------------
# Temporal text contract
# --------------------------------------------------------------------------


def test_parse_aware_utc_text_round_trip_is_aware() -> None:
    text = "2024-01-15T12:30:45.123456+00:00"
    parsed = parse_aware_utc_text(text)
    assert parsed.tzinfo is not None
    assert parsed.utcoffset() is not None
    assert parsed.isoformat(timespec="microseconds") == text


def test_parse_aware_utc_text_rejects_naive_text() -> None:
    with pytest.raises(ValueError):
        parse_aware_utc_text("2024-01-15T12:30:45")


# --------------------------------------------------------------------------
# Fingerprints
# --------------------------------------------------------------------------


def test_lineage_binding_fingerprint_order_invariant() -> None:
    a = _manifest("A")
    b = _manifest("B", parent="A", root="A")
    fp1 = compute_lineage_binding_fingerprint((a, b))
    fp2 = compute_lineage_binding_fingerprint((b, a))
    assert fp1 == fp2


def test_lineage_binding_fingerprint_sensitive_to_definition() -> None:
    fp1 = compute_lineage_binding_fingerprint((_manifest("A"),))
    fp2 = compute_lineage_binding_fingerprint((_manifest("A", parent="X", root="X"),))
    assert fp1 != fp2


def test_operation_fingerprint_excludes_operation_id() -> None:
    kwargs = dict(
        event_kind=OOSConsumptionEventKind.CLAIMED_FOR_EVALUATION,
        experiment_id="E",
        manifest_hash="a" * 64,
        parent_experiment_id=None,
        root_experiment_id="E",
        oos_start=_dt("2024-01-01"),
        oos_end=_dt("2024-02-01"),
        declared_occurred_at=_dt("2024-01-05"),
        lineage_binding_fingerprint="b" * 64,
    )
    assert compute_operation_fingerprint(**kwargs) == compute_operation_fingerprint(**kwargs)


def test_operation_fingerprint_sensitive_to_semantic_payload() -> None:
    base = dict(
        event_kind=OOSConsumptionEventKind.CLAIMED_FOR_EVALUATION,
        experiment_id="E",
        manifest_hash="a" * 64,
        parent_experiment_id=None,
        root_experiment_id="E",
        oos_start=_dt("2024-01-01"),
        oos_end=_dt("2024-02-01"),
        declared_occurred_at=_dt("2024-01-05"),
        lineage_binding_fingerprint="b" * 64,
    )
    changed_interval = dict(base, oos_end=_dt("2024-03-01"))
    changed_kind = dict(base, event_kind=OOSConsumptionEventKind.OUTCOME_USED)
    assert compute_operation_fingerprint(**base) != compute_operation_fingerprint(**changed_interval)
    assert compute_operation_fingerprint(**base) != compute_operation_fingerprint(**changed_kind)


# --------------------------------------------------------------------------
# Target-reachable lineage resolution (Fix 1) and canonical dedup (Fix 4)
# --------------------------------------------------------------------------


def test_resolver_ignores_unrelated_nodes() -> None:
    target = _manifest("C", parent="P", root="P")
    parent = _manifest("P")
    unrelated_self_parent = _manifest("X", parent="X", root="X")
    unrelated_cycle_a = _manifest("Y", parent="Z", root="Z")
    unrelated_cycle_b = _manifest("Z", parent="Y", root="Y")
    lineage = resolve_target_lineage(
        target,
        (parent, unrelated_self_parent, unrelated_cycle_a, unrelated_cycle_b),
    )
    assert lineage.conflict is False
    assert lineage.missing_ancestor_experiment_id is None
    assert [m.experiment_id for m in lineage.reachable] == ["C", "P"]


def test_resolver_conflict_on_reachable_conflicting_definitions() -> None:
    target = _manifest("C", parent="P", root="P")
    parent_v1 = _manifest("P")
    parent_v2 = ExperimentManifest(
        experiment_id="P",
        schema_version="v1",
        governed_components={"window_configuration": "a" * 64},
        created_at=_dt("2020-01-01T00:00:00"),
        root_experiment_id="P",
        parent_experiment_id=None,
    )
    lineage = resolve_target_lineage(target, (parent_v1, parent_v2))
    assert lineage.conflict is True


def test_resolver_conflict_on_reachable_cycle() -> None:
    target = _manifest("C", parent="P", root="P")
    p = _manifest("P", parent="C", root="C")
    lineage = resolve_target_lineage(target, (p,))
    assert lineage.conflict is True


def test_resolver_missing_ancestor() -> None:
    target = _manifest("C", parent="MISSING", root="MISSING")
    lineage = resolve_target_lineage(target, ())
    assert lineage.conflict is False
    assert lineage.missing_ancestor_experiment_id == "MISSING"
    assert [m.experiment_id for m in lineage.reachable] == ["C"]


def test_lineage_fingerprint_duplicate_and_shuffle_invariant() -> None:
    a = _manifest("A")
    b = _manifest("B", parent="A", root="A")
    c = _manifest("C", parent="B", root="A")
    base = compute_lineage_binding_fingerprint((c, b, a))
    dup = compute_lineage_binding_fingerprint((c, b, b, a, a))
    shuffled = compute_lineage_binding_fingerprint((a, c, b))
    assert base == dup == shuffled


def test_lineage_fingerprint_unrelated_ignored_via_resolver() -> None:
    target = _manifest("C", parent="P", root="P")
    parent = _manifest("P")
    unrelated = _manifest("Q")
    fp_clean = compute_lineage_binding_fingerprint(
        resolve_target_lineage(target, (parent,)).reachable
    )
    fp_with_unrelated = compute_lineage_binding_fingerprint(
        resolve_target_lineage(target, (parent, unrelated)).reachable
    )
    assert fp_clean == fp_with_unrelated


def test_lineage_fingerprint_rejects_conflicting_duplicate() -> None:
    parent_v1 = _manifest("P")
    parent_v2 = ExperimentManifest(
        experiment_id="P",
        schema_version="v1",
        governed_components={"window_configuration": "a" * 64},
        created_at=_dt("2020-01-01T00:00:00"),
        root_experiment_id="P",
        parent_experiment_id=None,
    )
    with pytest.raises(ValueError):
        compute_lineage_binding_fingerprint((parent_v1, parent_v2))


# --------------------------------------------------------------------------
# Domain event view
# --------------------------------------------------------------------------


def test_consumption_event_round_trips_aware_utc() -> None:
    event = OOSConsumptionEvent(
        event_id=1,
        operation_id="op-1",
        experiment_id="E",
        manifest_hash="a" * 64,
        root_experiment_id="E",
        lineage_binding_fingerprint="b" * 64,
        event_kind=OOSConsumptionEventKind.CLAIMED_FOR_EVALUATION,
        oos_interval=_interval("2024-01-01", "2024-02-01"),
        declared_occurred_at=_dt("2024-01-05"),
        recorded_at=_dt("2024-01-06"),
    )
    assert event.oos_interval.start.tzinfo is not None
    assert event.declared_occurred_at.tzinfo is not None
    assert event.recorded_at.tzinfo is not None


def test_no_reset_delete_unburn_public_api() -> None:
    forbidden = ("reset", "delete", "unconsume", "unburn", "force_pristine", "update_state")
    from src.repositories.oos_consumption_ledger_repo import OOSConsumptionLedgerRepository

    for member in inspect.getmembers(OOSConsumptionLedgerRepository):
        name = member[0]
        assert not any(token in name.lower() for token in forbidden), f"forbidden API surface: {name}"
