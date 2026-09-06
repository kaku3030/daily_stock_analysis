import dataclasses
import inspect
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from src.services.strategy_lab.universe_integrity import (
    ClassificationAnchor,
    ClassificationCoverageCertificate,
    ClassificationEvent,
    ClassificationFacts,
    ClassificationResolution,
    ClassificationState,
    ClassificationValue,
    CoverageDiagnostics,
    InstrumentLifecycleAnchor,
    InstrumentLifecycleCoverageCertificate,
    InstrumentLifecycleEvent,
    InstrumentLifecycleFacts,
    InstrumentLifecycleResolution,
    IntegrityFinding,
    IntegrityFindingCode,
    LifecycleState,
    MembershipState,
    UniverseIntegrityResolutionStatus,
    UniverseMembershipAnchor,
    UniverseMembershipCoverageCertificate,
    UniverseMembershipEvent,
    UniverseMembershipFacts,
    UniverseMembershipResolution,
    compute_classification_event_slice_fingerprint,
    compute_instrument_lifecycle_event_slice_fingerprint,
    compute_universe_membership_event_slice_fingerprint,
    resolve_classification,
    resolve_instrument_lifecycle,
    resolve_universe_membership,
)


PERMANENT_UNIVERSE_INTEGRITY_TEST_IDS = (
    "TEST_ANCHOR_OLDER_RESOLVED_LATER_CONFLICT_YIELDS_CONFLICT",
    "TEST_ANCHOR_EARLIER_CONFLICT_LATER_RESOLVED_YIELDS_RESOLVED",
    "TEST_BOUNDARY_REVISION_HARMLESS_WHEN_LATEST_MATCHES_ANCHOR",
    "TEST_BOUNDARY_INTERNAL_CONTRADICTION_YIELDS_EVENT_CONFLICT_NOT_ANCHOR_EVENT_CONFLICT",
    "TEST_COVERAGE_NOT_CERTIFIED_WHEN_REQUIRED_AND_NO_CERTIFICATES",
    "TEST_COVERAGE_GAP_WHEN_CERTIFICATE_STARTS_AFTER_ANCHOR",
    "TEST_COVERAGE_BOUNDARY_NOT_REACHED_WHEN_INTERVAL_ENDS_AT_AS_OF",
    "TEST_COVERAGE_GAP_WITH_DISCONNECTED_LATER_INTERVAL",
    "TEST_COVERAGE_SATISFIED_WHEN_INTERVAL_EXTENDS_PAST_AS_OF",
    "TEST_COVERAGE_NOT_REQUIRED_WHEN_AS_OF_EQUALS_ANCHOR",
    "TEST_EMPTY_MEMBERSHIP_ANCHOR_RESOLVES_TO_EMPTY_FROZENSET",
    "TEST_INVISIBLE_NEWER_EVENT_REVISION_IGNORED",
    "TEST_EVENT_CONFLICT_WITH_INSUFFICIENT_COVERAGE_PRESERVES_BOTH_FINDINGS",
    "TEST_CLASSIFICATION_BOUNDARY_DISAGREEMENT_YIELDS_ANCHOR_EVENT_CONFLICT",
    "TEST_LIFECYCLE_ROUNDTRIP_RESOLVES_TO_LATEST_STATE",
    "TEST_BOUNDARY_EVENT_AVAILABLE_AFTER_DECISION_IS_INVISIBLE",
    "TEST_BOUNDARY_EVENT_AVAILABLE_EQUAL_DECISION_IS_VISIBLE",
    "TEST_NO_VISIBLE_ANCHOR_YIELDS_INDETERMINATE",
    "TEST_ANCHOR_CONFLICT_SELECTED_ANCHOR_AND_COVERAGE_ARE_NONE",
    "TEST_IDENTITY_REJECTS_EMPTY_BLANK_WHITESPACE_AND_NON_STRING",
    "TEST_RAW_ENUM_STRING_REJECTED",
    "TEST_CLASSIFICATION_VALUE_ID_PRESENCE_MATCHES_STATE",
    "TEST_FACTS_SCOPE_COHERENCE_ENFORCED",
    "TEST_COVERAGE_CERTIFICATE_WRONG_SCOPE_COUNTED_AND_UNUSABLE",
    "TEST_COVERAGE_CERTIFICATE_WRONG_FINGERPRINT_COUNTED_AND_UNUSABLE",
    "TEST_EXTRA_INVALID_CERTIFICATES_DO_NOT_POISON_VALID_COVERAGE",
    "TEST_ADJACENT_AND_OVERLAPPING_INTERVALS_MERGE",
    "TEST_FINGERPRINT_REORDER_INVARIANT",
    "TEST_FINGERPRINT_DUPLICATE_COLLAPSE",
    "TEST_FINGERPRINT_CHANGES_WHEN_EVENT_INSIDE_WINDOW_CHANGES",
    "TEST_FINGERPRINT_UNCHANGED_WHEN_CHANGE_OUTSIDE_WINDOW",
    "TEST_FINGERPRINT_UNCHANGED_BY_ANCHOR_REVISION",
    "TEST_FINGERPRINT_HALF_OPEN_EXCLUDES_COVERAGE_END",
    "TEST_COVERAGE_DIAGNOSTICS_INVARIANT_ENFORCED",
    "TEST_MEMBERSHIP_RESOLVED_REQUIRES_FROZENSET_AND_NO_FINDINGS",
    "TEST_MEMBERSHIP_NON_RESOLVED_MEMBERS_IS_NONE",
    "TEST_LIFECYCLE_NON_RESOLVED_STATE_IS_NONE",
    "TEST_CLASSIFICATION_NON_RESOLVED_VALUE_IS_NONE",
    "TEST_FINDINGS_CANONICAL_ORDER_IS_INPUT_ORDER_INVARIANT",
    "TEST_STATUS_PRECEDENCE_CONFLICT_OVER_INDETERMINATE",
    "TEST_NO_FORBIDDEN_IMPORTS",
    "TEST_MODULE_IS_A_STRATEGY_LAB_LEAF",
    "TEST_FROZEN_PUBLIC_CONTRACT_SHAPE",
    "TEST_STATUS_DISTINCT_FROM_INFORMATION_DEPENDENCY_RESOLUTION_STATUS",
    "TEST_NO_CONTRACT_FINGERPRINT_PROPERTY",
    "TEST_MEMBERSHIP_VISIBLE_EVENT_WINS_OVER_INVISIBLE_LATER_EVENT",
    "TEST_MEMBERSHIP_VISIBLE_CONFLICT_NOT_MASKED_BY_INVISIBLE_LATER_EVENT",
    "TEST_LIFECYCLE_VISIBLE_EVENT_WINS_OVER_INVISIBLE_LATER_EVENT",
    "TEST_CLASSIFICATION_VISIBLE_EVENT_WINS_OVER_INVISIBLE_LATER_EVENT",
    "TEST_LATER_VISIBLE_RESOLVED_SUPERSEDES_EARLIER_CONFLICT_IN_NORMAL_EVENTS",
    "TEST_LATER_VISIBLE_CONFLICT_SUPERSEDES_EARLIER_RESOLVED_IN_NORMAL_EVENTS",
    "TEST_GOLDEN_FINGERPRINT_MEMBERSHIP",
    "TEST_GOLDEN_FINGERPRINT_LIFECYCLE",
    "TEST_GOLDEN_FINGERPRINT_CLASSIFICATION",
    "TEST_FACTS_REJECT_NON_TUPLE_ANCHORS_AND_EVENTS",
    "TEST_COVERAGE_DIAGNOSTICS_VALID_CERTIFICATE_COUNT_TRACKED",
    "TEST_COVERAGE_DIAGNOSTICS_NOT_REQUIRED_POPULATES_WINDOW",
)

UTC = timezone.utc
RESOLVED = UniverseIntegrityResolutionStatus.RESOLVED
CONFLICT = UniverseIntegrityResolutionStatus.CONFLICT
INDETERMINATE = UniverseIntegrityResolutionStatus.INDETERMINATE


def _dt(y: int, m: int, d: int, h: int = 0, minute: int = 0) -> datetime:
    return datetime(y, m, d, h, minute, tzinfo=UTC)


def _codes(resolution) -> set:
    return {f.code for f in resolution.findings}


def _empty_coverage(at: datetime) -> CoverageDiagnostics:
    return CoverageDiagnostics(
        required=False,
        satisfied=True,
        required_start=at,
        required_through=at,
        valid_certificate_count=0,
        scope_mismatch_count=0,
        fingerprint_mismatch_count=0,
        merged_intervals=(),
        furthest_contiguous_end=None,
    )


# ---- Decision-oracle case 1 & 2: anchor precedence ----


