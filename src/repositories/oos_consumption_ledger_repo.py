"""Persistence for the Strategy Lab OOS Consumption Ledger.

The ledger is the first persistent Strategy Lab module and follows the
repository's SQLAlchemy/SQLite conventions, with one deliberate exception
owned by the frozen spec: temporal columns are canonical UTC TEXT (never the
repo-wide UTC-naive DateTime convention), restored as aware UTC datetimes.

Transaction model (frozen)
--------------------------
Every write runs inside ``DatabaseManager._run_write_transaction``, which
acquires ``BEGIN IMMEDIATE`` on SQLite before any read, so the idempotency
resolution, identity register-or-verify, lineage audit, overlap check and
event insert form one atomic critical section. Two concurrent overlapping
claims therefore serialize: exactly one observes PRISTINE, the other
observes ALREADY_EXPOSED. No write path uses a plain ``get_session()``.

Lineage authority (frozen)
--------------------------
The persistent identity registry is the only source of lineage for state
derivation. Queries accept an ``experiment_id`` only; caller-supplied
ancestry can never make previously persisted exposure disappear. The ledger
itself calls ``audit_experiment_lineage`` and always passes
``history_complete=False``: a caller-supplied completeness flag would let a
caller assert what the ledger cannot verify, and missing ancestors must
degrade to INDETERMINATE -- never to fake PRISTINE.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.services.strategy_lab.experiment_governance import (
    ExperimentManifest,
    LineageAuditContext,
    LineageAuditVerdict,
    audit_experiment_lineage,
)
from src.services.strategy_lab.oos_consumption import (
    OOSBurnStatus,
    OOSClaimResult,
    OOSClaimStatus,
    OOSConsumptionAssessment,
    OOSConsumptionEvent,
    OOSConsumptionEventKind,
    OOSConsumptionResolution,
    OOSConsumptionState,
    OOSLedgerIdentityConflictError,
    OOSLedgerIdempotencyConflictError,
    OOSLedgerWriteResult,
    _require_identity,
    compute_lineage_binding_fingerprint,
    compute_operation_fingerprint,
    derive_state,
    intervals_overlap,
    parse_aware_utc_text,
    resolve_target_lineage,
)
from src.services.strategy_lab.temporal_contract import TemporalInterval, canonical_utc_text
from src.storage import (
    DatabaseManager,
    OOSConsumptionEventRecord,
    OOSExperimentIdentityRecord,
)


def _now_utc_text() -> str:
    return canonical_utc_text(datetime.now(timezone.utc))


def _event_row_to_domain(row: OOSConsumptionEventRecord) -> OOSConsumptionEvent:
    start = parse_aware_utc_text(row.oos_start_utc_text)
    end = parse_aware_utc_text(row.oos_end_utc_text)
    return OOSConsumptionEvent(
        event_id=row.event_id,
        operation_id=row.operation_id,
        experiment_id=row.experiment_id,
        manifest_hash=row.manifest_hash,
        root_experiment_id=row.root_experiment_id,
        lineage_binding_fingerprint=row.lineage_binding_fingerprint,
        event_kind=OOSConsumptionEventKind(row.event_kind),
        oos_interval=TemporalInterval(start, end),
        declared_occurred_at=parse_aware_utc_text(row.declared_occurred_at_utc_text),
        recorded_at=parse_aware_utc_text(row.recorded_at_utc_text),
    )


class OOSConsumptionLedgerRepository:
    """Append-only OOS consumption ledger over SQLite/SQLAlchemy.

    No reset/delete/unconsume/unburn/update-state API exists by design; the
    only writes are ``claim_if_pristine`` and ``mark_outcome_used``, and the
    only read paths are ``get_assessment`` and ``list_events``.
    """

    def __init__(self, db_manager: DatabaseManager | None = None):
        self.db = db_manager or DatabaseManager.get_instance()
        OOSExperimentIdentityRecord.__table__.create(self.db._engine, checkfirst=True)
        OOSConsumptionEventRecord.__table__.create(self.db._engine, checkfirst=True)

    # ------------------------------------------------------------------
    # Public read API
    # ------------------------------------------------------------------

    def get_assessment(
        self,
        *,
        experiment_id: str,
        oos_interval: TemporalInterval,
    ) -> OOSConsumptionAssessment:
        _require_identity("experiment_id", experiment_id)
        if not isinstance(oos_interval, TemporalInterval):
            raise ValueError(f"oos_interval must be a TemporalInterval, got {oos_interval!r}")
        with self.db.get_session() as session:
            return self._assessment(session, experiment_id, oos_interval)

    def list_events(
        self,
        *,
        experiment_id: str | None = None,
        event_kind: OOSConsumptionEventKind | None = None,
        after_event_id: int | None = None,
        limit: int = 500,
    ) -> tuple[OOSConsumptionEvent, ...]:
        if experiment_id is not None:
            _require_identity("experiment_id", experiment_id)
        if event_kind is not None and not isinstance(event_kind, OOSConsumptionEventKind):
            raise ValueError(f"event_kind must be an OOSConsumptionEventKind, got {event_kind!r}")
        if after_event_id is not None:
            if isinstance(after_event_id, bool) or not isinstance(after_event_id, int):
                raise ValueError(f"after_event_id must be an int or None, got {after_event_id!r}")
        if isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0:
            raise ValueError(f"limit must be a positive int, got {limit!r}")
        with self.db.get_session() as session:
            statement = select(OOSConsumptionEventRecord).order_by(
                OOSConsumptionEventRecord.event_id.asc()
            )
            if experiment_id is not None:
                statement = statement.where(OOSConsumptionEventRecord.experiment_id == experiment_id)
            if event_kind is not None:
                statement = statement.where(OOSConsumptionEventRecord.event_kind == event_kind.value)
            if after_event_id is not None:
                statement = statement.where(OOSConsumptionEventRecord.event_id > after_event_id)
            rows = session.execute(statement.limit(limit)).scalars().all()
            return tuple(_event_row_to_domain(row) for row in rows)

    # ------------------------------------------------------------------
    # Public write API
    # ------------------------------------------------------------------

    def claim_if_pristine(
        self,
        *,
        operation_id: str,
        target_manifest: ExperimentManifest,
        lineage_history: Sequence[ExperimentManifest] = (),
        oos_interval: TemporalInterval,
        declared_occurred_at: datetime,
    ) -> OOSClaimResult:
        operation_id = _require_identity("operation_id", operation_id)
        _validate_manifest_inputs(target_manifest, lineage_history, oos_interval, declared_occurred_at)
        lineage = resolve_target_lineage(target_manifest, lineage_history)

        def _write(session: Session) -> OOSClaimResult:
            # Frozen write precedence:
            #   1. locate the persisted-event idempotency key (do not return yet)
            #   2. read-only persistent identity conflict check (hard error)
            #   3. structural / combined-overlay lineage validation
            #   4. only now resolve idempotency replay vs conflict
            #   5. lineage audit, then claim eligibility / exposure logic
            replay = self._idempotency_lookup(session, operation_id)
            self._check_persistent_identity_conflicts(
                session, (target_manifest, *lineage_history)
            )

            if lineage.conflict or self._overlay_has_structural_violation(session, lineage.reachable):
                return OOSClaimResult(operation_id, OOSClaimStatus.LINEAGE_VIOLATION, None, None)

            fingerprint = self._operation_fingerprint(
                kind=OOSConsumptionEventKind.CLAIMED_FOR_EVALUATION,
                target=target_manifest,
                reachable=lineage.reachable,
                interval=oos_interval,
                declared_occurred_at=declared_occurred_at,
            )
            if replay is not None:
                if replay.operation_fingerprint != fingerprint:
                    raise OOSLedgerIdempotencyConflictError(
                        f"operation_id {operation_id!r} was already persisted with a different "
                        f"semantic fingerprint"
                    )
                assessment = self._assessment(session, target_manifest.experiment_id, oos_interval)
                return OOSClaimResult(
                    operation_id, OOSClaimStatus.IDEMPOTENT_REPLAY, assessment, replay.event_id
                )

            audit = audit_experiment_lineage(
                manifest=target_manifest,
                prior_manifests=[
                    manifest
                    for manifest in lineage.reachable
                    if manifest.experiment_id != target_manifest.experiment_id
                ],
                context=LineageAuditContext(history_complete=False),
            )
            if audit.verdict is LineageAuditVerdict.VIOLATION:
                return OOSClaimResult(operation_id, OOSClaimStatus.LINEAGE_VIOLATION, None, None)
            if audit.verdict is LineageAuditVerdict.INDETERMINATE:
                return OOSClaimResult(operation_id, OOSClaimStatus.LINEAGE_INDETERMINATE, None, None)

            # PASS: identity registration and the claim event stay atomic.
            self._insert_registrations(session, lineage.reachable)
            session.flush()

            assessment = self._assessment(session, target_manifest.experiment_id, oos_interval)
            if assessment.state is not OOSConsumptionState.PRISTINE:
                # Provisional registrations staged above must not survive a
                # denial: roll the whole transaction back before returning.
                session.rollback()
                return OOSClaimResult(operation_id, OOSClaimStatus.ALREADY_EXPOSED, assessment, None)

            record = OOSConsumptionEventRecord(
                operation_id=operation_id,
                operation_fingerprint=fingerprint,
                experiment_id=target_manifest.experiment_id,
                manifest_hash=target_manifest.manifest_hash,
                root_experiment_id=target_manifest.root_experiment_id,
                lineage_binding_fingerprint=compute_lineage_binding_fingerprint(lineage.reachable),
                oos_start_utc_text=canonical_utc_text(oos_interval.start),
                oos_end_utc_text=canonical_utc_text(oos_interval.end),
                event_kind=OOSConsumptionEventKind.CLAIMED_FOR_EVALUATION.value,
                declared_occurred_at_utc_text=canonical_utc_text(declared_occurred_at),
                recorded_at_utc_text=_now_utc_text(),
            )
            session.add(record)
            session.flush()
            post = self._assessment(session, target_manifest.experiment_id, oos_interval)
            return OOSClaimResult(operation_id, OOSClaimStatus.CLAIMED, post, record.event_id)

        return self.db._run_write_transaction("oos ledger claim_if_pristine", _write)

    def mark_outcome_used(
        self,
        *,
        operation_id: str,
        target_manifest: ExperimentManifest,
        lineage_history: Sequence[ExperimentManifest] = (),
        oos_interval: TemporalInterval,
        declared_occurred_at: datetime,
    ) -> OOSLedgerWriteResult:
        operation_id = _require_identity("operation_id", operation_id)
        _validate_manifest_inputs(target_manifest, lineage_history, oos_interval, declared_occurred_at)
        lineage = resolve_target_lineage(target_manifest, lineage_history)

        def _write(session: Session) -> OOSLedgerWriteResult:
            replay = self._idempotency_lookup(session, operation_id)
            self._check_persistent_identity_conflicts(
                session, (target_manifest, *lineage_history)
            )

            # Known structural contradiction (cycle / self-parent / root
            # violation / child-root mismatch) rejects the whole write; only
            # missing ancestry is a permitted INDETERMINATE condition.
            if lineage.conflict or self._overlay_has_structural_violation(session, lineage.reachable):
                return OOSLedgerWriteResult(operation_id, OOSBurnStatus.LINEAGE_VIOLATION, None, None)

            fingerprint = self._operation_fingerprint(
                kind=OOSConsumptionEventKind.OUTCOME_USED,
                target=target_manifest,
                reachable=lineage.reachable,
                interval=oos_interval,
                declared_occurred_at=declared_occurred_at,
            )
            if replay is not None:
                if replay.operation_fingerprint != fingerprint:
                    raise OOSLedgerIdempotencyConflictError(
                        f"operation_id {operation_id!r} was already persisted with a different "
                        f"semantic fingerprint"
                    )
                assessment = self._assessment(session, target_manifest.experiment_id, oos_interval)
                return OOSLedgerWriteResult(
                    operation_id, OOSBurnStatus.IDEMPOTENT_REPLAY, replay.event_id, assessment
                )

            audit = audit_experiment_lineage(
                manifest=target_manifest,
                prior_manifests=[
                    manifest
                    for manifest in lineage.reachable
                    if manifest.experiment_id != target_manifest.experiment_id
                ],
                context=LineageAuditContext(history_complete=False),
            )
            if audit.verdict is LineageAuditVerdict.VIOLATION:
                return OOSLedgerWriteResult(operation_id, OOSBurnStatus.LINEAGE_VIOLATION, None, None)

            # PASS and INDETERMINATE both record real pollution: refusing to
            # record a known burn because ancestry is incomplete would let
            # contamination be forgotten. Registration covers the target and
            # the target-reachable supplied ancestor prefix only -- missing
            # ancestors stay missing and are never fabricated, and unrelated
            # supplied nodes never enter the registry.
            self._insert_registrations(session, lineage.reachable)
            session.flush()

            record = OOSConsumptionEventRecord(
                operation_id=operation_id,
                operation_fingerprint=fingerprint,
                experiment_id=target_manifest.experiment_id,
                manifest_hash=target_manifest.manifest_hash,
                root_experiment_id=target_manifest.root_experiment_id,
                lineage_binding_fingerprint=compute_lineage_binding_fingerprint(lineage.reachable),
                oos_start_utc_text=canonical_utc_text(oos_interval.start),
                oos_end_utc_text=canonical_utc_text(oos_interval.end),
                event_kind=OOSConsumptionEventKind.OUTCOME_USED.value,
                declared_occurred_at_utc_text=canonical_utc_text(declared_occurred_at),
                recorded_at_utc_text=_now_utc_text(),
            )
            session.add(record)
            session.flush()
            post = self._assessment(session, target_manifest.experiment_id, oos_interval)
            return OOSLedgerWriteResult(operation_id, OOSBurnStatus.BURNED, record.event_id, post)

        return self.db._run_write_transaction("oos ledger mark_outcome_used", _write)

    # ------------------------------------------------------------------
    # Internal helpers -- all run inside the active write transaction or
    # a plain read session; never write outside _run_write_transaction.
    # ------------------------------------------------------------------

    def _operation_fingerprint(
        self,
        *,
        kind: OOSConsumptionEventKind,
        target: ExperimentManifest,
        reachable: Sequence[ExperimentManifest],
        interval: TemporalInterval,
        declared_occurred_at: datetime,
    ) -> str:
        return compute_operation_fingerprint(
            event_kind=kind,
            experiment_id=target.experiment_id,
            manifest_hash=target.manifest_hash,
            parent_experiment_id=target.parent_experiment_id,
            root_experiment_id=target.root_experiment_id,
            oos_start=interval.start,
            oos_end=interval.end,
            declared_occurred_at=declared_occurred_at,
            lineage_binding_fingerprint=compute_lineage_binding_fingerprint(reachable),
        )

    def _idempotency_lookup(
        self,
        session: Session,
        operation_id: str,
    ) -> OOSConsumptionEventRecord | None:
        """Locate a persisted state-changing event by operation_id WITHOUT
        resolving replay: the caller must validate identity + structure
        before deciding replay vs conflict."""

        return session.execute(
            select(OOSConsumptionEventRecord).where(
                OOSConsumptionEventRecord.operation_id == operation_id
            )
        ).scalar_one_or_none()

    @staticmethod
    def _persisted_identity_definitions(
        session: Session,
    ) -> dict[str, tuple[str, str | None, str]]:
        rows = session.execute(select(OOSExperimentIdentityRecord)).scalars().all()
        return {
            row.experiment_id: (row.manifest_hash, row.parent_experiment_id, row.root_experiment_id)
            for row in rows
        }

    def _check_persistent_identity_conflicts(
        self,
        session: Session,
        supplied: Sequence[ExperimentManifest],
    ) -> None:
        """Step 2 of the frozen write precedence: any supplied manifest (the
        target or any lineage-history node) that contradicts the persisted
        registry is a hard integrity error, never hidden behind a structural
        lineage verdict or an idempotent replay. Read-only; never mutates.
        Checked over the FULL supplied set -- a resolver that truncates a
        structurally broken chain must not hide the contradiction."""

        persisted = self._persisted_identity_definitions(session)
        for manifest in supplied:
            row = persisted.get(manifest.experiment_id)
            if row is None:
                continue
            if row != (
                manifest.manifest_hash,
                manifest.parent_experiment_id,
                manifest.root_experiment_id,
            ):
                raise OOSLedgerIdentityConflictError(
                    f"experiment_id {manifest.experiment_id!r} is already registered with a "
                    f"different definition (manifest_hash/parent/root)"
                )

    def _overlay_has_structural_violation(
        self,
        session: Session,
        reachable: Sequence[ExperimentManifest],
    ) -> bool:
        """Step 3 of the frozen write precedence: validate the tentative
        overlay graph (persisted registry + target-reachable candidate
        definitions). The combined graph must never contain a self-parent,
        a lineage cycle, a root-invariant violation, or a child/root
        mismatch. Missing ancestry is NOT a violation here -- only known
        structural contradiction is."""

        overlay = self._persisted_identity_definitions(session)
        for manifest in reachable:
            overlay[manifest.experiment_id] = (
                manifest.manifest_hash,
                manifest.parent_experiment_id,
                manifest.root_experiment_id,
            )

        for experiment_id, (_hash, parent, root) in overlay.items():
            if parent is None:
                if root != experiment_id:
                    return True  # root node must declare itself as its own root
            else:
                if root == experiment_id:
                    return True  # child must not declare itself as its own root
                if parent == experiment_id:
                    return True  # self-parent
                parent_row = overlay.get(parent)
                if parent_row is not None and parent_row[2] != root:
                    return True  # child/root mismatch along the combined graph

        # Cycle detection over the combined overlay.
        for experiment_id in overlay:
            seen: set[str] = set()
            current: str | None = experiment_id
            while current is not None:
                if current in seen:
                    return True
                if current not in overlay:
                    break
                seen.add(current)
                current = overlay[current][1]
        return False

    def _insert_registrations(
        self,
        session: Session,
        reachable: Sequence[ExperimentManifest],
    ) -> None:
        """Insert only target-reachable nodes not yet persisted. Structural
        and identity validity of the combined overlay has already been
        verified before this is ever called."""

        persisted = self._persisted_identity_definitions(session)
        for manifest in reachable:
            if manifest.experiment_id in persisted:
                continue
            session.add(
                OOSExperimentIdentityRecord(
                    experiment_id=manifest.experiment_id,
                    manifest_hash=manifest.manifest_hash,
                    parent_experiment_id=manifest.parent_experiment_id,
                    root_experiment_id=manifest.root_experiment_id,
                    registered_at_utc_text=_now_utc_text(),
                )
            )
        session.flush()

    def _assessment(
        self,
        session: Session,
        experiment_id: str,
        oos_interval: TemporalInterval,
    ) -> OOSConsumptionAssessment:
        rows = session.execute(select(OOSExperimentIdentityRecord)).scalars().all()
        definitions = {row.experiment_id: row for row in rows}
        chain, conflict = self._lineage_chain(definitions, experiment_id)
        if conflict is not None:
            return OOSConsumptionAssessment(
                resolution=conflict,
                state=None,
                overlapping_event_ids=(),
                lineage_experiment_ids=tuple(chain),
            )

        events = session.execute(
            select(OOSConsumptionEventRecord).where(
                OOSConsumptionEventRecord.experiment_id.in_(chain)
            )
        ).scalars().all()
        overlapping = [
            row
            for row in events
            if intervals_overlap(
                parse_aware_utc_text(row.oos_start_utc_text),
                parse_aware_utc_text(row.oos_end_utc_text),
                oos_interval.start,
                oos_interval.end,
            )
        ]
        kinds = [OOSConsumptionEventKind(row.event_kind) for row in overlapping]
        return OOSConsumptionAssessment(
            resolution=OOSConsumptionResolution.RESOLVED,
            state=derive_state(kinds),
            overlapping_event_ids=tuple(row.event_id for row in overlapping),
            lineage_experiment_ids=tuple(sorted(definitions.keys() & set(chain))),
        )

    @staticmethod
    def _lineage_chain(
        definitions: dict[str, OOSExperimentIdentityRecord],
        experiment_id: str,
    ) -> tuple[list[str], OOSConsumptionResolution | None]:
        if experiment_id not in definitions:
            return [], OOSConsumptionResolution.INDETERMINATE
        chain: list[str] = [experiment_id]
        visited = {experiment_id}
        current = definitions[experiment_id]
        while current.parent_experiment_id is not None:
            parent_id = current.parent_experiment_id
            if parent_id in visited:
                return chain, OOSConsumptionResolution.CONFLICT
            if parent_id not in definitions:
                return chain, OOSConsumptionResolution.INDETERMINATE
            chain.append(parent_id)
            visited.add(parent_id)
            current = definitions[parent_id]
        root_id = current.experiment_id
        if current.root_experiment_id != root_id:
            return chain, OOSConsumptionResolution.CONFLICT
        for node_id in chain:
            if definitions[node_id].root_experiment_id != root_id:
                return chain, OOSConsumptionResolution.CONFLICT
        return chain, None


def _validate_manifest_inputs(
    target_manifest: ExperimentManifest,
    lineage_history: Sequence[ExperimentManifest],
    oos_interval: TemporalInterval,
    declared_occurred_at: datetime,
) -> None:
    if not isinstance(target_manifest, ExperimentManifest):
        raise ValueError(f"target_manifest must be an ExperimentManifest, got {target_manifest!r}")
    if not isinstance(oos_interval, TemporalInterval):
        raise ValueError(f"oos_interval must be a TemporalInterval, got {oos_interval!r}")
    # canonical_utc_datetime rejects naive datetimes outright.
    canonical_utc_text(declared_occurred_at)
    for manifest in lineage_history:
        if not isinstance(manifest, ExperimentManifest):
            raise ValueError(
                f"lineage_history must contain only ExperimentManifest, got {manifest!r}"
            )
