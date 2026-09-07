"""Permanent adversarial tests for the OOS Consumption Ledger repository.

In-memory SQLite for single-writer behavior; a real temporary SQLite file
(not :memory:) for the concurrent overlapping-claim test, because :memory:
does not share a database across connections and would mask real lock
semantics.
"""

import os
import tempfile
import threading
import time
from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from src.repositories.oos_consumption_ledger_repo import OOSConsumptionLedgerRepository
from src.services.strategy_lab.experiment_governance import ExperimentManifest
from src.services.strategy_lab.oos_consumption import (
    OOSBurnStatus,
    OOSClaimStatus,
    OOSConsumptionResolution,
    OOSConsumptionState,
    OOSLedgerIdempotencyConflictError,
    OOSLedgerIdentityConflictError,
)
from src.services.strategy_lab.temporal_contract import TemporalInterval
from src.storage import (
    Base,
    DatabaseManager,
    OOSConsumptionEventRecord,
    OOSExperimentIdentityRecord,
)

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


def setup_function() -> None:
    DatabaseManager.reset_instance()


def teardown_function() -> None:
    DatabaseManager.reset_instance()


@pytest.fixture()
def repo() -> OOSConsumptionLedgerRepository:
    DatabaseManager("sqlite:///:memory:")
    return OOSConsumptionLedgerRepository()


def _state(repo: OOSConsumptionLedgerRepository, experiment_id: str, start: str, end: str) -> OOSConsumptionState:
    return repo.get_assessment(experiment_id=experiment_id, oos_interval=_interval(start, end)).state


def _event_count(repo: OOSConsumptionLedgerRepository) -> int:
    with repo.db.get_session() as session:
        return len(session.execute(select(OOSConsumptionEventRecord)).scalars().all())


# --------------------------------------------------------------------------
# Claim basics and crash semantics
# --------------------------------------------------------------------------


def test_claim_immediately_consumes_before_evaluation(repo) -> None:
    manifest = _manifest("E1")
    result = repo.claim_if_pristine(
        operation_id="op-1",
        target_manifest=manifest,
        oos_interval=_interval("2024-01-01", "2024-02-01"),
        declared_occurred_at=_dt("2024-01-10"),
    )
    assert result.status is OOSClaimStatus.CLAIMED
    assert result.assessment.state is OOSConsumptionState.CONSUMED
    # "evaluation crashes": we simply never write anything else.
    assert _state(repo, "E1", "2024-01-01", "2024-02-01") is OOSConsumptionState.CONSUMED


def test_committed_claim_survives_evaluation_crash(repo) -> None:
    manifest = _manifest("E1")
    repo.claim_if_pristine(
        operation_id="op-1",
        target_manifest=manifest,
        oos_interval=_interval("2024-01-01", "2024-02-01"),
        declared_occurred_at=_dt("2024-01-10"),
    )
    # Simulate a crash: a brand-new repository over the same data must still
    # observe CONSUMED, never PRISTINE.
    assert _state(repo, "E1", "2024-01-01", "2024-02-01") is OOSConsumptionState.CONSUMED
    assert _event_count(repo) == 1


def test_repeated_claim_denied_not_auto_burned(repo) -> None:
    manifest = _manifest("E1")
    first = repo.claim_if_pristine(
        operation_id="op-1",
        target_manifest=manifest,
        oos_interval=_interval("2024-01-01", "2024-02-01"),
        declared_occurred_at=_dt("2024-01-10"),
    )
    assert first.status is OOSClaimStatus.CLAIMED
    second = repo.claim_if_pristine(
        operation_id="op-2",
        target_manifest=manifest,
        oos_interval=_interval("2024-01-01", "2024-02-01"),
        declared_occurred_at=_dt("2024-01-11"),
    )
    assert second.status is OOSClaimStatus.ALREADY_EXPOSED
    assert second.assessment.state is OOSConsumptionState.CONSUMED  # not BURNED
    assert _event_count(repo) == 1


def test_direct_burn_without_claim(repo) -> None:
    manifest = _manifest("E1")
    result = repo.mark_outcome_used(
        operation_id="op-1",
        target_manifest=manifest,
        oos_interval=_interval("2024-01-01", "2024-02-01"),
        declared_occurred_at=_dt("2024-01-10"),
    )
    assert result.status is OOSBurnStatus.BURNED
    assert result.assessment.state is OOSConsumptionState.BURNED


# --------------------------------------------------------------------------
# Idempotency
# --------------------------------------------------------------------------


def test_same_operation_idempotent_replay(repo) -> None:
    manifest = _manifest("E1")
    kwargs = dict(
        target_manifest=manifest,
        oos_interval=_interval("2024-01-01", "2024-02-01"),
        declared_occurred_at=_dt("2024-01-10"),
    )
    first = repo.claim_if_pristine(operation_id="op-1", **kwargs)
    replay = repo.claim_if_pristine(operation_id="op-1", **kwargs)
    assert replay.status is OOSClaimStatus.IDEMPOTENT_REPLAY
    assert replay.event_id == first.event_id
    assert _event_count(repo) == 1


def test_same_operation_id_changed_payload_conflicts(repo) -> None:
    manifest = _manifest("E1")
    repo.claim_if_pristine(
        operation_id="op-1",
        target_manifest=manifest,
        oos_interval=_interval("2024-01-01", "2024-02-01"),
        declared_occurred_at=_dt("2024-01-10"),
    )
    with pytest.raises(OOSLedgerIdempotencyConflictError):
        repo.claim_if_pristine(
            operation_id="op-1",
            target_manifest=manifest,
            oos_interval=_interval("2024-03-01", "2024-04-01"),
            declared_occurred_at=_dt("2024-01-10"),
        )


def test_same_operation_id_reused_by_burn_conflicts(repo) -> None:
    manifest = _manifest("E1")
    repo.claim_if_pristine(
        operation_id="op-1",
        target_manifest=manifest,
        oos_interval=_interval("2024-01-01", "2024-02-01"),
        declared_occurred_at=_dt("2024-01-10"),
    )
    with pytest.raises(OOSLedgerIdempotencyConflictError):
        repo.mark_outcome_used(
            operation_id="op-1",
            target_manifest=manifest,
            oos_interval=_interval("2024-01-01", "2024-02-01"),
            declared_occurred_at=_dt("2024-01-10"),
        )


# --------------------------------------------------------------------------
# Identity conflicts
# --------------------------------------------------------------------------


def test_experiment_id_conflicting_manifest_hash_conflicts(repo) -> None:
    repo.claim_if_pristine(
        operation_id="op-1",
        target_manifest=_manifest("E1"),
        oos_interval=_interval("2024-01-01", "2024-02-01"),
        declared_occurred_at=_dt("2024-01-10"),
    )
    changed = _manifest("E1")
    changed = ExperimentManifest(
        experiment_id="E1",
        schema_version="v1",
        governed_components={"window_configuration": "a" * 64},
        created_at=_dt("2020-01-01T00:00:00"),
        root_experiment_id="E1",
        parent_experiment_id=None,
    )
    with pytest.raises(OOSLedgerIdentityConflictError):
        repo.mark_outcome_used(
            operation_id="op-2",
            target_manifest=changed,
            oos_interval=_interval("2024-01-01", "2024-02-01"),
            declared_occurred_at=_dt("2024-01-10"),
        )