def test_anchor_older_resolved_later_conflict_yields_conflict() -> None:
    u = "U1"
    jan_resolved = UniverseMembershipAnchor(
        universe_id=u, members=frozenset({"A"}), effective_at=_dt(2026, 1, 1), available_at=_dt(2026, 1, 1)
    )
    feb_1 = UniverseMembershipAnchor(
        universe_id=u, members=frozenset({"A"}), effective_at=_dt(2026, 2, 1), available_at=_dt(2026, 2, 1)
    )
    feb_2 = UniverseMembershipAnchor(
        universe_id=u, members=frozenset({"B"}), effective_at=_dt(2026, 2, 1), available_at=_dt(2026, 2, 1)
    )
    facts = UniverseMembershipFacts(universe_id=u, anchors=(jan_resolved, feb_1, feb_2), events=())

    result = resolve_universe_membership(facts, as_of=_dt(2026, 2, 1), decision_time=_dt(2026, 3, 1))

    assert result.status is CONFLICT
    assert IntegrityFindingCode.ANCHOR_CONFLICT in _codes(result)
    assert result.members is None
    assert result.selected_anchor is None


def test_anchor_earlier_conflict_later_resolved_yields_resolved() -> None:
    u = "U1"
    jan_1 = UniverseMembershipAnchor(
        universe_id=u, members=frozenset({"A"}), effective_at=_dt(2026, 1, 1), available_at=_dt(2026, 1, 1)
    )
    jan_2 = UniverseMembershipAnchor(
        universe_id=u, members=frozenset({"B"}), effective_at=_dt(2026, 1, 1), available_at=_dt(2026, 1, 1)
    )
    feb_resolved = UniverseMembershipAnchor(
        universe_id=u, members=frozenset({"C"}), effective_at=_dt(2026, 2, 1), available_at=_dt(2026, 2, 1)
    )
    facts = UniverseMembershipFacts(universe_id=u, anchors=(jan_1, jan_2, feb_resolved), events=())

    result = resolve_universe_membership(facts, as_of=_dt(2026, 2, 1), decision_time=_dt(2026, 3, 1))

    assert result.status is RESOLVED
    assert result.members == frozenset({"C"})
    assert result.selected_anchor is feb_resolved


# ---- Decision-oracle case 3 & 4: boundary events ----


def test_boundary_revision_harmless_when_latest_matches_anchor() -> None:
    u = "U1"
    a = _dt(2026, 1, 10)
    anchor = UniverseMembershipAnchor(
        universe_id=u, members=frozenset({"X"}), effective_at=a, available_at=_dt(2026, 1, 1)
    )
    v1 = UniverseMembershipEvent(
        universe_id=u, instrument_id="X", state=MembershipState.NON_MEMBER, effective_at=a, available_at=_dt(2026, 1, 9)
    )
    v2 = UniverseMembershipEvent(
        universe_id=u, instrument_id="X", state=MembershipState.MEMBER, effective_at=a, available_at=_dt(2026, 1, 10, 10)
    )
    facts = UniverseMembershipFacts(universe_id=u, anchors=(anchor,), events=(v1, v2))

    result = resolve_universe_membership(facts, as_of=a, decision_time=_dt(2026, 1, 11))

    assert result.status is RESOLVED
    assert result.members == frozenset({"X"})


def test_boundary_internal_contradiction_yields_event_conflict_not_anchor_event_conflict() -> None:
    u = "U1"
    a = _dt(2026, 1, 10)
    anchor = UniverseMembershipAnchor(
        universe_id=u, members=frozenset({"X"}), effective_at=a, available_at=_dt(2026, 1, 1)
    )
    e1 = UniverseMembershipEvent(
        universe_id=u, instrument_id="X", state=MembershipState.MEMBER, effective_at=a, available_at=_dt(2026, 1, 10, 10)
    )
    e2 = UniverseMembershipEvent(
        universe_id=u, instrument_id="X", state=MembershipState.NON_MEMBER, effective_at=a, available_at=_dt(2026, 1, 10, 10)
    )
    facts = UniverseMembershipFacts(universe_id=u, anchors=(anchor,), events=(e1, e2))

    result = resolve_universe_membership(facts, as_of=a, decision_time=_dt(2026, 1, 11))

    assert result.status is CONFLICT
    assert IntegrityFindingCode.EVENT_CONFLICT in _codes(result)
    assert IntegrityFindingCode.ANCHOR_EVENT_CONFLICT not in _codes(result)


def test_boundary_event_available_after_decision_is_invisible() -> None:
    u = "U1"
    a = _dt(2026, 1, 10)
    anchor = UniverseMembershipAnchor(
        universe_id=u, members=frozenset({"X"}), effective_at=a, available_at=_dt(2026, 1, 1)
    )
    boundary = UniverseMembershipEvent(
        universe_id=u, instrument_id="X", state=MembershipState.NON_MEMBER, effective_at=a, available_at=_dt(2026, 1, 12)
    )
    facts = UniverseMembershipFacts(universe_id=u, anchors=(anchor,), events=(boundary,))

    result = resolve_universe_membership(facts, as_of=a, decision_time=_dt(2026, 1, 11))

    assert result.status is RESOLVED
    assert result.members == frozenset({"X"})


def test_boundary_event_available_equal_decision_is_visible() -> None:
    u = "U1"
    a = _dt(2026, 1, 10)
    anchor = UniverseMembershipAnchor(
        universe_id=u, members=frozenset({"X"}), effective_at=a, available_at=_dt(2026, 1, 1)
    )
    boundary = UniverseMembershipEvent(
        universe_id=u, instrument_id="X", state=MembershipState.NON_MEMBER, effective_at=a, available_at=_dt(2026, 1, 12)
    )
    facts = UniverseMembershipFacts(universe_id=u, anchors=(anchor,), events=(boundary,))

    result = resolve_universe_membership(facts, as_of=a, decision_time=_dt(2026, 1, 12))

    assert result.status is CONFLICT
    assert IntegrityFindingCode.ANCHOR_EVENT_CONFLICT in _codes(result)


# ---- Coverage decision-oracle cases 5-10 ----


def test_coverage_not_certified_when_required_and_no_certificates() -> None:
    u = "U1"
    a = _dt(2026, 1, 10)
    q = _dt(2026, 2, 1)
    anchor = UniverseMembershipAnchor(
        universe_id=u, members=frozenset({"X"}), effective_at=a, available_at=_dt(2026, 1, 1)
    )
    facts = UniverseMembershipFacts(universe_id=u, anchors=(anchor,), events=())

    result = resolve_universe_membership(facts, as_of=q, decision_time=q)

    assert result.status is INDETERMINATE
    assert IntegrityFindingCode.COVERAGE_NOT_CERTIFIED in _codes(result)
    assert result.coverage.merged_intervals == ()


def test_coverage_gap_when_certificate_starts_after_anchor() -> None:
    u = "U1"
    a = _dt(2026, 1, 10)
    q = _dt(2026, 2, 1)
    anchor = UniverseMembershipAnchor(
        universe_id=u, members=frozenset({"X"}), effective_at=a, available_at=_dt(2026, 1, 1)
    )
    facts = UniverseMembershipFacts(universe_id=u, anchors=(anchor,), events=())
    start = a + timedelta(days=1)
    fp = compute_universe_membership_event_slice_fingerprint(
        universe_id=u, coverage_start=start, coverage_end=q + timedelta(days=1), events=()
    )
    cert = UniverseMembershipCoverageCertificate(
        universe_id=u, coverage_start=start, coverage_end=q + timedelta(days=1), certified_event_slice_fingerprint=fp
    )

    result = resolve_universe_membership(facts, as_of=q, decision_time=q, coverage_certificates=(cert,))

    assert result.status is INDETERMINATE
    assert IntegrityFindingCode.COVERAGE_GAP in _codes(result)


def test_coverage_boundary_not_reached_when_interval_ends_at_as_of() -> None:
    u = "U1"
    a = _dt(2026, 1, 10)
    q = _dt(2026, 2, 1)
    anchor = UniverseMembershipAnchor(
        universe_id=u, members=frozenset({"X"}), effective_at=a, available_at=_dt(2026, 1, 1)
    )
    facts = UniverseMembershipFacts(universe_id=u, anchors=(anchor,), events=())
    fp = compute_universe_membership_event_slice_fingerprint(
        universe_id=u, coverage_start=a, coverage_end=q, events=()
    )
    cert = UniverseMembershipCoverageCertificate(
        universe_id=u, coverage_start=a, coverage_end=q, certified_event_slice_fingerprint=fp
    )

    result = resolve_universe_membership(facts, as_of=q, decision_time=q, coverage_certificates=(cert,))

    assert result.status is INDETERMINATE
    assert IntegrityFindingCode.COVERAGE_BOUNDARY_NOT_REACHED in _codes(result)
    assert result.coverage.furthest_contiguous_end == q


def test_coverage_gap_with_disconnected_later_interval() -> None:
    u = "U1"
    a = _dt(2026, 1, 10)
    b = _dt(2026, 1, 15)
    c = _dt(2026, 1, 20)
    z = _dt(2026, 2, 5)
    q = _dt(2026, 2, 1)
    anchor = UniverseMembershipAnchor(
        universe_id=u, members=frozenset({"X"}), effective_at=a, available_at=_dt(2026, 1, 1)
    )
    facts = UniverseMembershipFacts(universe_id=u, anchors=(anchor,), events=())
    fp_first = compute_universe_membership_event_slice_fingerprint(
        universe_id=u, coverage_start=a, coverage_end=b, events=()
    )
    fp_second = compute_universe_membership_event_slice_fingerprint(
        universe_id=u, coverage_start=c, coverage_end=z, events=()
    )
    cert_first = UniverseMembershipCoverageCertificate(
        universe_id=u, coverage_start=a, coverage_end=b, certified_event_slice_fingerprint=fp_first
    )
    cert_second = UniverseMembershipCoverageCertificate(
        universe_id=u, coverage_start=c, coverage_end=z, certified_event_slice_fingerprint=fp_second
    )

    result = resolve_universe_membership(
        facts, as_of=q, decision_time=q, coverage_certificates=(cert_first, cert_second)
    )

    assert result.status is INDETERMINATE
    assert IntegrityFindingCode.COVERAGE_GAP in _codes(result)
    assert result.coverage.furthest_contiguous_end == b


def test_coverage_satisfied_when_interval_extends_past_as_of() -> None:
    u = "U1"
    a = _dt(2026, 1, 10)
    q = _dt(2026, 2, 1)
    anchor = UniverseMembershipAnchor(
        universe_id=u, members=frozenset({"X"}), effective_at=a, available_at=_dt(2026, 1, 1)
    )
    facts = UniverseMembershipFacts(universe_id=u, anchors=(anchor,), events=())
    start = a - timedelta(days=10)
    end = q + timedelta(days=1)
    fp = compute_universe_membership_event_slice_fingerprint(
        universe_id=u, coverage_start=start, coverage_end=end, events=()
    )
    cert = UniverseMembershipCoverageCertificate(
        universe_id=u, coverage_start=start, coverage_end=end, certified_event_slice_fingerprint=fp
    )

    result = resolve_universe_membership(facts, as_of=q, decision_time=q, coverage_certificates=(cert,))

    assert result.status is RESOLVED
    assert result.coverage.satisfied is True


def test_coverage_not_required_when_as_of_equals_anchor() -> None:
    u = "U1"
    a = _dt(2026, 1, 10)
    anchor = UniverseMembershipAnchor(universe_id=u, members=frozenset({"X"}), effective_at=a, available_at=_dt(2026, 1, 1))
    facts = UniverseMembershipFacts(universe_id=u, anchors=(anchor,), events=())

    result = resolve_universe_membership(facts, as_of=a, decision_time=a)

    assert result.status is RESOLVED
    assert result.coverage.required is False
    assert result.coverage.satisfied is True
    assert result.coverage.required_start == a
    assert result.coverage.required_through == a
    assert result.coverage.furthest_contiguous_end is None


# ---- Case 11-15 ----


def test_empty_membership_anchor_resolves_to_empty_frozenset() -> None:
    u = "U1"
    a = _dt(2026, 1, 10)
    anchor = UniverseMembershipAnchor(universe_id=u, members=frozenset(), effective_at=a, available_at=a)
    facts = UniverseMembershipFacts(universe_id=u, anchors=(anchor,), events=())

    result = resolve_universe_membership(facts, as_of=a, decision_time=a)

    assert result.status is RESOLVED
    assert result.members == frozenset()
    assert result.members is not None


def test_invisible_newer_event_revision_ignored() -> None:
    u = "U1"
    a = _dt(2026, 1, 10)
    anchor = UniverseMembershipAnchor(universe_id=u, members=frozenset({"X"}), effective_at=a, available_at=_dt(2026, 1, 1))
    older_visible = UniverseMembershipEvent(
        universe_id=u, instrument_id="X", state=MembershipState.NON_MEMBER, effective_at=_dt(2026, 1, 15), available_at=_dt(2026, 1, 15)
    )
    newer_invisible = UniverseMembershipEvent(
        universe_id=u, instrument_id="X", state=MembershipState.MEMBER, effective_at=_dt(2026, 1, 15), available_at=_dt(2026, 1, 25)
    )
    facts = UniverseMembershipFacts(universe_id=u, anchors=(anchor,), events=(older_visible, newer_invisible))
    q = _dt(2026, 1, 20)
    fp = compute_universe_membership_event_slice_fingerprint(
        universe_id=u, coverage_start=a, coverage_end=q + timedelta(days=1), events=facts.events
    )
    cert = UniverseMembershipCoverageCertificate(
        universe_id=u, coverage_start=a, coverage_end=q + timedelta(days=1), certified_event_slice_fingerprint=fp
    )

    result = resolve_universe_membership(
        facts, as_of=q, decision_time=_dt(2026, 1, 18), coverage_certificates=(cert,)
    )

    assert result.status is RESOLVED
    assert "X" not in result.members


def test_event_conflict_with_insufficient_coverage_preserves_both_findings() -> None:
    u = "U1"
    a = _dt(2026, 1, 10)
    q = _dt(2026, 2, 1)
    anchor = UniverseMembershipAnchor(universe_id=u, members=frozenset({"X"}), effective_at=a, available_at=_dt(2026, 1, 1))
    ec1 = UniverseMembershipEvent(
        universe_id=u, instrument_id="Y", state=MembershipState.MEMBER, effective_at=_dt(2026, 1, 15), available_at=_dt(2026, 1, 15)
    )
    ec2 = UniverseMembershipEvent(
        universe_id=u, instrument_id="Y", state=MembershipState.NON_MEMBER, effective_at=_dt(2026, 1, 15), available_at=_dt(2026, 1, 15)
    )
    facts = UniverseMembershipFacts(universe_id=u, anchors=(anchor,), events=(ec1, ec2))

    result = resolve_universe_membership(facts, as_of=q, decision_time=q)

    assert result.status is CONFLICT
    assert IntegrityFindingCode.EVENT_CONFLICT in _codes(result)
    assert IntegrityFindingCode.COVERAGE_NOT_CERTIFIED in _codes(result)
    assert result.members is None
    assert result.coverage is not None
    assert result.coverage.satisfied is False


def test_classification_boundary_disagreement_yields_anchor_event_conflict() -> None:
    a = _dt(2026, 1, 10)
    tech = ClassificationValue(state=ClassificationState.CLASSIFIED, classification_id="TECH")
    finance = ClassificationValue(state=ClassificationState.CLASSIFIED, classification_id="FINANCE")
    anchor = ClassificationAnchor(
        instrument_id="I1", taxonomy_id="T1", value=tech, effective_at=a, available_at=_dt(2026, 1, 1)
    )
    boundary = ClassificationEvent(
        instrument_id="I1", taxonomy_id="T1", value=finance, effective_at=a, available_at=_dt(2026, 1, 10, 10)
    )
    facts = ClassificationFacts(instrument_id="I1", taxonomy_id="T1", anchors=(anchor,), events=(boundary,))

    result = resolve_classification(facts, as_of=a, decision_time=_dt(2026, 1, 11))

    assert result.status is CONFLICT
    assert IntegrityFindingCode.ANCHOR_EVENT_CONFLICT in _codes(result)
    assert result.value is None


def test_lifecycle_roundtrip_resolves_to_latest_state() -> None:
    a = _dt(2026, 1, 10)
    anchor = InstrumentLifecycleAnchor(
        instrument_id="I1", state=LifecycleState.LISTED, effective_at=a, available_at=_dt(2026, 1, 1)
    )
    e1 = InstrumentLifecycleEvent(
        instrument_id="I1", state=LifecycleState.NOT_LISTED, effective_at=_dt(2026, 1, 15), available_at=_dt(2026, 1, 15)
    )
    e2 = InstrumentLifecycleEvent(
        instrument_id="I1", state=LifecycleState.LISTED, effective_at=_dt(2026, 1, 20), available_at=_dt(2026, 1, 20)
    )
    facts = InstrumentLifecycleFacts(instrument_id="I1", anchors=(anchor,), events=(e1, e2))
    q = _dt(2026, 1, 25)
    fp = compute_instrument_lifecycle_event_slice_fingerprint(
        instrument_id="I1", coverage_start=a, coverage_end=q + timedelta(days=1), events=facts.events
    )
    cert = InstrumentLifecycleCoverageCertificate(
        instrument_id="I1", coverage_start=a, coverage_end=q + timedelta(days=1), certified_event_slice_fingerprint=fp
    )

    result = resolve_instrument_lifecycle(facts, as_of=q, decision_time=q, coverage_certificates=(cert,))

    assert result.status is RESOLVED
    assert result.state is LifecycleState.LISTED