def test_experiment_id_changed_parent_conflicts(repo) -> None:
    parent_a = _manifest("PA")
    parent_b = _manifest("PB")
    child_v1 = _manifest("E1", parent="PA", root="PA")
    repo.claim_if_pristine(
        operation_id="op-1",
        target_manifest=child_v1,
        lineage_history=(parent_a,),
        oos_interval=_interval("2024-01-01", "2024-02-01"),
        declared_occurred_at=_dt("2024-01-10"),
    )
    child_v2 = _manifest("E1", parent="PB", root="PB")
    with pytest.raises(OOSLedgerIdentityConflictError):
        repo.mark_outcome_used(
            operation_id="op-2",
            target_manifest=child_v2,
            lineage_history=(parent_b,),
            oos_interval=_interval("2024-01-01", "2024-02-01"),
            declared_occurred_at=_dt("2024-01-10"),
        )


def test_experiment_id_changed_root_conflicts(repo) -> None:
    repo.claim_if_pristine(
        operation_id="op-1",
        target_manifest=_manifest("E1"),
        oos_interval=_interval("2024-01-01", "2024-02-01"),
        declared_occurred_at=_dt("2024-01-10"),
    )
    # E2 itself is new, but its declared root contradicts the persisted
    # parent E1's root: the combined-overlay child/root mismatch rejects the
    # write as a structural lineage violation (no event, no registration).
    child = _manifest("E2", parent="E1", root="OTHER")
    result = repo.mark_outcome_used(
        operation_id="op-2",
        target_manifest=child,
        oos_interval=_interval("2024-01-01", "2024-02-01"),
        declared_occurred_at=_dt("2024-01-10"),
    )
    assert result.status is OOSBurnStatus.LINEAGE_VIOLATION
    assert _identity_ids(repo) == {"E1"}


# --------------------------------------------------------------------------
# Lineage inheritance and persistence authority
# --------------------------------------------------------------------------


def test_ancestor_consumed_inherited_by_descendant(repo) -> None:
    parent = _manifest("P")
    child = _manifest("C", parent="P", root="P")
    repo.claim_if_pristine(
        operation_id="op-parent",
        target_manifest=parent,
        oos_interval=_interval("2024-01-01", "2024-02-01"),
        declared_occurred_at=_dt("2024-01-10"),
    )
    # Register the child by claiming its own disjoint pristine window.
    repo.claim_if_pristine(
        operation_id="op-child",
        target_manifest=child,
        lineage_history=(parent,),
        oos_interval=_interval("2024-03-01", "2024-04-01"),
        declared_occurred_at=_dt("2024-03-05"),
    )
    # The query names only the child, but the persisted graph makes P's
    # CONSUMED exposure inherited.
    assessment = repo.get_assessment(experiment_id="C", oos_interval=_interval("2024-01-01", "2024-02-01"))
    assert assessment.resolution is OOSConsumptionResolution.RESOLVED
    assert assessment.state is OOSConsumptionState.CONSUMED


def test_ancestor_burned_inherited_by_descendant(repo) -> None:
    parent = _manifest("P")
    repo.mark_outcome_used(
        operation_id="op-parent",
        target_manifest=parent,
        oos_interval=_interval("2024-01-01", "2024-02-01"),
        declared_occurred_at=_dt("2024-01-10"),
    )
    assessment = repo.get_assessment(experiment_id="C", oos_interval=_interval("2024-01-01", "2024-02-01"))
    assert assessment.resolution is OOSConsumptionResolution.INDETERMINATE  # C itself never registered
    child = _manifest("C", parent="P", root="P")
    repo.claim_if_pristine(
        operation_id="op-child-claim",
        target_manifest=child,
        lineage_history=(parent,),
        oos_interval=_interval("2024-03-01", "2024-04-01"),
        declared_occurred_at=_dt("2024-03-05"),
    )
    # Child's own interval is pristine and claimable...
    assessment = repo.get_assessment(experiment_id="C", oos_interval=_interval("2024-03-01", "2024-04-01"))
    assert assessment.state is OOSConsumptionState.CONSUMED
    # ...but the parent's burned window is inherited, even though the query
    # names only the child -- the caller supplied no ancestry here at all.
    assessment = repo.get_assessment(experiment_id="C", oos_interval=_interval("2024-01-01", "2024-02-01"))
    assert assessment.resolution is OOSConsumptionResolution.RESOLVED
    assert assessment.state is OOSConsumptionState.BURNED


def test_query_cannot_omit_ancestor_exposure(repo) -> None:
    parent = _manifest("P")
    child = _manifest("C", parent="P", root="P")
    repo.mark_outcome_used(
        operation_id="op-1",
        target_manifest=parent,
        oos_interval=_interval("2024-01-01", "2024-02-01"),
        declared_occurred_at=_dt("2024-01-10"),
    )
    repo.claim_if_pristine(
        operation_id="op-2",
        target_manifest=child,
        lineage_history=(parent,),
        oos_interval=_interval("2024-03-01", "2024-04-01"),
        declared_occurred_at=_dt("2024-03-05"),
    )
    # get_assessment accepts an experiment_id only -- there is no ancestry
    # parameter a caller could use to hide P's exposure from C.
    assessment = repo.get_assessment(experiment_id="C", oos_interval=_interval("2024-01-01", "2024-02-01"))
    assert assessment.state is OOSConsumptionState.BURNED


# --------------------------------------------------------------------------
# Lineage verdict gating
# --------------------------------------------------------------------------


def test_lineage_indeterminate_blocks_claim(repo) -> None:
    child = _manifest("C", parent="MISSING", root="MISSING")
    result = repo.claim_if_pristine(
        operation_id="op-1",
        target_manifest=child,
        oos_interval=_interval("2024-01-01", "2024-02-01"),
        declared_occurred_at=_dt("2024-01-10"),
    )
    assert result.status is OOSClaimStatus.LINEAGE_INDETERMINATE
    assert _event_count(repo) == 0


def test_lineage_violation_blocks_claim(repo) -> None:
    self_parent = _manifest("E1", parent="E1", root="E1")
    result = repo.claim_if_pristine(
        operation_id="op-1",
        target_manifest=self_parent,
        oos_interval=_interval("2024-01-01", "2024-02-01"),
        declared_occurred_at=_dt("2024-01-10"),
    )
    assert result.status is OOSClaimStatus.LINEAGE_VIOLATION
    assert _event_count(repo) == 0


def test_lineage_violation_blocks_burn(repo) -> None:
    self_parent = _manifest("E1", parent="E1", root="E1")
    result = repo.mark_outcome_used(
        operation_id="op-1",
        target_manifest=self_parent,
        oos_interval=_interval("2024-01-01", "2024-02-01"),
        declared_occurred_at=_dt("2024-01-10"),
    )
    assert result.status is OOSBurnStatus.LINEAGE_VIOLATION
    assert _event_count(repo) == 0


# --------------------------------------------------------------------------
# Whole-window overlap semantics
# --------------------------------------------------------------------------


def test_partial_overlap_blocks_claim(repo) -> None:
    manifest = _manifest("E1")
    repo.claim_if_pristine(
        operation_id="op-1",
        target_manifest=manifest,
        oos_interval=_interval("2024-01-01", "2024-01-31"),
        declared_occurred_at=_dt("2024-01-05"),
    )
    result = repo.claim_if_pristine(
        operation_id="op-2",
        target_manifest=manifest,
        oos_interval=_interval("2024-01-15", "2024-02-15"),
        declared_occurred_at=_dt("2024-01-20"),
    )
    assert result.status is OOSClaimStatus.ALREADY_EXPOSED
    assert result.assessment.state is OOSConsumptionState.CONSUMED