# ---- Anchor selection failure modes ----


def test_no_visible_anchor_yields_indeterminate() -> None:
    u = "U1"
    facts = UniverseMembershipFacts(universe_id=u, anchors=(), events=())

    result = resolve_universe_membership(facts, as_of=_dt(2026, 1, 1), decision_time=_dt(2026, 1, 1))

    assert result.status is INDETERMINATE
    assert IntegrityFindingCode.NO_VISIBLE_ANCHOR in _codes(result)
    assert result.selected_anchor is None
    assert result.coverage is None
    assert result.members is None
    finding = next(f for f in result.findings if f.code is IntegrityFindingCode.NO_VISIBLE_ANCHOR)
    assert finding.effective_at is None
    assert finding.available_at is None
    assert finding.subject_id is None


def test_anchor_conflict_selected_anchor_and_coverage_are_none() -> None:
    u = "U1"
    a = _dt(2026, 1, 10)
    anchor_1 = UniverseMembershipAnchor(universe_id=u, members=frozenset({"A"}), effective_at=a, available_at=a)
    anchor_2 = UniverseMembershipAnchor(universe_id=u, members=frozenset({"B"}), effective_at=a, available_at=a)
    facts = UniverseMembershipFacts(universe_id=u, anchors=(anchor_1, anchor_2), events=())

    result = resolve_universe_membership(facts, as_of=a, decision_time=a)

    assert result.status is CONFLICT
    assert result.selected_anchor is None
    assert result.coverage is None
    assert result.members is None


# ---- Identity and enum invariants ----


@pytest.mark.parametrize("bad", ["", "  ", " x", "x ", 123, None, 4.5])
def test_identity_rejects_empty_blank_whitespace_and_non_string(bad) -> None:
    with pytest.raises(ValueError):
        UniverseMembershipEvent(
            universe_id="U1", instrument_id=bad, state=MembershipState.MEMBER,
            effective_at=_dt(2026, 1, 1), available_at=_dt(2026, 1, 1),
        )
    with pytest.raises(ValueError):
        UniverseMembershipAnchor(
            universe_id=bad, members=frozenset(), effective_at=_dt(2026, 1, 1), available_at=_dt(2026, 1, 1)
        )


def test_raw_enum_string_rejected() -> None:
    with pytest.raises(ValueError):
        UniverseMembershipEvent(
            universe_id="U1", instrument_id="X", state="member",  # type: ignore[arg-type]
            effective_at=_dt(2026, 1, 1), available_at=_dt(2026, 1, 1),
        )
    with pytest.raises(ValueError):
        InstrumentLifecycleAnchor(
            instrument_id="I1", state="listed",  # type: ignore[arg-type]
            effective_at=_dt(2026, 1, 1), available_at=_dt(2026, 1, 1),
        )


def test_classification_value_id_presence_matches_state() -> None:
    with pytest.raises(ValueError):
        ClassificationValue(state=ClassificationState.CLASSIFIED, classification_id=None)
    with pytest.raises(ValueError):
        ClassificationValue(state=ClassificationState.UNCLASSIFIED, classification_id="X")
    with pytest.raises(ValueError):
        ClassificationValue(state=ClassificationState.NOT_APPLICABLE, classification_id="X")

    # legal states construct cleanly
    ClassificationValue(state=ClassificationState.CLASSIFIED, classification_id="TECH")
    ClassificationValue(state=ClassificationState.UNCLASSIFIED, classification_id=None)
    ClassificationValue(state=ClassificationState.NOT_APPLICABLE, classification_id=None)


def test_facts_scope_coherence_enforced() -> None:
    a = _dt(2026, 1, 1)
    with pytest.raises(ValueError):
        UniverseMembershipFacts(
            universe_id="U1",
            anchors=(UniverseMembershipAnchor(universe_id="U2", members=frozenset(), effective_at=a, available_at=a),),
            events=(),
        )
    with pytest.raises(ValueError):
        InstrumentLifecycleFacts(
            instrument_id="I1",
            anchors=(InstrumentLifecycleAnchor(instrument_id="I2", state=LifecycleState.LISTED, effective_at=a, available_at=a),),
            events=(),
        )
    with pytest.raises(ValueError):
        ClassificationFacts(
            instrument_id="I1",
            taxonomy_id="T1",
            anchors=(
                ClassificationAnchor(
                    instrument_id="I1", taxonomy_id="T2",
                    value=ClassificationValue(state=ClassificationState.UNCLASSIFIED),
                    effective_at=a, available_at=a,
                ),
            ),
            events=(),
        )
    with pytest.raises(ValueError):
        ClassificationFacts(
            instrument_id="I1",
            taxonomy_id="T1",
            anchors=(),
            events=(
                ClassificationEvent(
                    instrument_id="I2", taxonomy_id="T1",
                    value=ClassificationValue(state=ClassificationState.UNCLASSIFIED),
                    effective_at=a, available_at=a,
                ),
            ),
        )


def test_facts_reject_non_tuple_anchors_and_events() -> None:
    a = _dt(2026, 1, 1)
    anchor = UniverseMembershipAnchor(universe_id="U1", members=frozenset(), effective_at=a, available_at=a)
    event = UniverseMembershipEvent(
        universe_id="U1", instrument_id="X", state=MembershipState.MEMBER, effective_at=a, available_at=a
    )

    with pytest.raises(ValueError):
        UniverseMembershipFacts(universe_id="U1", anchors=[anchor], events=())  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        UniverseMembershipFacts(universe_id="U1", anchors=(), events=[event])  # type: ignore[arg-type]

    lifecycle_anchor = InstrumentLifecycleAnchor(instrument_id="I1", state=LifecycleState.LISTED, effective_at=a, available_at=a)
    with pytest.raises(ValueError):
        InstrumentLifecycleFacts(instrument_id="I1", anchors=[lifecycle_anchor], events=())  # type: ignore[arg-type]

    classification_anchor = ClassificationAnchor(
        instrument_id="I1", taxonomy_id="T1",
        value=ClassificationValue(state=ClassificationState.UNCLASSIFIED),
        effective_at=a, available_at=a,
    )
    with pytest.raises(ValueError):
        ClassificationFacts(
            instrument_id="I1", taxonomy_id="T1", anchors=[classification_anchor], events=()  # type: ignore[arg-type]
        )


# ---- Coverage certificate scope/fingerprint validation ----


def test_coverage_certificate_wrong_scope_counted_and_unusable() -> None:
    u = "U1"
    a = _dt(2026, 1, 10)
    q = _dt(2026, 2, 1)
    anchor = UniverseMembershipAnchor(universe_id=u, members=frozenset({"X"}), effective_at=a, available_at=_dt(2026, 1, 1))
    facts = UniverseMembershipFacts(universe_id=u, anchors=(anchor,), events=())
    wrong_scope_fp = compute_universe_membership_event_slice_fingerprint(
        universe_id="OTHER", coverage_start=a, coverage_end=q + timedelta(days=1), events=()
    )
    cert = UniverseMembershipCoverageCertificate(
        universe_id="OTHER", coverage_start=a, coverage_end=q + timedelta(days=1), certified_event_slice_fingerprint=wrong_scope_fp
    )

    result = resolve_universe_membership(facts, as_of=q, decision_time=q, coverage_certificates=(cert,))

    assert result.coverage.scope_mismatch_count == 1
    assert result.coverage.merged_intervals == ()
    assert IntegrityFindingCode.COVERAGE_NOT_CERTIFIED in _codes(result)


def test_coverage_certificate_wrong_fingerprint_counted_and_unusable() -> None:
    u = "U1"
    a = _dt(2026, 1, 10)
    q = _dt(2026, 2, 1)
    anchor = UniverseMembershipAnchor(universe_id=u, members=frozenset({"X"}), effective_at=a, available_at=_dt(2026, 1, 1))
    facts = UniverseMembershipFacts(universe_id=u, anchors=(anchor,), events=())
    cert = UniverseMembershipCoverageCertificate(
        universe_id=u, coverage_start=a, coverage_end=q + timedelta(days=1), certified_event_slice_fingerprint="0" * 64
    )

    result = resolve_universe_membership(facts, as_of=q, decision_time=q, coverage_certificates=(cert,))

    assert result.coverage.fingerprint_mismatch_count == 1
    assert result.coverage.merged_intervals == ()