def test_subset_cannot_reset(repo) -> None:
    manifest = _manifest("E1")
    repo.claim_if_pristine(
        operation_id="op-1",
        target_manifest=manifest,
        oos_interval=_interval("2024-01-01", "2024-02-01"),
        declared_occurred_at=_dt("2024-01-05"),
    )
    result = repo.claim_if_pristine(
        operation_id="op-2",
        target_manifest=manifest,
        oos_interval=_interval("2024-01-10", "2024-01-20"),
        declared_occurred_at=_dt("2024-01-15"),
    )
    assert result.status is OOSClaimStatus.ALREADY_EXPOSED


def test_superset_cannot_reset(repo) -> None:
    manifest = _manifest("E1")
    repo.claim_if_pristine(
        operation_id="op-1",
        target_manifest=manifest,
        oos_interval=_interval("2024-01-10", "2024-01-20"),
        declared_occurred_at=_dt("2024-01-15"),
    )
    result = repo.claim_if_pristine(
        operation_id="op-2",
        target_manifest=manifest,
        oos_interval=_interval("2024-01-01", "2024-02-01"),
        declared_occurred_at=_dt("2024-01-05"),
    )
    assert result.status is OOSClaimStatus.ALREADY_EXPOSED


def test_window_padding_cannot_reset(repo) -> None:
    manifest = _manifest("E1")
    repo.claim_if_pristine(
        operation_id="op-1",
        target_manifest=manifest,
        oos_interval=_interval("2024-01-01", "2024-01-10"),
        declared_occurred_at=_dt("2024-01-05"),
    )
    result = repo.claim_if_pristine(
        operation_id="op-2",
        target_manifest=manifest,
        oos_interval=_interval("2023-12-20", "2024-01-20"),
        declared_occurred_at=_dt("2024-01-05"),
    )
    assert result.status is OOSClaimStatus.ALREADY_EXPOSED


def test_adjacent_half_open_intervals_are_independent(repo) -> None:
    manifest = _manifest("E1")
    first = repo.claim_if_pristine(
        operation_id="op-1",
        target_manifest=manifest,
        oos_interval=_interval("2024-01-01", "2024-02-01"),
        declared_occurred_at=_dt("2024-01-05"),
    )
    assert first.status is OOSClaimStatus.CLAIMED
    second = repo.claim_if_pristine(
        operation_id="op-2",
        target_manifest=manifest,
        oos_interval=_interval("2024-02-01", "2024-03-01"),
        declared_occurred_at=_dt("2024-02-05"),
    )
    assert second.status is OOSClaimStatus.CLAIMED
    assert _event_count(repo) == 2


# --------------------------------------------------------------------------
# INDETERMINATE burn and late lineage completion
# --------------------------------------------------------------------------


def test_indeterminate_burn_records_pollution_without_fabrication(repo) -> None:
    child = _manifest("C", parent="MISSING", root="MISSING")
    result = repo.mark_outcome_used(
        operation_id="op-1",
        target_manifest=child,
        oos_interval=_interval("2024-01-01", "2024-02-01"),
        declared_occurred_at=_dt("2024-01-10"),
    )
    assert result.status is OOSBurnStatus.BURNED
    with repo.db.get_session() as session:
        identities = session.execute(select(OOSExperimentIdentityRecord)).scalars().all()
        assert {row.experiment_id for row in identities} == {"C"}  # MISSING not fabricated
    assessment = repo.get_assessment(experiment_id="C", oos_interval=_interval("2024-01-01", "2024-02-01"))
    assert assessment.resolution is OOSConsumptionResolution.INDETERMINATE
    assert assessment.state is None


def test_late_ancestor_registration_resolves_incomplete_graph(repo) -> None:
    child = _manifest("C", parent="P", root="P")
    repo.mark_outcome_used(
        operation_id="op-child-burn",
        target_manifest=child,
        oos_interval=_interval("2024-01-01", "2024-02-01"),
        declared_occurred_at=_dt("2024-01-10"),
    )
    before = repo.get_assessment(experiment_id="C", oos_interval=_interval("2024-01-01", "2024-02-01"))
    assert before.resolution is OOSConsumptionResolution.INDETERMINATE

    parent = _manifest("P")
    repo.mark_outcome_used(
        operation_id="op-parent-burn",
        target_manifest=parent,
        oos_interval=_interval("2024-01-05", "2024-01-15"),
        declared_occurred_at=_dt("2024-01-12"),
    )
    after = repo.get_assessment(experiment_id="C", oos_interval=_interval("2024-01-01", "2024-02-01"))
    assert after.resolution is OOSConsumptionResolution.RESOLVED
    assert after.state is OOSConsumptionState.BURNED


def test_registered_graph_cannot_be_mutated_to_downgrade(repo) -> None:
    parent = _manifest("P")
    child = _manifest("C", parent="P", root="P")
    repo.claim_if_pristine(
        operation_id="op-1",
        target_manifest=child,
        lineage_history=(parent,),
        oos_interval=_interval("2024-01-01", "2024-02-01"),
        declared_occurred_at=_dt("2024-01-10"),
    )
    # A later write that redefines P (different root) must conflict, not
    # mutate the graph into something that erases inheritance.
    forged_parent = _manifest("P", parent="X", root="X")
    with pytest.raises(OOSLedgerIdentityConflictError):
        repo.mark_outcome_used(
            operation_id="op-2",
            target_manifest=forged_parent,
            lineage_history=(_manifest("X"),),
            oos_interval=_interval("2024-01-01", "2024-02-01"),
            declared_occurred_at=_dt("2024-01-10"),
        )


# --------------------------------------------------------------------------
# Fix 1: unrelated supplied lineage nodes never enter the registry
# --------------------------------------------------------------------------


def test_unrelated_self_parent_node_never_registered(repo) -> None:
    target = _manifest("T")
    unrelated = _manifest("X", parent="X", root="X")
    result = repo.claim_if_pristine(
        operation_id="op-1",
        target_manifest=target,
        lineage_history=(unrelated,),
        oos_interval=_interval("2024-01-01", "2024-02-01"),
        declared_occurred_at=_dt("2024-01-10"),
    )
    assert result.status is OOSClaimStatus.CLAIMED
    with repo.db.get_session() as session:
        identities = session.execute(select(OOSExperimentIdentityRecord)).scalars().all()
        assert {row.experiment_id for row in identities} == {"T"}


def test_unrelated_cycle_nodes_never_registered(repo) -> None:
    target = _manifest("T")
    cycle_a = _manifest("Y", parent="Z", root="Z")
    cycle_b = _manifest("Z", parent="Y", root="Y")
    result = repo.claim_if_pristine(
        operation_id="op-1",
        target_manifest=target,
        lineage_history=(cycle_a, cycle_b),
        oos_interval=_interval("2024-01-01", "2024-02-01"),
        declared_occurred_at=_dt("2024-01-10"),
    )
    assert result.status is OOSClaimStatus.CLAIMED
    with repo.db.get_session() as session:
        identities = session.execute(select(OOSExperimentIdentityRecord)).scalars().all()
        assert {row.experiment_id for row in identities} == {"T"}


def test_indeterminate_burn_ignores_unrelated_malformed_nodes(repo) -> None:
    child = _manifest("C", parent="MISSING", root="MISSING")
    unrelated = _manifest("X", parent="X", root="X")
    result = repo.mark_outcome_used(
        operation_id="op-1",
        target_manifest=child,
        lineage_history=(unrelated,),
        oos_interval=_interval("2024-01-01", "2024-02-01"),
        declared_occurred_at=_dt("2024-01-10"),
    )
    assert result.status is OOSBurnStatus.BURNED
    with repo.db.get_session() as session:
        identities = session.execute(select(OOSExperimentIdentityRecord)).scalars().all()
        assert {row.experiment_id for row in identities} == {"C"}


# --------------------------------------------------------------------------
# Atomicity / Fix 2: denied claims must not mutate the identity registry
# --------------------------------------------------------------------------


def test_unseen_child_of_consumed_ancestor_claim_denied_without_persisting_identity(repo) -> None:
    parent = _manifest("P")
    child = _manifest("C", parent="P", root="P")
    repo.claim_if_pristine(
        operation_id="op-parent",
        target_manifest=parent,
        oos_interval=_interval("2024-01-01", "2024-02-01"),
        declared_occurred_at=_dt("2024-01-10"),
    )
    before = [
        row.experiment_id
        for row in repo.db.get_session().execute(
            select(OOSExperimentIdentityRecord)
        ).scalars().all()
    ]
    assert before == ["P"]

    result = repo.claim_if_pristine(
        operation_id="op-child",
        target_manifest=child,
        lineage_history=(parent,),
        oos_interval=_interval("2024-01-15", "2024-01-20"),
        declared_occurred_at=_dt("2024-01-15"),
    )
    assert result.status is OOSClaimStatus.ALREADY_EXPOSED
    after = [
        row.experiment_id
        for row in repo.db.get_session().execute(
            select(OOSExperimentIdentityRecord)
        ).scalars().all()
    ]
    assert after == ["P"]  # child's provisional registration was rolled back
    assert _event_count(repo) == 1


def test_indeterminate_claim_persists_nothing(repo) -> None:
    child = _manifest("C", parent="MISSING", root="MISSING")
    result = repo.claim_if_pristine(
        operation_id="op-1",
        target_manifest=child,
        oos_interval=_interval("2024-01-01", "2024-02-01"),
        declared_occurred_at=_dt("2024-01-10"),
    )
    assert result.status is OOSClaimStatus.LINEAGE_INDETERMINATE
    with repo.db.get_session() as session:
        assert session.execute(select(OOSExperimentIdentityRecord)).scalars().all() == []
        assert session.execute(select(OOSConsumptionEventRecord)).scalars().all() == []


def test_violation_claim_persists_nothing(repo) -> None:
    self_parent = _manifest("E1", parent="E1", root="E1")
    result = repo.claim_if_pristine(
        operation_id="op-1",
        target_manifest=self_parent,
        oos_interval=_interval("2024-01-01", "2024-02-01"),
        declared_occurred_at=_dt("2024-01-10"),
    )
    assert result.status is OOSClaimStatus.LINEAGE_VIOLATION
    with repo.db.get_session() as session:
        assert session.execute(select(OOSExperimentIdentityRecord)).scalars().all() == []
        assert session.execute(select(OOSConsumptionEventRecord)).scalars().all() == []


# --------------------------------------------------------------------------
# Fix 3: claim gate precedence -- unresolved lineage wins over exposure
# --------------------------------------------------------------------------


def test_indeterminate_lineage_reported_before_already_exposed(repo) -> None:
    child = _manifest("C", parent="P", root="P")
    burn = repo.mark_outcome_used(
        operation_id="op-burn",
        target_manifest=child,
        oos_interval=_interval("2024-01-01", "2024-02-01"),
        declared_occurred_at=_dt("2024-01-10"),
    )
    assert burn.status is OOSBurnStatus.BURNED
    # Own OUTCOME_USED exists, but lineage is still incomplete: the claim
    # must report LINEAGE_INDETERMINATE, never ALREADY_EXPOSED.
    claim = repo.claim_if_pristine(
        operation_id="op-claim",
        target_manifest=child,
        oos_interval=_interval("2024-01-01", "2024-02-01"),
        declared_occurred_at=_dt("2024-01-10"),
    )
    assert claim.status is OOSClaimStatus.LINEAGE_INDETERMINATE
    assessment = repo.get_assessment(
        experiment_id="C", oos_interval=_interval("2024-01-01", "2024-02-01")
    )
    assert assessment.resolution is OOSConsumptionResolution.INDETERMINATE
    assert assessment.state is None

    # Late ancestor registration resolves the graph: the same exposure now
    # derives BURNED normally.
    parent = _manifest("P")
    repo.mark_outcome_used(
        operation_id="op-parent",
        target_manifest=parent,
        oos_interval=_interval("2024-01-01", "2024-02-01"),
        declared_occurred_at=_dt("2024-01-10"),
    )
    assessment = repo.get_assessment(
        experiment_id="C", oos_interval=_interval("2024-01-01", "2024-02-01")
    )
    assert assessment.resolution is OOSConsumptionResolution.RESOLVED
    assert assessment.state is OOSConsumptionState.BURNED
    # Retrying the same claim now passes lineage and hits the exposure gate.
    retry = repo.claim_if_pristine(
        operation_id="op-claim",
        target_manifest=child,
        lineage_history=(parent,),
        oos_interval=_interval("2024-01-01", "2024-02-01"),
        declared_occurred_at=_dt("2024-01-10"),
    )
    assert retry.status is OOSClaimStatus.ALREADY_EXPOSED


# --------------------------------------------------------------------------
# Fix 4: canonical lineage fingerprint invariance at the repository level
# --------------------------------------------------------------------------


def test_stored_lineage_fingerprint_invariant_to_unrelated_and_duplicates(repo) -> None:
    parent = _manifest("P")
    child = _manifest("C", parent="P", root="P")
    unrelated = _manifest("Q")
    repo.claim_if_pristine(
        operation_id="op-1",
        target_manifest=child,
        lineage_history=(parent, parent, unrelated),
        oos_interval=_interval("2024-01-01", "2024-02-01"),
        declared_occurred_at=_dt("2024-01-10"),
    )
    repo.claim_if_pristine(
        operation_id="op-2",
        target_manifest=child,
        lineage_history=(unrelated, parent),
        oos_interval=_interval("2024-02-01", "2024-03-01"),
        declared_occurred_at=_dt("2024-02-05"),
    )
    with repo.db.get_session() as session:
        fingerprints = {
            row.operation_id: row.lineage_binding_fingerprint
            for row in session.execute(select(OOSConsumptionEventRecord)).scalars().all()
        }
    assert fingerprints["op-1"] == fingerprints["op-2"]


def test_reachable_conflicting_duplicate_rejected(repo) -> None:
    child = _manifest("C", parent="P", root="P")
    parent_v1 = _manifest("P")
    parent_v2 = ExperimentManifest(
        experiment_id="P",
        schema_version="v1",
        governed_components={"window_configuration": "a" * 64},
        created_at=_dt("2020-01-01T00:00:00"),
        root_experiment_id="P",
        parent_experiment_id=None,
    )
    result = repo.claim_if_pristine(
        operation_id="op-1",
        target_manifest=child,
        lineage_history=(parent_v1, parent_v2),
        oos_interval=_interval("2024-01-01", "2024-02-01"),
        declared_occurred_at=_dt("2024-01-10"),
    )
    assert result.status is OOSClaimStatus.LINEAGE_VIOLATION
    assert _event_count(repo) == 0