def test_extra_invalid_certificates_do_not_poison_valid_coverage() -> None:
    u = "U1"
    a = _dt(2026, 1, 10)
    q = _dt(2026, 2, 1)
    anchor = UniverseMembershipAnchor(universe_id=u, members=frozenset({"X"}), effective_at=a, available_at=_dt(2026, 1, 1))
    facts = UniverseMembershipFacts(universe_id=u, anchors=(anchor,), events=())
    end = q + timedelta(days=1)
    good_fp = compute_universe_membership_event_slice_fingerprint(
        universe_id=u, coverage_start=a, coverage_end=end, events=()
    )
    good_cert = UniverseMembershipCoverageCertificate(
        universe_id=u, coverage_start=a, coverage_end=end, certified_event_slice_fingerprint=good_fp
    )
    bad_scope = UniverseMembershipCoverageCertificate(
        universe_id="OTHER", coverage_start=a, coverage_end=end, certified_event_slice_fingerprint="1" * 64
    )
    bad_fp = UniverseMembershipCoverageCertificate(
        universe_id=u, coverage_start=a, coverage_end=end, certified_event_slice_fingerprint="2" * 64
    )

    result = resolve_universe_membership(
        facts, as_of=q, decision_time=q, coverage_certificates=(good_cert, bad_scope, bad_fp)
    )

    assert result.status is RESOLVED
    assert result.coverage.scope_mismatch_count == 1
    assert result.coverage.fingerprint_mismatch_count == 1
    assert result.coverage.valid_certificate_count == 1


def test_adjacent_and_overlapping_intervals_merge() -> None:
    u = "U1"
    a = _dt(2026, 1, 1)
    b = _dt(2026, 1, 10)
    c = _dt(2026, 1, 20)
    q = _dt(2026, 1, 25)
    anchor = UniverseMembershipAnchor(universe_id=u, members=frozenset(), effective_at=a, available_at=a)
    facts = UniverseMembershipFacts(universe_id=u, anchors=(anchor,), events=())
    fp1 = compute_universe_membership_event_slice_fingerprint(
        universe_id=u, coverage_start=a, coverage_end=b, events=()
    )
    fp2 = compute_universe_membership_event_slice_fingerprint(
        universe_id=u, coverage_start=b, coverage_end=c, events=()
    )
    fp3 = compute_universe_membership_event_slice_fingerprint(
        universe_id=u, coverage_start=c - timedelta(days=1), coverage_end=q + timedelta(days=1), events=()
    )
    cert1 = UniverseMembershipCoverageCertificate(universe_id=u, coverage_start=a, coverage_end=b, certified_event_slice_fingerprint=fp1)
    cert2 = UniverseMembershipCoverageCertificate(universe_id=u, coverage_start=b, coverage_end=c, certified_event_slice_fingerprint=fp2)
    cert3 = UniverseMembershipCoverageCertificate(
        universe_id=u, coverage_start=c - timedelta(days=1), coverage_end=q + timedelta(days=1), certified_event_slice_fingerprint=fp3
    )

    result = resolve_universe_membership(
        facts, as_of=q, decision_time=q, coverage_certificates=(cert1, cert2, cert3)
    )

    assert result.status is RESOLVED
    assert len(result.coverage.merged_intervals) == 1
    assert result.coverage.merged_intervals[0].start == a
    assert result.coverage.merged_intervals[0].end == q + timedelta(days=1)
    assert result.coverage.valid_certificate_count == 3


# ---- Blocker 1 regression: visibility must be filtered before effective-group selection ----


def test_membership_visible_event_wins_over_invisible_later_event() -> None:
    """Test A: a visible NON_MEMBER revision at Jan05 must win over a later,
    entirely-invisible MEMBER revision at Jan10 -- the invisible group must
    not mask the earlier visible one.
    """

    u = "U1"
    anchor = UniverseMembershipAnchor(
        universe_id=u, members=frozenset({"A"}), effective_at=_dt(2026, 1, 1), available_at=_dt(2026, 1, 1)
    )
    visible = UniverseMembershipEvent(
        universe_id=u, instrument_id="A", state=MembershipState.NON_MEMBER,
        effective_at=_dt(2026, 1, 5), available_at=_dt(2026, 1, 5),
    )
    invisible_later = UniverseMembershipEvent(
        universe_id=u, instrument_id="A", state=MembershipState.MEMBER,
        effective_at=_dt(2026, 1, 10), available_at=_dt(2026, 1, 20),
    )
    events = (visible, invisible_later)
    as_of = _dt(2026, 1, 15)
    decision_time = _dt(2026, 1, 15)
    fp = compute_universe_membership_event_slice_fingerprint(
        universe_id=u, coverage_start=_dt(2026, 1, 1), coverage_end=_dt(2026, 1, 16), events=events
    )
    cert = UniverseMembershipCoverageCertificate(
        universe_id=u, coverage_start=_dt(2026, 1, 1), coverage_end=_dt(2026, 1, 16), certified_event_slice_fingerprint=fp
    )
    facts = UniverseMembershipFacts(universe_id=u, anchors=(anchor,), events=events)

    result = resolve_universe_membership(
        facts, as_of=as_of, decision_time=decision_time, coverage_certificates=(cert,)
    )

    assert result.status is RESOLVED
    assert result.members == frozenset()


def test_membership_visible_conflict_not_masked_by_invisible_later_event() -> None:
    """Test B: a visible EVENT_CONFLICT at Jan05 must remain authoritative
    even when a later, entirely-invisible group exists at Jan10.
    """

    u = "U1"
    anchor = UniverseMembershipAnchor(
        universe_id=u, members=frozenset({"A"}), effective_at=_dt(2026, 1, 1), available_at=_dt(2026, 1, 1)
    )
    conflict_1 = UniverseMembershipEvent(
        universe_id=u, instrument_id="A", state=MembershipState.MEMBER,
        effective_at=_dt(2026, 1, 5), available_at=_dt(2026, 1, 5),
    )
    conflict_2 = UniverseMembershipEvent(
        universe_id=u, instrument_id="A", state=MembershipState.NON_MEMBER,
        effective_at=_dt(2026, 1, 5), available_at=_dt(2026, 1, 5),
    )
    invisible_later = UniverseMembershipEvent(
        universe_id=u, instrument_id="A", state=MembershipState.MEMBER,
        effective_at=_dt(2026, 1, 10), available_at=_dt(2026, 1, 20),
    )
    facts = UniverseMembershipFacts(
        universe_id=u, anchors=(anchor,), events=(conflict_1, conflict_2, invisible_later)
    )

    result = resolve_universe_membership(
        facts, as_of=_dt(2026, 1, 15), decision_time=_dt(2026, 1, 15)
    )

    assert result.status is CONFLICT
    assert IntegrityFindingCode.EVENT_CONFLICT in _codes(result)


def test_lifecycle_visible_event_wins_over_invisible_later_event() -> None:
    anchor = InstrumentLifecycleAnchor(
        instrument_id="I1", state=LifecycleState.LISTED, effective_at=_dt(2026, 1, 1), available_at=_dt(2026, 1, 1)
    )
    visible = InstrumentLifecycleEvent(
        instrument_id="I1", state=LifecycleState.NOT_LISTED, effective_at=_dt(2026, 1, 5), available_at=_dt(2026, 1, 5)
    )
    invisible_later = InstrumentLifecycleEvent(
        instrument_id="I1", state=LifecycleState.LISTED, effective_at=_dt(2026, 1, 10), available_at=_dt(2026, 1, 20)
    )
    events = (visible, invisible_later)
    fp = compute_instrument_lifecycle_event_slice_fingerprint(
        instrument_id="I1", coverage_start=_dt(2026, 1, 1), coverage_end=_dt(2026, 1, 16), events=events
    )
    cert = InstrumentLifecycleCoverageCertificate(
        instrument_id="I1", coverage_start=_dt(2026, 1, 1), coverage_end=_dt(2026, 1, 16), certified_event_slice_fingerprint=fp
    )
    facts = InstrumentLifecycleFacts(instrument_id="I1", anchors=(anchor,), events=events)

    result = resolve_instrument_lifecycle(
        facts, as_of=_dt(2026, 1, 15), decision_time=_dt(2026, 1, 15), coverage_certificates=(cert,)
    )

    assert result.status is RESOLVED
    assert result.state is LifecycleState.NOT_LISTED