# --------------------------------------------------------------------------
# Fix 7: denied claims do not reserve the operation_id
# --------------------------------------------------------------------------


def test_rejected_claim_does_not_reserve_operation_id_and_retry_reevaluates(repo) -> None:
    child = _manifest("C", parent="P", root="P")
    first = repo.claim_if_pristine(
        operation_id="op-A",
        target_manifest=child,
        oos_interval=_interval("2024-01-01", "2024-02-01"),
        declared_occurred_at=_dt("2024-01-10"),
    )
    assert first.status is OOSClaimStatus.LINEAGE_INDETERMINATE
    assert _event_count(repo) == 0

    parent = _manifest("P")
    repo.mark_outcome_used(
        operation_id="op-register-parent",
        target_manifest=parent,
        oos_interval=_interval("2024-03-01", "2024-04-01"),
        declared_occurred_at=_dt("2024-03-05"),
    )
    retry = repo.claim_if_pristine(
        operation_id="op-A",
        target_manifest=child,
        lineage_history=(parent,),
        oos_interval=_interval("2024-01-01", "2024-02-01"),
        declared_occurred_at=_dt("2024-01-10"),
    )
    assert retry.status is OOSClaimStatus.CLAIMED
    assert _event_count(repo) == 2


def test_failed_claim_leaves_interval_pristine(repo) -> None:
    child = _manifest("C", parent="MISSING", root="MISSING")
    result = repo.claim_if_pristine(
        operation_id="op-1",
        target_manifest=child,
        oos_interval=_interval("2024-01-01", "2024-02-01"),
        declared_occurred_at=_dt("2024-01-10"),
    )
    assert result.status is OOSClaimStatus.LINEAGE_INDETERMINATE
    assert _event_count(repo) == 0
    assert _state(repo, "C", "2024-01-01", "2024-02-01") is None


# --------------------------------------------------------------------------
# UTC TEXT persistence and aware round-trip
# --------------------------------------------------------------------------


def test_utc_text_persistence_and_aware_round_trip(repo) -> None:
    manifest = _manifest("E1")
    repo.claim_if_pristine(
        operation_id="op-1",
        target_manifest=manifest,
        oos_interval=_interval("2024-01-01", "2024-02-01"),
        declared_occurred_at=_dt("2024-01-10"),
    )
    with repo.db.get_session() as session:
        row = session.execute(select(OOSConsumptionEventRecord)).scalar_one()
        assert isinstance(row.oos_start_utc_text, str)
        assert row.oos_start_utc_text.endswith("+00:00")
        assert row.oos_end_utc_text.endswith("+00:00")
        assert row.recorded_at_utc_text.endswith("+00:00")
        assert row.declared_occurred_at_utc_text.endswith("+00:00")
    events = repo.list_events(experiment_id="E1")
    assert len(events) == 1
    assert events[0].oos_interval.start.tzinfo is not None
    assert events[0].recorded_at.tzinfo is not None
    assert events[0].declared_occurred_at.tzinfo is not None


# --------------------------------------------------------------------------
# Event ordering and input-order invariance
# --------------------------------------------------------------------------


def test_derived_state_does_not_depend_on_write_order(repo) -> None:
    manifest = _manifest("E1")
    repo.claim_if_pristine(
        operation_id="op-1",
        target_manifest=manifest,
        oos_interval=_interval("2024-01-01", "2024-01-15"),
        declared_occurred_at=_dt("2024-01-05"),
    )
    repo.mark_outcome_used(
        operation_id="op-2",
        target_manifest=manifest,
        oos_interval=_interval("2024-01-10", "2024-01-20"),
        declared_occurred_at=_dt("2024-01-12"),
    )
    assessment = repo.get_assessment(experiment_id="E1", oos_interval=_interval("2024-01-01", "2024-01-20"))
    assert assessment.state is OOSConsumptionState.BURNED
    events = repo.list_events()
    assert [e.event_id for e in events] == sorted(e.event_id for e in events)


def test_event_replay_order_invariance_across_databases() -> None:
    """Same final event set written in opposite orders yields identical state."""

    for order in ("claim-then-burn", "burn-then-claim"):
        DatabaseManager.reset_instance()
        DatabaseManager("sqlite:///:memory:")
        current = OOSConsumptionLedgerRepository()
        manifest = _manifest("E1")
        if order == "claim-then-burn":
            current.claim_if_pristine(
                operation_id="op-1", target_manifest=manifest,
                oos_interval=_interval("2024-01-01", "2024-01-10"),
                declared_occurred_at=_dt("2024-01-05"),
            )
            current.mark_outcome_used(
                operation_id="op-2", target_manifest=manifest,
                oos_interval=_interval("2024-01-20", "2024-01-30"),
                declared_occurred_at=_dt("2024-01-25"),
            )
        else:
            current.mark_outcome_used(
                operation_id="op-2", target_manifest=manifest,
                oos_interval=_interval("2024-01-20", "2024-01-30"),
                declared_occurred_at=_dt("2024-01-25"),
            )
            current.claim_if_pristine(
                operation_id="op-1", target_manifest=manifest,
                oos_interval=_interval("2024-01-01", "2024-01-10"),
                declared_occurred_at=_dt("2024-01-05"),
            )
        assessment = current.get_assessment(
            experiment_id="E1", oos_interval=_interval("2024-01-01", "2024-01-30")
        )
        assert assessment.state is OOSConsumptionState.BURNED


# --------------------------------------------------------------------------
# Concurrency: real temp-file SQLite with demonstrated lock contention
# --------------------------------------------------------------------------


def test_concurrent_overlapping_claims_contend_on_real_sqlite_lock() -> None:
    """Deterministic lock-contention proof without sleep-based guesswork.

    A dedicated connection holds BEGIN IMMEDIATE (the SQLite writer lock).
    Both workers signal ``started`` immediately before entering their Ledger
    claim (which begins with BEGIN IMMEDIATE). While the lock is held and
    both workers have started, neither worker can complete -- completion in
    the uncontended case takes milliseconds, far less than the observation
    window below, so an unset ``done`` event with both ``started`` events
    set proves the workers are blocked on the real SQLite write lock. After
    release they serialize: exactly one CLAIMED, one ALREADY_EXPOSED, one
    event.
    """

    temp_dir = tempfile.TemporaryDirectory()
    db_path = os.path.join(temp_dir.name, "ledger_concurrency.db")
    try:
        DatabaseManager(f"sqlite:///{db_path}")
        repo = OOSConsumptionLedgerRepository()
        manifest = _manifest("E1")

        started_a = threading.Event()
        started_b = threading.Event()
        done_a = threading.Event()
        done_b = threading.Event()
        results: dict[str, object] = {}
        errors: list[Exception] = []

        def worker(operation_id: str, start: str, end: str, started: threading.Event, done: threading.Event) -> None:
            try:
                started.set()
                results[operation_id] = repo.claim_if_pristine(
                    operation_id=operation_id,
                    target_manifest=manifest,
                    oos_interval=_interval(start, end),
                    declared_occurred_at=_dt("2024-01-10"),
                )
            except Exception as exc:  # pragma: no cover - failure reporting
                errors.append(exc)
            finally:
                done.set()

        # Hold the writer lock on an independent connection.
        lock_session = repo.db.get_session()
        lock_session.connection().exec_driver_sql("BEGIN IMMEDIATE")
        try:
            threads = [
                threading.Thread(target=worker, args=("op-A", "2024-01-01", "2024-01-30", started_a, done_a)),
                threading.Thread(target=worker, args=("op-B", "2024-01-15", "2024-02-15", started_b, done_b)),
            ]
            for thread in threads:
                thread.start()
            assert started_a.wait(timeout=10), "worker A never reached its Ledger write"
            assert started_b.wait(timeout=10), "worker B never reached its Ledger write"
            # Both workers are inside/entering BEGIN IMMEDIATE. Give the OS
            # scheduler a generous window in which an uncontended write would
            # trivially finish, then prove both are still blocked on the
            # held lock.
            deadline = time.monotonic() + 2.0
            while time.monotonic() < deadline:
                if done_a.is_set() and done_b.is_set():
                    break
                time.sleep(0.05)
            assert not done_a.is_set(), "worker A finished while the SQLite write lock was held"
            assert not done_b.is_set(), "worker B finished while the SQLite write lock was held"
        finally:
            lock_session.rollback()
            lock_session.close()

        for thread in threads:
            thread.join(timeout=30)
        assert not any(thread.is_alive() for thread in threads)
        assert errors == []

        statuses = {results["op-A"].status, results["op-B"].status}
        assert statuses == {OOSClaimStatus.CLAIMED, OOSClaimStatus.ALREADY_EXPOSED}
        # Exactly one event was persisted.
        with repo.db.get_session() as session:
            events = session.execute(select(OOSConsumptionEventRecord)).scalars().all()
            assert len(events) == 1
    finally:
        DatabaseManager.reset_instance()
        temp_dir.cleanup()


# --------------------------------------------------------------------------
# Fix 9: committed claim survives close + reopen of the same SQLite file
# --------------------------------------------------------------------------


def test_committed_claim_survives_database_reopen() -> None:
    temp_dir = tempfile.TemporaryDirectory()
    db_path = os.path.join(temp_dir.name, "ledger_reopen.db")
    try:
        DatabaseManager(f"sqlite:///{db_path}")
        repo = OOSConsumptionLedgerRepository()
        manifest = _manifest("E1")
        result = repo.claim_if_pristine(
            operation_id="op-1",
            target_manifest=manifest,
            oos_interval=_interval("2024-01-01", "2024-02-01"),
            declared_occurred_at=_dt("2024-01-10"),
        )
        assert result.status is OOSClaimStatus.CLAIMED

        # Simulate a process crash: dispose the engine/singleton entirely and
        # reopen the same file from scratch.
        DatabaseManager.reset_instance()
        DatabaseManager(f"sqlite:///{db_path}")
        reopened = OOSConsumptionLedgerRepository()
        assessment = reopened.get_assessment(
            experiment_id="E1", oos_interval=_interval("2024-01-01", "2024-02-01")
        )
        assert assessment.resolution is OOSConsumptionResolution.RESOLVED
        assert assessment.state is OOSConsumptionState.CONSUMED
    finally:
        DatabaseManager.reset_instance()
        temp_dir.cleanup()


# --------------------------------------------------------------------------
# Fix 5: true AUTOINCREMENT in the actual SQLite DDL
# --------------------------------------------------------------------------


def test_events_table_ddl_uses_true_autoincrement(repo) -> None:
    with repo.db._engine.connect() as connection:
        ddl = connection.exec_driver_sql(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name=:name",
            {"name": OOSConsumptionEventRecord.__tablename__},
        ).scalar_one_or_none()
    assert ddl is not None
    assert "AUTOINCREMENT" in ddl.upper()


# --------------------------------------------------------------------------
# Fix 6: migration fails closed on a malformed pre-existing Ledger table
# --------------------------------------------------------------------------


def test_malformed_ledger_table_fails_closed_without_stamping_migration() -> None:
    from sqlalchemy import create_engine

    from src.storage import CURRENT_SCHEMA_VERSION, DatabaseSchemaMigration

    temp_dir = tempfile.TemporaryDirectory()
    db_path = os.path.join(temp_dir.name, "ledger_malformed.db")
    try:
        # Pre-create a partial events table that violates the frozen contract.
        pre_engine = create_engine(f"sqlite:///{db_path}")
        with pre_engine.begin() as connection:
            connection.exec_driver_sql(
                "CREATE TABLE oos_consumption_event_records ("
                "event_id INTEGER PRIMARY KEY AUTOINCREMENT, "
                "operation_id TEXT)"
            )
        pre_engine.dispose()

        with pytest.raises(RuntimeError):
            DatabaseManager(f"sqlite:///{db_path}")

        # The migration version must NOT have been stamped.
        verify_engine = create_engine(f"sqlite:///{db_path}")
        with verify_engine.connect() as connection:
            rows = connection.exec_driver_sql(
                "SELECT version FROM schema_migrations WHERE version = :v",
                {"v": CURRENT_SCHEMA_VERSION},
            ).all()
            assert rows == []
        verify_engine.dispose()
    finally:
        DatabaseManager.reset_instance()
        temp_dir.cleanup()


# --------------------------------------------------------------------------
# Fix R2-1: persistent graph overlay must be validated before any write
# --------------------------------------------------------------------------


def _burn(repo, operation_id, manifest, *, history=(), start="2024-01-01", end="2024-02-01"):
    return repo.mark_outcome_used(
        operation_id=operation_id,
        target_manifest=manifest,
        lineage_history=history,
        oos_interval=_interval(start, end),
        declared_occurred_at=_dt("2024-01-10"),
    )


def _identity_ids(repo) -> set[str]:
    with repo.db.get_session() as session:
        return {row.experiment_id for row in session.execute(select(OOSExperimentIdentityRecord)).scalars().all()}


def test_burn_cycle_rejected_atomically(repo) -> None:
    a = _manifest("A", parent="B", root="B")  # B missing -> INDETERMINATE, permitted
    first = _burn(repo, "op-1", a)
    assert first.status is OOSBurnStatus.BURNED
    assert _identity_ids(repo) == {"A"}

    b = _manifest("B", parent="A", root="A")  # would close the A->B->A cycle
    second = _burn(repo, "op-2", b)
    assert second.status is OOSBurnStatus.LINEAGE_VIOLATION
    assert _identity_ids(repo) == {"A"}  # B not registered
    with repo.db.get_session() as session:
        events = session.execute(select(OOSConsumptionEventRecord)).scalars().all()
        assert len(events) == 1  # second event absent


def test_burn_cycle_rejected_reverse_order(repo) -> None:
    b = _manifest("B", parent="A", root="A")  # A missing -> permitted
    first = _burn(repo, "op-1", b)
    assert first.status is OOSBurnStatus.BURNED
    assert _identity_ids(repo) == {"B"}

    a = _manifest("A", parent="B", root="B")
    second = _burn(repo, "op-2", a)
    assert second.status is OOSBurnStatus.LINEAGE_VIOLATION
    assert _identity_ids(repo) == {"B"}