def test_classification_visible_event_wins_over_invisible_later_event() -> None:
    tech = ClassificationValue(state=ClassificationState.CLASSIFIED, classification_id="TECH")
    unclassified = ClassificationValue(state=ClassificationState.UNCLASSIFIED)
    anchor = ClassificationAnchor(
        instrument_id="I1", taxonomy_id="T1", value=tech, effective_at=_dt(2026, 1, 1), available_at=_dt(2026, 1, 1)
    )
    visible = ClassificationEvent(
        instrument_id="I1", taxonomy_id="T1", value=unclassified, effective_at=_dt(2026, 1, 5), available_at=_dt(2026, 1, 5)
    )
    invisible_later = ClassificationEvent(
        instrument_id="I1", taxonomy_id="T1", value=tech, effective_at=_dt(2026, 1, 10), available_at=_dt(2026, 1, 20)
    )
    events = (visible, invisible_later)
    fp = compute_classification_event_slice_fingerprint(
        instrument_id="I1", taxonomy_id="T1", coverage_start=_dt(2026, 1, 1), coverage_end=_dt(2026, 1, 16), events=events
    )
    cert = ClassificationCoverageCertificate(
        instrument_id="I1", taxonomy_id="T1", coverage_start=_dt(2026, 1, 1), coverage_end=_dt(2026, 1, 16),
        certified_event_slice_fingerprint=fp,
    )
    facts = ClassificationFacts(instrument_id="I1", taxonomy_id="T1", anchors=(anchor,), events=events)

    result = resolve_classification(
        facts, as_of=_dt(2026, 1, 15), decision_time=_dt(2026, 1, 15), coverage_certificates=(cert,)
    )

    assert result.status is RESOLVED
    assert result.value == unclassified


def test_later_visible_resolved_supersedes_earlier_conflict_in_normal_events() -> None:
    u = "U1"
    anchor = UniverseMembershipAnchor(
        universe_id=u, members=frozenset({"A"}), effective_at=_dt(2026, 1, 1), available_at=_dt(2026, 1, 1)
    )
    conflict_1 = UniverseMembershipEvent(
        universe_id=u, instrument_id="A", state=MembershipState.MEMBER,
        effective_at=_dt(2026, 1, 5), available_at=_dt(2026, 1, 5),
    )
    conflict_2 = UniverseMembershipEvent(
        universe_id=u, instrument_id="A", state=MembershipState.NON_MEMBER,
        effective_at=_dt(2026, 1, 5), available_at=_dt(2026, 1, 5),
    )
    later_resolved = UniverseMembershipEvent(
        universe_id=u, instrument_id="A", state=MembershipState.MEMBER,
        effective_at=_dt(2026, 1, 10), available_at=_dt(2026, 1, 10),
    )
    events = (conflict_1, conflict_2, later_resolved)
    fp = compute_universe_membership_event_slice_fingerprint(
        universe_id=u, coverage_start=_dt(2026, 1, 1), coverage_end=_dt(2026, 1, 16), events=events
    )
    cert = UniverseMembershipCoverageCertificate(
        universe_id=u, coverage_start=_dt(2026, 1, 1), coverage_end=_dt(2026, 1, 16), certified_event_slice_fingerprint=fp
    )
    facts = UniverseMembershipFacts(universe_id=u, anchors=(anchor,), events=events)

    result = resolve_universe_membership(
        facts, as_of=_dt(2026, 1, 15), decision_time=_dt(2026, 1, 15), coverage_certificates=(cert,)
    )

    assert result.status is RESOLVED
    assert result.members == frozenset({"A"})


def test_later_visible_conflict_supersedes_earlier_resolved_in_normal_events() -> None:
    u = "U1"
    anchor = UniverseMembershipAnchor(
        universe_id=u, members=frozenset({"A"}), effective_at=_dt(2026, 1, 1), available_at=_dt(2026, 1, 1)
    )
    earlier_resolved = UniverseMembershipEvent(
        universe_id=u, instrument_id="A", state=MembershipState.NON_MEMBER,
        effective_at=_dt(2026, 1, 5), available_at=_dt(2026, 1, 5),
    )
    conflict_1 = UniverseMembershipEvent(
        universe_id=u, instrument_id="A", state=MembershipState.MEMBER,
        effective_at=_dt(2026, 1, 10), available_at=_dt(2026, 1, 10),
    )
    conflict_2 = UniverseMembershipEvent(
        universe_id=u, instrument_id="A", state=MembershipState.NON_MEMBER,
        effective_at=_dt(2026, 1, 10), available_at=_dt(2026, 1, 10),
    )
    events = (earlier_resolved, conflict_1, conflict_2)
    facts = UniverseMembershipFacts(universe_id=u, anchors=(anchor,), events=events)

    result = resolve_universe_membership(
        facts, as_of=_dt(2026, 1, 15), decision_time=_dt(2026, 1, 15)
    )

    assert result.status is CONFLICT
    assert IntegrityFindingCode.EVENT_CONFLICT in _codes(result)


# ---- Fingerprint properties ----


def test_fingerprint_reorder_invariant() -> None:
    u = "U1"
    start, end = _dt(2026, 1, 1), _dt(2026, 2, 1)
    e1 = UniverseMembershipEvent(universe_id=u, instrument_id="X", state=MembershipState.MEMBER, effective_at=_dt(2026, 1, 10), available_at=_dt(2026, 1, 10))
    e2 = UniverseMembershipEvent(universe_id=u, instrument_id="Y", state=MembershipState.NON_MEMBER, effective_at=_dt(2026, 1, 15), available_at=_dt(2026, 1, 15))

    fp_a = compute_universe_membership_event_slice_fingerprint(
        universe_id=u, coverage_start=start, coverage_end=end, events=[e1, e2]
    )
    fp_b = compute_universe_membership_event_slice_fingerprint(
        universe_id=u, coverage_start=start, coverage_end=end, events=[e2, e1]
    )

    assert fp_a == fp_b
    assert len(fp_a) == 64


def test_fingerprint_duplicate_collapse() -> None:
    u = "U1"
    start, end = _dt(2026, 1, 1), _dt(2026, 2, 1)
    e1 = UniverseMembershipEvent(universe_id=u, instrument_id="X", state=MembershipState.MEMBER, effective_at=_dt(2026, 1, 10), available_at=_dt(2026, 1, 10))

    fp_single = compute_universe_membership_event_slice_fingerprint(
        universe_id=u, coverage_start=start, coverage_end=end, events=[e1]
    )
    fp_dup = compute_universe_membership_event_slice_fingerprint(
        universe_id=u, coverage_start=start, coverage_end=end, events=[e1, e1, e1]
    )

    assert fp_single == fp_dup


def test_fingerprint_changes_when_event_inside_window_changes() -> None:
    u = "U1"
    start, end = _dt(2026, 1, 1), _dt(2026, 2, 1)
    e1 = UniverseMembershipEvent(universe_id=u, instrument_id="X", state=MembershipState.MEMBER, effective_at=_dt(2026, 1, 10), available_at=_dt(2026, 1, 10))
    e1_added = UniverseMembershipEvent(universe_id=u, instrument_id="W", state=MembershipState.MEMBER, effective_at=_dt(2026, 1, 20), available_at=_dt(2026, 1, 20))
    e1_revised = UniverseMembershipEvent(universe_id=u, instrument_id="X", state=MembershipState.MEMBER, effective_at=_dt(2026, 1, 10), available_at=_dt(2026, 1, 11))

    fp_base = compute_universe_membership_event_slice_fingerprint(
        universe_id=u, coverage_start=start, coverage_end=end, events=[e1]
    )
    fp_added = compute_universe_membership_event_slice_fingerprint(
        universe_id=u, coverage_start=start, coverage_end=end, events=[e1, e1_added]
    )
    fp_revised = compute_universe_membership_event_slice_fingerprint(
        universe_id=u, coverage_start=start, coverage_end=end, events=[e1_revised]
    )

    assert fp_base != fp_added
    assert fp_base != fp_revised


def test_fingerprint_unchanged_when_change_outside_window() -> None:
    u = "U1"
    start, end = _dt(2026, 1, 1), _dt(2026, 2, 1)
    e1 = UniverseMembershipEvent(universe_id=u, instrument_id="X", state=MembershipState.MEMBER, effective_at=_dt(2026, 1, 10), available_at=_dt(2026, 1, 10))
    e_outside = UniverseMembershipEvent(universe_id=u, instrument_id="Z", state=MembershipState.MEMBER, effective_at=_dt(2026, 3, 1), available_at=_dt(2026, 3, 1))

    fp_without = compute_universe_membership_event_slice_fingerprint(
        universe_id=u, coverage_start=start, coverage_end=end, events=[e1]
    )
    fp_with_outside = compute_universe_membership_event_slice_fingerprint(
        universe_id=u, coverage_start=start, coverage_end=end, events=[e1, e_outside]
    )

    assert fp_without == fp_with_outside


def test_fingerprint_unchanged_by_anchor_revision() -> None:
    """The fingerprint function accepts only events -- there is no parameter
    through which an anchor could ever participate.
    """

    params = set(
        inspect.signature(compute_universe_membership_event_slice_fingerprint).parameters
    )
    assert "anchor" not in params
    assert "anchors" not in params