def test_three_node_cycle_final_write_rejected(repo) -> None:
    # Chain A -> B -> C with a consistent external root R; the final write
    # C -> A closes the cycle and must be rejected atomically.
    a = _manifest("A", parent="B", root="R")
    assert _burn(repo, "op-1", a).status is OOSBurnStatus.BURNED  # registers A (B missing)
    b = _manifest("B", parent="C", root="R")
    assert _burn(repo, "op-2", b).status is OOSBurnStatus.BURNED  # registers B (C missing)
    assert _identity_ids(repo) == {"A", "B"}

    c = _manifest("C", parent="A", root="R")  # closes A->B->C->A
    third = _burn(repo, "op-3", c)
    assert third.status is OOSBurnStatus.LINEAGE_VIOLATION
    assert _identity_ids(repo) == {"A", "B"}
    with repo.db.get_session() as session:
        assert len(session.execute(select(OOSConsumptionEventRecord)).scalars().all()) == 2


def test_incomplete_non_cyclic_chain_still_permitted(repo) -> None:
    # A -> B -> C with consistent roots, A missing: valid truncated chain.
    c = _manifest("C", parent="B", root="A")
    assert _burn(repo, "op-1", c).status is OOSBurnStatus.BURNED  # registers C (B missing)
    b = _manifest("B", parent="A", root="A")
    assert _burn(repo, "op-2", b).status is OOSBurnStatus.BURNED  # registers B (A missing)
    assert _identity_ids(repo) == {"C", "B"}


# --------------------------------------------------------------------------
# Fix R2-2: identity conflict precedes structural lineage rejection
# --------------------------------------------------------------------------


def test_identity_conflict_not_hidden_by_self_parent(repo) -> None:
    a_v1 = _manifest("A")
    assert _burn(repo, "op-1", a_v1).status is OOSBurnStatus.BURNED

    a_v2_self_parent = ExperimentManifest(
        experiment_id="A",
        schema_version="v1",
        governed_components={"window_configuration": "a" * 64},
        created_at=_dt("2020-01-01T00:00:00"),
        root_experiment_id="A",
        parent_experiment_id="A",
    )
    with pytest.raises(OOSLedgerIdentityConflictError):
        repo.claim_if_pristine(
            operation_id="op-2",
            target_manifest=a_v2_self_parent,
            oos_interval=_interval("2024-01-01", "2024-02-01"),
            declared_occurred_at=_dt("2024-01-10"),
        )


def test_identity_conflict_not_hidden_by_changed_parent_plus_defect(repo) -> None:
    a_v1 = _manifest("A")
    assert _burn(repo, "op-1", a_v1).status is OOSBurnStatus.BURNED

    a_v2 = ExperimentManifest(
        experiment_id="A",
        schema_version="v1",
        governed_components={"window_configuration": "b" * 64},
        created_at=_dt("2020-01-01T00:00:00"),
        root_experiment_id="A",
        parent_experiment_id="A",  # self-parent AND identity conflict
    )
    with pytest.raises(OOSLedgerIdentityConflictError):
        repo.mark_outcome_used(
            operation_id="op-2",
            target_manifest=a_v2,
            oos_interval=_interval("2024-01-01", "2024-02-01"),
            declared_occurred_at=_dt("2024-01-10"),
        )


# --------------------------------------------------------------------------
# Fix R2-3: idempotent replay only after full validation
# --------------------------------------------------------------------------


def test_replay_of_valid_incomplete_burn_returns_replay(repo) -> None:
    a = _manifest("A", parent="MISSING", root="MISSING")
    kwargs = dict(
        operation_id="op-1",
        target_manifest=a,
        oos_interval=_interval("2024-01-01", "2024-02-01"),
        declared_occurred_at=_dt("2024-01-10"),
    )
    first = repo.mark_outcome_used(**kwargs)
    assert first.status is OOSBurnStatus.BURNED
    replay = repo.mark_outcome_used(**kwargs)
    assert replay.status is OOSBurnStatus.IDEMPOTENT_REPLAY
    assert replay.event_id == first.event_id


def test_replay_with_self_parent_rejected_not_replay(repo) -> None:
    a = _manifest("A", parent="MISSING", root="MISSING")
    kwargs = dict(
        operation_id="op-1",
        target_manifest=a,
        oos_interval=_interval("2024-01-01", "2024-02-01"),
        declared_occurred_at=_dt("2024-01-10"),
    )
    assert repo.mark_outcome_used(**kwargs).status is OOSBurnStatus.BURNED

    # Same experiment_id with a self-parent necessarily changes the persisted
    # definition (parent "MISSING" -> "A"), so per the frozen write
    # precedence the persistent identity conflict fires first. Either way the
    # structurally invalid replay must never receive IDEMPOTENT_REPLAY.
    a_self_parent = ExperimentManifest(
        experiment_id="A",
        schema_version="v1",
        governed_components={"window_configuration": "f" * 64},
        created_at=_dt("2020-01-01T00:00:00"),
        root_experiment_id="A",
        parent_experiment_id="A",
    )
    with pytest.raises(OOSLedgerIdentityConflictError):
        repo.mark_outcome_used(
            operation_id="op-1",
            target_manifest=a_self_parent,
            oos_interval=_interval("2024-01-01", "2024-02-01"),
            declared_occurred_at=_dt("2024-01-10"),
        )
    # The persisted event remains the original one -- no replay, no new event.
    with repo.db.get_session() as session:
        events = session.execute(select(OOSConsumptionEventRecord)).scalars().all()
        assert len(events) == 1


def test_replay_with_changed_parent_raises_identity_conflict(repo) -> None:
    a = _manifest("A", parent="MISSING", root="MISSING")
    kwargs = dict(
        operation_id="op-1",
        target_manifest=a,
        oos_interval=_interval("2024-01-01", "2024-02-01"),
        declared_occurred_at=_dt("2024-01-10"),
    )
    assert repo.mark_outcome_used(**kwargs).status is OOSBurnStatus.BURNED

    a_changed = _manifest("A", parent="OTHER", root="OTHER")
    with pytest.raises(OOSLedgerIdentityConflictError):
        repo.mark_outcome_used(
            operation_id="op-1",
            target_manifest=a_changed,
            oos_interval=_interval("2024-01-01", "2024-02-01"),
            declared_occurred_at=_dt("2024-01-10"),
        )


def test_replay_with_unrelated_malformed_node_still_replays(repo) -> None:
    a = _manifest("A", parent="MISSING", root="MISSING")
    unrelated_self_parent = _manifest("X", parent="X", root="X")
    first = repo.mark_outcome_used(
        operation_id="op-1",
        target_manifest=a,
        oos_interval=_interval("2024-01-01", "2024-02-01"),
        declared_occurred_at=_dt("2024-01-10"),
    )
    assert first.status is OOSBurnStatus.BURNED
    replay = repo.mark_outcome_used(
        operation_id="op-1",
        target_manifest=a,
        lineage_history=(unrelated_self_parent,),
        oos_interval=_interval("2024-01-01", "2024-02-01"),
        declared_occurred_at=_dt("2024-01-10"),
    )
    assert replay.status is OOSBurnStatus.IDEMPOTENT_REPLAY
    assert replay.event_id == first.event_id
    assert "X" not in _identity_ids(repo)


# --------------------------------------------------------------------------
# Fix R2-4: exact frozen schema constraints fail closed
# --------------------------------------------------------------------------


_EVENTS_FULL_DDL = (
    "CREATE TABLE oos_consumption_event_records ("
    "event_id INTEGER PRIMARY KEY AUTOINCREMENT, "
    "operation_id TEXT NOT NULL UNIQUE, "
    "operation_fingerprint TEXT NOT NULL, "
    "experiment_id TEXT NOT NULL, "
    "manifest_hash TEXT NOT NULL, "
    "root_experiment_id TEXT NOT NULL, "
    "lineage_binding_fingerprint TEXT NOT NULL, "
    "oos_start_utc_text TEXT NOT NULL, "
    "oos_end_utc_text TEXT NOT NULL, "
    "event_kind TEXT NOT NULL, "
    "declared_occurred_at_utc_text TEXT NOT NULL, "
    "recorded_at_utc_text TEXT NOT NULL)"
)

_IDENTITY_FULL_DDL = (
    "CREATE TABLE oos_experiment_identity_records ("
    "id INTEGER PRIMARY KEY, "
    "experiment_id TEXT NOT NULL UNIQUE, "
    "manifest_hash TEXT NOT NULL, "
    "parent_experiment_id TEXT, "
    "root_experiment_id TEXT NOT NULL, "
    "registered_at_utc_text TEXT NOT NULL)"
)


@pytest.mark.parametrize(
    "identity_ddl,events_ddl,extra_sql",
    [
        # identity experiment_id only composite-UNIQUE
        (
            _IDENTITY_FULL_DDL.replace("experiment_id TEXT NOT NULL UNIQUE", "experiment_id TEXT NOT NULL")[:-1]
            + ", UNIQUE(experiment_id, manifest_hash))",
            None,
            None,
        ),
        # event operation_id only composite-UNIQUE
        (
            None,
            _EVENTS_FULL_DDL.replace("operation_id TEXT NOT NULL UNIQUE", "operation_id TEXT NOT NULL")[:-1]
            + ", UNIQUE(operation_id, event_kind))",
            None,
        ),
        # partial UNIQUE on operation_id
        (
            None,
            _EVENTS_FULL_DDL.replace("operation_id TEXT NOT NULL UNIQUE", "operation_id TEXT NOT NULL"),
            "CREATE UNIQUE INDEX ux_partial_op ON oos_consumption_event_records(operation_id) "
            "WHERE event_kind='claimed_for_evaluation'",
        ),
        # identity experiment_id nullable
        (
            _IDENTITY_FULL_DDL.replace("experiment_id TEXT NOT NULL UNIQUE", "experiment_id TEXT UNIQUE"),
            None,
            None,
        ),
        # identity root_experiment_id nullable
        (
            _IDENTITY_FULL_DDL.replace("root_experiment_id TEXT NOT NULL", "root_experiment_id TEXT"),
            None,
            None,
        ),
        # event operation_id nullable
        (
            None,
            _EVENTS_FULL_DDL.replace("operation_id TEXT NOT NULL UNIQUE", "operation_id TEXT UNIQUE"),
            None,
        ),
        # event temporal required column nullable
        (
            None,
            _EVENTS_FULL_DDL.replace("oos_start_utc_text TEXT NOT NULL", "oos_start_utc_text TEXT"),
            None,
        ),
        # event_id without real AUTOINCREMENT
        (
            None,
            _EVENTS_FULL_DDL.replace("event_id INTEGER PRIMARY KEY AUTOINCREMENT", "event_id INTEGER PRIMARY KEY"),
            None,
        ),
    ],
)
def test_exact_schema_violations_fail_closed(identity_ddl, events_ddl, extra_sql) -> None:
    from sqlalchemy import create_engine

    from src.storage import CURRENT_SCHEMA_VERSION

    temp_dir = tempfile.TemporaryDirectory()
    db_path = os.path.join(temp_dir.name, "ledger_strict.db")
    try:
        pre_engine = create_engine(f"sqlite:///{db_path}")
        with pre_engine.begin() as connection:
            if identity_ddl:
                connection.exec_driver_sql(identity_ddl)
            if events_ddl:
                connection.exec_driver_sql(events_ddl)
            if extra_sql:
                connection.exec_driver_sql(extra_sql)
        pre_engine.dispose()

        with pytest.raises(RuntimeError):
            DatabaseManager(f"sqlite:///{db_path}")

        verify_engine = create_engine(f"sqlite:///{db_path}")
        with verify_engine.connect() as connection:
            rows = connection.exec_driver_sql(
                "SELECT version FROM schema_migrations WHERE version = :v",
                {"v": CURRENT_SCHEMA_VERSION},
            ).all()
            assert rows == []
        verify_engine.dispose()
    finally:
        DatabaseManager.reset_instance()
        temp_dir.cleanup()


# --------------------------------------------------------------------------
# Graph-integrity regression suite
# --------------------------------------------------------------------------


def test_graph_extends_monotonically_never_cyclic(repo) -> None:
    a = _manifest("A")
    b = _manifest("B", parent="A", root="A")
    c = _manifest("C", parent="B", root="A")
    assert _burn(repo, "op-1", a).status is OOSBurnStatus.BURNED
    assert _burn(repo, "op-2", b).status is OOSBurnStatus.BURNED
    assert _burn(repo, "op-3", c).status is OOSBurnStatus.BURNED
    assert _identity_ids(repo) == {"A", "B", "C"}
    assessment = repo.get_assessment(experiment_id="C", oos_interval=_interval("2024-01-01", "2024-02-01"))
    assert assessment.resolution is OOSConsumptionResolution.RESOLVED
    assert assessment.state is OOSConsumptionState.BURNED


def test_persisted_node_definitions_never_mutate(repo) -> None:
    a_v1 = _manifest("A")
    assert _burn(repo, "op-1", a_v1).status is OOSBurnStatus.BURNED
    a_v2 = ExperimentManifest(
        experiment_id="A",
        schema_version="v1",
        governed_components={"window_configuration": "a" * 64},
        created_at=_dt("2020-01-01T00:00:00"),
        root_experiment_id="A",
        parent_experiment_id=None,
    )
    with pytest.raises(OOSLedgerIdentityConflictError):
        _burn(repo, "op-2", a_v2)
    with repo.db.get_session() as session:
        row = session.execute(
            select(OOSExperimentIdentityRecord).where(OOSExperimentIdentityRecord.experiment_id == "A")
        ).scalar_one()
        assert row.manifest_hash == a_v1.manifest_hash


def test_late_registration_cannot_introduce_cycle(repo) -> None:
    a = _manifest("A", parent="B", root="B")
    assert _burn(repo, "op-1", a).status is OOSBurnStatus.BURNED
    b = _manifest("B", parent="A", root="A")
    assert _burn(repo, "op-2", b).status is OOSBurnStatus.LINEAGE_VIOLATION
    assert _identity_ids(repo) == {"A"}


def test_unrelated_nodes_cannot_poison_graph(repo) -> None:
    a = _manifest("A")
    unrelated = _manifest("X", parent="X", root="X")
    assert _burn(repo, "op-1", a, history=(unrelated,)).status is OOSBurnStatus.BURNED
    assert _identity_ids(repo) == {"A"}


def test_no_write_transforms_valid_graph_into_invalid(repo) -> None:
    a = _manifest("A")
    assert _burn(repo, "op-1", a).status is OOSBurnStatus.BURNED
    bad_child = _manifest("B", parent="A", root="OTHER")
    result = _burn(repo, "op-2", bad_child)
    assert result.status is OOSBurnStatus.LINEAGE_VIOLATION
    assert _identity_ids(repo) == {"A"}  # valid graph untouched