def test_fingerprint_half_open_excludes_coverage_end() -> None:
    u = "U1"
    start, end = _dt(2026, 1, 1), _dt(2026, 2, 1)
    e1 = UniverseMembershipEvent(universe_id=u, instrument_id="X", state=MembershipState.MEMBER, effective_at=_dt(2026, 1, 10), available_at=_dt(2026, 1, 10))
    e_at_end = UniverseMembershipEvent(universe_id=u, instrument_id="V", state=MembershipState.MEMBER, effective_at=end, available_at=end)

    fp_without = compute_universe_membership_event_slice_fingerprint(
        universe_id=u, coverage_start=start, coverage_end=end, events=[e1]
    )
    fp_with_at_end = compute_universe_membership_event_slice_fingerprint(
        universe_id=u, coverage_start=start, coverage_end=end, events=[e1, e_at_end]
    )

    assert fp_without == fp_with_at_end


# ---- Golden fingerprint fixtures (hard-coded, not merely self-consistent) ----


def test_golden_fingerprint_membership() -> None:
    event = UniverseMembershipEvent(
        universe_id="GOLD-U1", instrument_id="A", state=MembershipState.MEMBER,
        effective_at=_dt(2024, 1, 10), available_at=_dt(2024, 1, 10),
    )
    fp = compute_universe_membership_event_slice_fingerprint(
        universe_id="GOLD-U1", coverage_start=_dt(2024, 1, 1), coverage_end=_dt(2024, 2, 1), events=[event]
    )
    assert fp == "ce6fa3e79394930d983ce3171813671debcd8ebebe236e6fe58cfb0ba6cbf1cc"


def test_golden_fingerprint_lifecycle() -> None:
    event = InstrumentLifecycleEvent(
        instrument_id="GOLD-I1", state=LifecycleState.NOT_LISTED,
        effective_at=_dt(2024, 1, 15), available_at=_dt(2024, 1, 15),
    )
    fp = compute_instrument_lifecycle_event_slice_fingerprint(
        instrument_id="GOLD-I1", coverage_start=_dt(2024, 1, 1), coverage_end=_dt(2024, 2, 1), events=[event]
    )
    assert fp == "09d75200372469c783605df37705ec67bab0af106f3bbb4df1d6ceceacd4cd43"


def test_golden_fingerprint_classification() -> None:
    event = ClassificationEvent(
        instrument_id="GOLD-I1", taxonomy_id="GOLD-T1",
        value=ClassificationValue(state=ClassificationState.CLASSIFIED, classification_id="TECH"),
        effective_at=_dt(2024, 1, 20), available_at=_dt(2024, 1, 20),
    )
    fp = compute_classification_event_slice_fingerprint(
        instrument_id="GOLD-I1", taxonomy_id="GOLD-T1", coverage_start=_dt(2024, 1, 1), coverage_end=_dt(2024, 2, 1), events=[event]
    )
    assert fp == "1ce32b84c761654b718625e7117a1e1bab0e2fd8340d9d8b97c1b0e051b9cae5"


# ---- CoverageDiagnostics invariant ----


def test_coverage_diagnostics_invariant_enforced() -> None:
    start, end = _dt(2026, 1, 1), _dt(2026, 2, 1)

    with pytest.raises(ValueError):
        CoverageDiagnostics(
            required=True,
            satisfied=True,
            required_start=start,
            required_through=end,
            valid_certificate_count=0,
            scope_mismatch_count=0,
            fingerprint_mismatch_count=0,
            merged_intervals=(),
            furthest_contiguous_end=None,
        )
    with pytest.raises(ValueError):
        CoverageDiagnostics(
            required=False,
            satisfied=True,
            required_start=start,
            required_through=end,
            valid_certificate_count=0,
            scope_mismatch_count=0,
            fingerprint_mismatch_count=0,
            merged_intervals=(),
            furthest_contiguous_end=None,
        )
    with pytest.raises(ValueError):
        CoverageDiagnostics(
            required=True,
            satisfied=False,
            required_start=end,
            required_through=start,
            valid_certificate_count=0,
            scope_mismatch_count=0,
            fingerprint_mismatch_count=0,
            merged_intervals=(),
            furthest_contiguous_end=None,
        )
    with pytest.raises(ValueError):
        CoverageDiagnostics(
            required=False,
            satisfied=True,
            required_start=start,
            required_through=start,
            valid_certificate_count=0,
            scope_mismatch_count=-1,
            fingerprint_mismatch_count=0,
            merged_intervals=(),
            furthest_contiguous_end=None,
        )
    with pytest.raises(ValueError):
        CoverageDiagnostics(
            required=False,
            satisfied=True,
            required_start=start,
            required_through=start,
            valid_certificate_count=0,
            scope_mismatch_count=0,
            fingerprint_mismatch_count=0,
            merged_intervals=(),
            furthest_contiguous_end=end,
        )

    good = _empty_coverage(start)
    assert good.satisfied is True


def test_coverage_diagnostics_valid_certificate_count_tracked() -> None:
    diagnostics = CoverageDiagnostics(
        required=True,
        satisfied=True,
        required_start=_dt(2026, 1, 1),
        required_through=_dt(2026, 1, 10),
        valid_certificate_count=3,
        scope_mismatch_count=1,
        fingerprint_mismatch_count=1,
        merged_intervals=(),
        furthest_contiguous_end=_dt(2026, 1, 20),
    )
    assert diagnostics.valid_certificate_count == 3


def test_coverage_diagnostics_not_required_populates_window() -> None:
    at = _dt(2026, 1, 1)
    diagnostics = _empty_coverage(at)
    assert diagnostics.required_start == at
    assert diagnostics.required_through == at
    assert diagnostics.furthest_contiguous_end is None


# ---- Fail-closed resolution invariants ----


def test_membership_resolved_requires_frozenset_and_no_findings() -> None:
    a = _dt(2026, 1, 1)
    anchor = UniverseMembershipAnchor(universe_id="U1", members=frozenset({"X"}), effective_at=a, available_at=a)
    with pytest.raises(ValueError):
        UniverseMembershipResolution(
            status=RESOLVED,
            universe_id="U1",
            as_of=a,
            decision_time=a,
            members=None,
            selected_anchor=anchor,
            coverage=_empty_coverage(a),
            findings=(),
        )


def test_membership_non_resolved_members_is_none() -> None:
    with pytest.raises(ValueError):
        UniverseMembershipResolution(
            status=INDETERMINATE,
            universe_id="U1",
            as_of=_dt(2026, 1, 1),
            decision_time=_dt(2026, 1, 1),
            members=frozenset({"X"}),
            selected_anchor=None,
            coverage=None,
            findings=(
                IntegrityFinding(
                    code=IntegrityFindingCode.NO_VISIBLE_ANCHOR, subject_id=None, effective_at=None, available_at=None
                ),
            ),
        )


def test_lifecycle_non_resolved_state_is_none() -> None:
    with pytest.raises(ValueError):
        InstrumentLifecycleResolution(
            status=INDETERMINATE,
            instrument_id="I1",
            as_of=_dt(2026, 1, 1),
            decision_time=_dt(2026, 1, 1),
            state=LifecycleState.LISTED,
            selected_anchor=None,
            coverage=None,
            findings=(
                IntegrityFinding(
                    code=IntegrityFindingCode.NO_VISIBLE_ANCHOR, subject_id=None, effective_at=None, available_at=None
                ),
            ),
        )


def test_classification_non_resolved_value_is_none() -> None:
    with pytest.raises(ValueError):
        ClassificationResolution(
            status=INDETERMINATE,
            instrument_id="I1",
            taxonomy_id="T1",
            as_of=_dt(2026, 1, 1),
            decision_time=_dt(2026, 1, 1),
            value=ClassificationValue(state=ClassificationState.UNCLASSIFIED),
            selected_anchor=None,
            coverage=None,
            findings=(
                IntegrityFinding(
                    code=IntegrityFindingCode.NO_VISIBLE_ANCHOR, subject_id=None, effective_at=None, available_at=None
                ),
            ),
        )


def test_findings_canonical_order_is_input_order_invariant() -> None:
    import itertools

    findings = [
        IntegrityFinding(code=IntegrityFindingCode.COVERAGE_GAP, subject_id=None, effective_at=None, available_at=None),
        IntegrityFinding(code=IntegrityFindingCode.EVENT_CONFLICT, subject_id="B", effective_at=_dt(2026, 1, 1), available_at=_dt(2026, 1, 1)),
        IntegrityFinding(code=IntegrityFindingCode.EVENT_CONFLICT, subject_id="A", effective_at=_dt(2026, 1, 1), available_at=_dt(2026, 1, 1)),
    ]
    kwargs = dict(
        universe_id="U1",
        as_of=_dt(2026, 1, 1),
        decision_time=_dt(2026, 1, 1),
        members=None,
        selected_anchor=None,
        coverage=None,
        status=CONFLICT,
    )
    results = [
        UniverseMembershipResolution(findings=tuple(p), **kwargs)
        for p in itertools.permutations(findings)
    ]
    for result in results:
        assert result.findings == results[0].findings
    assert [f.code for f in results[0].findings] == [
        IntegrityFindingCode.EVENT_CONFLICT,
        IntegrityFindingCode.EVENT_CONFLICT,
        IntegrityFindingCode.COVERAGE_GAP,
    ]
    assert [f.subject_id for f in results[0].findings[:2]] == ["A", "B"]


def test_status_precedence_conflict_over_indeterminate() -> None:
    findings = (
        IntegrityFinding(code=IntegrityFindingCode.EVENT_CONFLICT, subject_id="A", effective_at=_dt(2026, 1, 1), available_at=_dt(2026, 1, 1)),
        IntegrityFinding(code=IntegrityFindingCode.COVERAGE_GAP, subject_id=None, effective_at=None, available_at=None),
    )
    result = UniverseMembershipResolution(
        status=CONFLICT,
        universe_id="U1",
        as_of=_dt(2026, 1, 1),
        decision_time=_dt(2026, 1, 1),
        members=None,
        selected_anchor=None,
        coverage=None,
        findings=findings,
    )
    assert result.status is CONFLICT
    assert len(result.findings) == 2


# ---- Structural boundaries ----


def _module_tree():
    import ast

    from src.services.strategy_lab import universe_integrity

    return ast.parse(Path(universe_integrity.__file__).read_text(encoding="utf-8"))


def test_no_forbidden_imports() -> None:
    import ast

    forbidden_roots = {
        "screening",
        "stock_mapping",
        "stock_index_loader",
        "providers",
        "repositories",
        "trading_calendar",
        "information_dependency",
        "experiment_governance",
        "pandas",
        "numpy",
        "data_provider",
        "storage",
        "sqlalchemy",
        "walk_forward",
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
            if node.level == 0:
                assert not (node.module or "").startswith("src.services.strategy_lab") or (
                    node.module == "src.services.strategy_lab.temporal_contract"
                )
            else:
                # only the sibling temporal_contract module may be imported
                assert node.module == "temporal_contract"


# ---- Frozen public contract shape ----


def test_frozen_public_contract_shape() -> None:
    frozen_fields = {
        UniverseMembershipAnchor: ("universe_id", "members", "effective_at", "available_at"),
        UniverseMembershipEvent: (
            "universe_id",
            "instrument_id",
            "state",
            "effective_at",
            "available_at",
        ),
        UniverseMembershipFacts: ("universe_id", "anchors", "events"),
        InstrumentLifecycleAnchor: ("instrument_id", "state", "effective_at", "available_at"),
        InstrumentLifecycleEvent: ("instrument_id", "state", "effective_at", "available_at"),
        InstrumentLifecycleFacts: ("instrument_id", "anchors", "events"),
        ClassificationValue: ("state", "classification_id"),
        ClassificationAnchor: (
            "instrument_id",
            "taxonomy_id",
            "value",
            "effective_at",
            "available_at",
        ),
        ClassificationEvent: (
            "instrument_id",
            "taxonomy_id",
            "value",
            "effective_at",
            "available_at",
        ),
        ClassificationFacts: ("instrument_id", "taxonomy_id", "anchors", "events"),
        UniverseMembershipCoverageCertificate: (
            "universe_id",
            "coverage_start",
            "coverage_end",
            "certified_event_slice_fingerprint",
        ),
        InstrumentLifecycleCoverageCertificate: (
            "instrument_id",
            "coverage_start",
            "coverage_end",
            "certified_event_slice_fingerprint",
        ),
        ClassificationCoverageCertificate: (
            "instrument_id",
            "taxonomy_id",
            "coverage_start",
            "coverage_end",
            "certified_event_slice_fingerprint",
        ),
        CoverageDiagnostics: (
            "required",
            "satisfied",
            "required_start",
            "required_through",
            "valid_certificate_count",
            "scope_mismatch_count",
            "fingerprint_mismatch_count",
            "merged_intervals",
            "furthest_contiguous_end",
        ),
        IntegrityFinding: ("code", "subject_id", "effective_at", "available_at"),
        UniverseMembershipResolution: (
            "status",
            "universe_id",
            "as_of",
            "decision_time",
            "members",
            "selected_anchor",
            "coverage",
            "findings",
        ),
        InstrumentLifecycleResolution: (
            "status",
            "instrument_id",
            "as_of",
            "decision_time",
            "state",
            "selected_anchor",
            "coverage",
            "findings",
        ),
        ClassificationResolution: (
            "status",
            "instrument_id",
            "taxonomy_id",
            "as_of",
            "decision_time",
            "value",
            "selected_anchor",
            "coverage",
            "findings",
        ),
    }
    for cls, names in frozen_fields.items():
        assert dataclasses.is_dataclass(cls), cls.__name__
        actual = tuple(f.name for f in dataclasses.fields(cls))
        assert actual == names, f"{cls.__name__} field drift: {actual} != {names}"

    frozen_enum_members = {
        UniverseIntegrityResolutionStatus: {"RESOLVED", "INDETERMINATE", "CONFLICT"},
        MembershipState: {"MEMBER", "NON_MEMBER"},
        LifecycleState: {"LISTED", "NOT_LISTED"},
        ClassificationState: {"CLASSIFIED", "UNCLASSIFIED", "NOT_APPLICABLE"},
        IntegrityFindingCode: {
            "NO_VISIBLE_ANCHOR",
            "ANCHOR_CONFLICT",
            "ANCHOR_EVENT_CONFLICT",
            "COVERAGE_NOT_CERTIFIED",
            "COVERAGE_GAP",
            "COVERAGE_BOUNDARY_NOT_REACHED",
            "EVENT_CONFLICT",
        },
    }
    for enum_type, members in frozen_enum_members.items():
        assert {m.name for m in enum_type} == members, enum_type.__name__

    assert not hasattr(IntegrityFinding, "message")
    assert "message" not in {f.name for f in dataclasses.fields(IntegrityFinding)}
    assert "evidence" not in {f.name for f in dataclasses.fields(IntegrityFinding)}

    assert tuple(
        inspect.signature(compute_universe_membership_event_slice_fingerprint).parameters
    ) == ("universe_id", "coverage_start", "coverage_end", "events")
    assert tuple(
        inspect.signature(compute_instrument_lifecycle_event_slice_fingerprint).parameters
    ) == ("instrument_id", "coverage_start", "coverage_end", "events")
    assert tuple(
        inspect.signature(compute_classification_event_slice_fingerprint).parameters
    ) == ("instrument_id", "taxonomy_id", "coverage_start", "coverage_end", "events")
    assert tuple(inspect.signature(resolve_universe_membership).parameters) == (
        "facts",
        "as_of",
        "decision_time",
        "coverage_certificates",
    )
    assert tuple(inspect.signature(resolve_instrument_lifecycle).parameters) == (
        "facts",
        "as_of",
        "decision_time",
        "coverage_certificates",
    )
    assert tuple(inspect.signature(resolve_classification).parameters) == (
        "facts",
        "as_of",
        "decision_time",
        "coverage_certificates",
    )


def test_status_distinct_from_information_dependency_resolution_status() -> None:
    """This module must not import information_dependency at all, so there is
    no shared/aliased ResolutionStatus type -- verified structurally by the
    forbidden-imports test, and here by identity/name distinctness.
    """

    assert UniverseIntegrityResolutionStatus.__name__ == "UniverseIntegrityResolutionStatus"
    assert UniverseIntegrityResolutionStatus.__name__ != "ResolutionStatus"


def test_no_contract_fingerprint_property() -> None:
    for cls in (
        UniverseMembershipResolution,
        InstrumentLifecycleResolution,
        ClassificationResolution,
        UniverseMembershipCoverageCertificate,
        CoverageDiagnostics,
    ):
        assert not hasattr(cls, "contract_fingerprint")
        field_names = {f.name for f in dataclasses.fields(cls)}
        assert "contract_fingerprint" not in field_names


# ---- Permanent adversarial manifest ----


def test_permanent_universe_integrity_manifest_cannot_shrink() -> None:
    module_tests = set(globals())
    for test_id in PERMANENT_UNIVERSE_INTEGRITY_TEST_IDS:
        assert test_id.lower() in module_tests, f"missing permanent adversarial test: {test_id}"
    assert len(PERMANENT_UNIVERSE_INTEGRITY_TEST_IDS) == 57
