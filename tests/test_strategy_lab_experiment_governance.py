import itertools
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from src.services.strategy_lab.experiment_governance import (
    DEFINITION_DESCRIPTOR_FIELDS,
    RECOGNIZED_GOVERNED_COMPONENTS,
    ExperimentLineageAudit,
    ExperimentManifest,
    LineageAuditContext,
    LineageAuditVerdict,
    LineageViolation,
    LineageViolationCode,
    LineageViolationSeverity,
    ParameterOrigin,
    ParameterOriginType,
    audit_experiment_lineage,
)


UTC = timezone.utc

# Permanent adversarial manifest for this module. The key *set* of
# governed_components is deliberately NOT anti-shrink protected (governance
# coverage is expected to grow); this manifest protects the adversarial
# test IDs themselves, matching tests/test_strategy_lab_adversarial.py.
PERMANENT_GOVERNANCE_ADVERSARIAL_TEST_IDS = (
    "TEST_SAME_EXPERIMENT_ID_MANIFEST_MUTATION_REJECTED",
    "TEST_IDENTITY_FIELDS_EXCLUDED_FROM_HASH",
    "TEST_GOVERNED_COMPONENT_CHANGE_CHANGES_HASH",
    "TEST_MANIFEST_GOVERNED_COMPONENTS_CANNOT_MUTATE",
    "TEST_CALLER_CANNOT_FORGE_MANIFEST_HASH",
    "TEST_NAIVE_DATETIME_REJECTED",
    "TEST_FIXED_PARAMETER_WITHOUT_ORIGIN",
    "TEST_FIXED_PARAMETER_FROM_FUTURE_ORIGIN",
    "TEST_SELF_PARENT_DETECTED",
    "TEST_LINEAGE_CYCLE_DETECTED",
    "TEST_MISSING_PARENT_COMPLETENESS_AWARE",
    "TEST_CHILD_ROOT_MISMATCH_DETECTED",
    "TEST_AUDIT_ORDER_INVARIANCE",
    "TEST_CONFLICTING_PARENT_DEFINITION_ORDER_INVARIANCE",
    "TEST_CONFLICTING_ANCESTOR_DOES_NOT_DRIVE_ARBITRARY_LINEAGE_FACTS",
    "TEST_INDETERMINATE_AUDIT_EXPOSES_UNVERIFIABLE_CLAIMS",
    "TEST_PASS_HAS_NO_UNVERIFIABLE_CLAIMS",
)


def _dt(day: int = 10, hour: int = 12, tz: timezone = UTC) -> datetime:
    return datetime(2026, 1, day, hour, tzinfo=tz)


def _components(**overrides: str) -> dict[str, str]:
    base = {"strategy_config": "sc-1", "features": "f-1", "labels": "l-1"}
    base.update(overrides)
    return base


def _manifest(
    experiment_id: str = "exp-1",
    *,
    parent: str | None = None,
    root: str | None = None,
    components: dict[str, str] | None = None,
    schema_version: str = "experiment-manifest-v1",
    created_at: datetime | None = None,
) -> ExperimentManifest:
    return ExperimentManifest(
        experiment_id=experiment_id,
        schema_version=schema_version,
        governed_components=components if components is not None else _components(),
        created_at=created_at or _dt(),
        root_experiment_id=root if root is not None else experiment_id,
        parent_experiment_id=parent,
    )


def _origin(
    origin_type: ParameterOriginType = ParameterOriginType.LITERATURE,
    *,
    source_ref: str = "paper-2019",
    parameter_hash: str = "ph-1",
    declared_at: datetime | None = None,
    information_horizon_end: datetime | None = None,
    origin_experiment_id: str | None = None,
) -> ParameterOrigin:
    return ParameterOrigin(
        origin_type=origin_type,
        source_ref=source_ref,
        parameter_hash=parameter_hash,
        declared_at=declared_at or _dt(day=10),
        information_horizon_end=information_horizon_end or _dt(day=5),
        origin_experiment_id=origin_experiment_id,
    )


def _complete() -> LineageAuditContext:
    return LineageAuditContext(history_complete=True)


def _incomplete() -> LineageAuditContext:
    return LineageAuditContext(history_complete=False)


# ---- Manifest hash contract ----


def test_identity_fields_excluded_from_hash() -> None:
    """experiment_id / parent / root / created_at must not affect the hash."""

    base = _manifest("exp-1")
    renamed = _manifest("exp-999", root="exp-999")
    reparented = _manifest("exp-1", parent="exp-0", root="exp-0")
    retimed = _manifest("exp-1", created_at=_dt(day=28, hour=3))

    assert base.manifest_hash == renamed.manifest_hash
    assert base.manifest_hash == reparented.manifest_hash
    assert base.manifest_hash == retimed.manifest_hash


def test_governed_component_change_changes_hash() -> None:
    base = _manifest()
    changed_value = _manifest(components=_components(features="f-2"))
    added_key = _manifest(components=_components(universe_policy="up-1"))

    assert base.manifest_hash != changed_value.manifest_hash
    assert base.manifest_hash != added_key.manifest_hash


def test_schema_version_participates_in_hash() -> None:
    base = _manifest(schema_version="experiment-manifest-v1")
    bumped = _manifest(schema_version="experiment-manifest-v2")

    assert base.manifest_hash != bumped.manifest_hash


def test_manifest_hash_is_deterministic_and_key_order_invariant() -> None:
    forward = _manifest(components={"a_component": "1", "b_component": "2"})
    reversed_insert = _manifest(components={"b_component": "2", "a_component": "1"})

    assert forward.manifest_hash == reversed_insert.manifest_hash
    assert forward.manifest_hash == forward.manifest_hash
    assert len(forward.manifest_hash) == 64


def test_governed_components_are_defensively_copied() -> None:
    """Mutating the caller's original mapping cannot reach the manifest."""

    supplied = _components()
    manifest = _manifest(components=supplied)
    before = manifest.manifest_hash

    supplied["features"] = "mutated-after-construction"

    assert manifest.manifest_hash == before
    assert manifest.governed_components["features"] == "f-1"


def test_manifest_governed_components_cannot_mutate() -> None:
    """Governed components are definition identity, so the stored mapping
    itself must be read-only -- not merely a private copy.
    """

    manifest = _manifest()
    before = manifest.manifest_hash

    with pytest.raises(TypeError):
        manifest.governed_components["strategy_config"] = "changed"  # type: ignore[index]
    with pytest.raises(TypeError):
        del manifest.governed_components["strategy_config"]  # type: ignore[attr-defined]
    with pytest.raises(AttributeError):
        manifest.governed_components.update({"strategy_config": "changed"})  # type: ignore[attr-defined]
    with pytest.raises(AttributeError):
        manifest.governed_components.clear()  # type: ignore[attr-defined]

    assert manifest.manifest_hash == before
    assert manifest.governed_components["strategy_config"] == "sc-1"


def test_caller_cannot_forge_manifest_hash() -> None:
    """manifest_hash is derived and read-only: it can be neither injected at
    construction nor assigned afterwards.
    """

    manifest = _manifest()
    expected = manifest.manifest_hash

    with pytest.raises(TypeError):
        ExperimentManifest(
            experiment_id="exp-1",
            schema_version="experiment-manifest-v1",
            governed_components=_components(),
            created_at=_dt(),
            root_experiment_id="exp-1",
            manifest_hash="forged",  # type: ignore[call-arg]
        )

    with pytest.raises(AttributeError):
        manifest.manifest_hash = "forged"  # type: ignore[misc]

    assert type(manifest).__dict__["manifest_hash"].fset is None
    assert manifest.manifest_hash == expected


# ---- Open governed-component mapping (advisory recognition only) ----


def test_unknown_component_keys_are_accepted_and_surfaced_as_diagnostics() -> None:
    manifest = _manifest(components={"strategy_config": "sc-1", "feature": "typo-1"})

    assert manifest.governed_components["feature"] == "typo-1"
    assert manifest.unrecognized_component_keys == ("feature",)


def test_recognized_component_keys_produce_no_diagnostics() -> None:
    manifest = _manifest(
        components={"strategy_config": "sc-1", "parameter_origin": "po-1", "labels": "l-1"}
    )

    assert manifest.unrecognized_component_keys == ()
    assert "parameter_origin" in RECOGNIZED_GOVERNED_COMPONENTS


# ---- Narrow canonicalization: strict rejection, never coercion ----


@pytest.mark.parametrize(
    "components",
    [
        {1: "value"},
        {"key": 2},
        {"key": None},
        {"key": 3.5},
        {"": "value"},
        {"key": ""},
        {"key": {"nested": "value"}},
    ],
)
def test_malformed_components_are_rejected(components) -> None:
    with pytest.raises(ValueError):
        _manifest(components=components)


def test_empty_components_are_rejected() -> None:
    with pytest.raises(ValueError):
        _manifest(components={})


def test_non_mapping_components_are_rejected() -> None:
    with pytest.raises(ValueError):
        _manifest(components=[("strategy_config", "sc-1")])  # type: ignore[arg-type]


# ---- Temporal contract ----


def test_naive_datetime_rejected() -> None:
    with pytest.raises(ValueError):
        _manifest(created_at=datetime(2026, 1, 10, 12))

    with pytest.raises(ValueError):
        _origin(declared_at=datetime(2026, 1, 10, 12))

    with pytest.raises(ValueError):
        _origin(information_horizon_end=datetime(2026, 1, 5, 12))


def test_aware_datetimes_are_canonicalized_to_utc() -> None:
    plus_eight = timezone(timedelta(hours=8))
    manifest = _manifest(created_at=datetime(2026, 1, 10, 20, tzinfo=plus_eight))

    assert manifest.created_at.tzinfo is timezone.utc
    assert manifest.created_at == datetime(2026, 1, 10, 12, tzinfo=UTC)


def test_equivalent_instants_produce_identical_origin_fingerprints() -> None:
    plus_eight = timezone(timedelta(hours=8))
    utc_origin = _origin(declared_at=_dt(day=10, hour=12))
    shifted_origin = _origin(declared_at=datetime(2026, 1, 10, 20, tzinfo=plus_eight))

    assert utc_origin.fingerprint == shifted_origin.fingerprint


# ---- ParameterOrigin provenance rules ----


def test_fixed_parameter_without_origin() -> None:
    """PRIOR_EXPERIMENT provenance cannot omit its origin experiment."""

    with pytest.raises(ValueError):
        _origin(ParameterOriginType.PRIOR_EXPERIMENT, origin_experiment_id=None)


@pytest.mark.parametrize(
    "origin_type",
    [ParameterOriginType.LITERATURE, ParameterOriginType.MANUAL_PRIOR],
)
def test_non_experiment_origin_prohibits_origin_experiment_id(origin_type) -> None:
    with pytest.raises(ValueError):
        _origin(origin_type, origin_experiment_id="exp-1")


def test_prior_experiment_origin_accepts_origin_experiment_id() -> None:
    origin = _origin(ParameterOriginType.PRIOR_EXPERIMENT, origin_experiment_id="exp-1")

    assert origin.origin_experiment_id == "exp-1"


def test_fixed_parameter_from_future_origin() -> None:
    """information_horizon_end may never be later than declared_at."""

    with pytest.raises(ValueError):
        _origin(declared_at=_dt(day=5), information_horizon_end=_dt(day=10))


def test_horizon_equal_to_declared_at_is_allowed() -> None:
    origin = _origin(declared_at=_dt(day=10), information_horizon_end=_dt(day=10))

    assert origin.information_horizon_end == origin.declared_at


def test_origin_fingerprint_covers_every_provenance_field() -> None:
    base = _origin(ParameterOriginType.PRIOR_EXPERIMENT, origin_experiment_id="exp-1")
    variants = [
        _origin(ParameterOriginType.MANUAL_PRIOR),
        _origin(ParameterOriginType.PRIOR_EXPERIMENT, source_ref="other", origin_experiment_id="exp-1"),
        _origin(ParameterOriginType.PRIOR_EXPERIMENT, parameter_hash="ph-2", origin_experiment_id="exp-1"),
        _origin(
            ParameterOriginType.PRIOR_EXPERIMENT,
            declared_at=_dt(day=11),
            origin_experiment_id="exp-1",
        ),
        _origin(
            ParameterOriginType.PRIOR_EXPERIMENT,
            information_horizon_end=_dt(day=6),
            origin_experiment_id="exp-1",
        ),
        _origin(ParameterOriginType.PRIOR_EXPERIMENT, origin_experiment_id="exp-2"),
    ]

    for variant in variants:
        assert variant.fingerprint != base.fingerprint
    assert len(base.fingerprint) == 64


def test_origin_rejects_malformed_fields() -> None:
    with pytest.raises(ValueError):
        _origin(source_ref="")
    with pytest.raises(ValueError):
        _origin(parameter_hash="")
    with pytest.raises(ValueError):
        _origin("literature")  # type: ignore[arg-type]


# ---- Lineage audit ----


def test_clean_root_manifest_passes() -> None:
    audit = audit_experiment_lineage(manifest=_manifest("exp-1"), context=_complete())

    assert audit.verdict is LineageAuditVerdict.PASS
    assert audit.violations == ()


def test_clean_child_manifest_passes() -> None:
    root = _manifest("exp-1")
    child = _manifest("exp-2", parent="exp-1", root="exp-1")

    audit = audit_experiment_lineage(
        manifest=child, prior_manifests=[root], context=_complete()
    )

    assert audit.verdict is LineageAuditVerdict.PASS


def test_root_invariant_violation_when_root_does_not_self_reference() -> None:
    audit = audit_experiment_lineage(
        manifest=_manifest("exp-1", root="exp-other"), context=_complete()
    )

    assert audit.verdict is LineageAuditVerdict.VIOLATION
    assert {v.code for v in audit.violations} == {LineageViolationCode.ROOT_INVARIANT}


def test_root_invariant_violation_when_child_claims_itself_as_root() -> None:
    child = _manifest("exp-2", parent="exp-1", root="exp-2")
    audit = audit_experiment_lineage(
        manifest=child, prior_manifests=[_manifest("exp-1")], context=_complete()
    )

    assert audit.verdict is LineageAuditVerdict.VIOLATION
    assert LineageViolationCode.ROOT_INVARIANT in {v.code for v in audit.violations}


def test_child_root_mismatch_detected() -> None:
    root_a = _manifest("exp-1")
    root_b = _manifest("exp-9")
    child = _manifest("exp-2", parent="exp-1", root="exp-9")

    audit = audit_experiment_lineage(
        manifest=child, prior_manifests=[root_a, root_b], context=_complete()
    )

    assert audit.verdict is LineageAuditVerdict.VIOLATION
    mismatch = [v for v in audit.violations if v.code is LineageViolationCode.CHILD_ROOT_MISMATCH]
    assert len(mismatch) == 1
    assert mismatch[0].evidence["parent_root_experiment_id"] == "exp-1"


def test_missing_parent_completeness_aware() -> None:
    child = _manifest("exp-2", parent="exp-missing", root="exp-1")

    complete = audit_experiment_lineage(manifest=child, context=_complete())
    incomplete = audit_experiment_lineage(manifest=child, context=_incomplete())

    assert complete.verdict is LineageAuditVerdict.VIOLATION
    assert incomplete.verdict is LineageAuditVerdict.INDETERMINATE
    assert {v.code for v in complete.violations} == {LineageViolationCode.MISSING_PARENT}
    assert {v.code for v in incomplete.violations} == {LineageViolationCode.MISSING_PARENT}
    assert incomplete.violations[0].severity is LineageViolationSeverity.INDETERMINATE


def test_completeness_is_never_inferred_from_prior_manifests() -> None:
    """An empty history with history_complete=True must still be trusted."""

    child = _manifest("exp-2", parent="exp-1", root="exp-1")

    declared_complete = audit_experiment_lineage(
        manifest=child, prior_manifests=[], context=_complete()
    )

    assert declared_complete.verdict is LineageAuditVerdict.VIOLATION
    assert declared_complete.history_complete is True


def test_self_parent_detected() -> None:
    manifest = _manifest("exp-1", parent="exp-1", root="exp-0")

    audit = audit_experiment_lineage(manifest=manifest, context=_complete())

    assert audit.verdict is LineageAuditVerdict.VIOLATION
    codes = {v.code for v in audit.violations}
    assert LineageViolationCode.SELF_PARENT in codes
    assert LineageViolationCode.LINEAGE_CYCLE not in codes


def test_lineage_cycle_detected() -> None:
    a = _manifest("exp-a", parent="exp-b", root="exp-root")
    b = _manifest("exp-b", parent="exp-a", root="exp-root")

    audit = audit_experiment_lineage(manifest=a, prior_manifests=[b], context=_complete())

    assert audit.verdict is LineageAuditVerdict.VIOLATION
    cycle = [v for v in audit.violations if v.code is LineageViolationCode.LINEAGE_CYCLE]
    assert len(cycle) == 1
    assert "exp-a" in cycle[0].evidence["cycle"]


def test_same_experiment_id_manifest_mutation_rejected() -> None:
    """One experiment_id names exactly one manifest definition, permanently.

    No OOS-consumption state is involved: redefining an experiment is a
    lineage violation on its own.
    """

    original = _manifest("exp-1", components=_components(features="f-1"))
    mutated = _manifest("exp-1", components=_components(features="f-CHANGED"))

    audit = audit_experiment_lineage(
        manifest=mutated, prior_manifests=[original], context=_complete()
    )

    assert audit.verdict is LineageAuditVerdict.VIOLATION
    duplicates = [
        v for v in audit.violations
        if v.code is LineageViolationCode.DUPLICATE_EXPERIMENT_IDENTITY
    ]
    assert len(duplicates) == 1
    assert duplicates[0].evidence["experiment_id"] == "exp-1"
    assert duplicates[0].evidence["definition_fields"] == DEFINITION_DESCRIPTOR_FIELDS
    definitions = duplicates[0].evidence["definitions"]
    assert len(definitions) == 2
    assert definitions[0][0] != definitions[1][0]  # differing manifest_hash


def test_same_hash_parent_conflict_is_distinguishable_in_evidence() -> None:
    """A same-hash conflict must still identify what actually differs."""

    original = _manifest("exp-2", parent="exp-1", root="exp-1")
    reparented = _manifest("exp-2", parent="exp-9", root="exp-1")
    assert original.manifest_hash == reparented.manifest_hash

    audit = audit_experiment_lineage(
        manifest=reparented,
        prior_manifests=[original, _manifest("exp-1"), _manifest("exp-9")],
        context=_complete(),
    )

    duplicate = next(
        v for v in audit.violations
        if v.code is LineageViolationCode.DUPLICATE_EXPERIMENT_IDENTITY
    )
    definitions = duplicate.evidence["definitions"]
    assert duplicate.evidence["definition_fields"] == DEFINITION_DESCRIPTOR_FIELDS
    assert len(definitions) == 2
    assert definitions[0][0] == definitions[1][0]  # identical manifest_hash
    assert {definition[1] for definition in definitions} == {"exp-1", "exp-9"}  # parents differ


def test_identical_manifest_replay_is_not_a_duplicate_violation() -> None:
    original = _manifest("exp-1")
    replay = _manifest("exp-1")

    audit = audit_experiment_lineage(
        manifest=replay, prior_manifests=[original], context=_complete()
    )

    assert audit.verdict is LineageAuditVerdict.PASS


def test_same_experiment_id_with_conflicting_parent_is_rejected() -> None:
    original = _manifest("exp-2", parent="exp-1", root="exp-1")
    reparented = _manifest("exp-2", parent="exp-9", root="exp-1")

    audit = audit_experiment_lineage(
        manifest=reparented,
        prior_manifests=[original, _manifest("exp-1"), _manifest("exp-9")],
        context=_complete(),
    )

    assert audit.verdict is LineageAuditVerdict.VIOLATION
    assert LineageViolationCode.DUPLICATE_EXPERIMENT_IDENTITY in {
        v.code for v in audit.violations
    }


def test_audit_order_invariance() -> None:
    root = _manifest("exp-1")
    sibling = _manifest("exp-3", parent="exp-1", root="exp-1")
    conflicting = _manifest("exp-3", parent="exp-1", root="exp-1", components=_components(labels="l-X"))
    child = _manifest("exp-2", parent="exp-missing", root="exp-1")

    history = [root, sibling, conflicting]
    permutations = [
        list(history),
        list(reversed(history)),
        [history[1], history[2], history[0]],
        [history[2], history[0], history[1]],
    ]

    audits = [
        audit_experiment_lineage(
            manifest=child, prior_manifests=permutation, context=_complete()
        )
        for permutation in permutations
    ]

    first = audits[0]
    for audit in audits[1:]:
        assert audit.verdict is first.verdict
        assert audit.violations == first.violations
        assert audit == first


def test_conflicting_parent_definition_order_invariance() -> None:
    """A parent with conflicting definitions must not be silently resolved to
    whichever definition happened to arrive first.
    """

    child = _manifest("exp-c", parent="exp-p", root="exp-r")
    parent_a = _manifest("exp-p", parent=None, root="exp-p")
    parent_b = _manifest("exp-p", parent=None, root="exp-r")
    history = [parent_a, parent_b, _manifest("exp-r")]

    audits = [
        audit_experiment_lineage(
            manifest=child, prior_manifests=list(permutation), context=_complete()
        )
        for permutation in itertools.permutations(history)
    ]

    for audit in audits:
        assert audit == audits[0]
        codes = {v.code for v in audit.violations}
        # No definition was arbitrarily chosen, so no root comparison happened.
        assert LineageViolationCode.CHILD_ROOT_MISMATCH not in codes
        assert LineageViolationCode.MISSING_PARENT not in codes
        assert LineageViolationCode.DUPLICATE_EXPERIMENT_IDENTITY in codes
        assert LineageViolationCode.AMBIGUOUS_ANCESTOR in codes
    assert audits[0].unverifiable_claims != ()


def test_conflicting_ancestor_does_not_drive_arbitrary_lineage_facts() -> None:
    """One conflicting definition of a distant ancestor would close a cycle
    and the other would not; the audit must conclude neither.
    """

    child = _manifest("exp-c", parent="exp-b", root="exp-r")
    middle = _manifest("exp-b", parent="exp-a", root="exp-r")
    ancestor_acyclic = _manifest("exp-a", parent=None, root="exp-a")
    ancestor_cyclic = _manifest("exp-a", parent="exp-c", root="exp-r")
    history = [middle, ancestor_acyclic, ancestor_cyclic]

    audits = [
        audit_experiment_lineage(
            manifest=child, prior_manifests=list(permutation), context=_complete()
        )
        for permutation in itertools.permutations(history)
    ]

    for audit in audits:
        assert audit == audits[0]
        codes = {v.code for v in audit.violations}
        assert LineageViolationCode.LINEAGE_CYCLE not in codes
        assert LineageViolationCode.AMBIGUOUS_ANCESTOR in codes

    ambiguous = next(
        v for v in audits[0].violations if v.code is LineageViolationCode.AMBIGUOUS_ANCESTOR
    )
    assert ambiguous.evidence["ambiguous_ancestor_id"] == "exp-a"
    assert ambiguous.severity is LineageViolationSeverity.INDETERMINATE


def test_indeterminate_audit_exposes_unverifiable_claims() -> None:
    child = _manifest("exp-2", parent="exp-missing", root="exp-1")

    audit = audit_experiment_lineage(manifest=child, context=_incomplete())

    assert audit.verdict is LineageAuditVerdict.INDETERMINATE
    assert len(audit.unverifiable_claims) == 1
    claim = audit.unverifiable_claims[0]
    assert claim.code is LineageViolationCode.MISSING_PARENT
    assert claim.severity is LineageViolationSeverity.INDETERMINATE
    # Derived view, not a second source of truth.
    assert all(entry in audit.violations for entry in audit.unverifiable_claims)


def test_pass_has_no_unverifiable_claims() -> None:
    audit = audit_experiment_lineage(manifest=_manifest("exp-1"), context=_complete())

    assert audit.verdict is LineageAuditVerdict.PASS
    assert audit.unverifiable_claims == ()


def test_unverifiable_claims_exclude_hard_violations() -> None:
    manifest = _manifest("exp-2", parent="exp-missing", root="exp-2")

    audit = audit_experiment_lineage(manifest=manifest, context=_incomplete())

    assert audit.verdict is LineageAuditVerdict.VIOLATION
    assert {v.code for v in audit.unverifiable_claims} == {LineageViolationCode.MISSING_PARENT}
    assert all(
        v.severity is LineageViolationSeverity.INDETERMINATE for v in audit.unverifiable_claims
    )
    assert len(audit.unverifiable_claims) < len(audit.violations)


def test_violation_precedence_violation_dominates_indeterminate() -> None:
    manifest = _manifest("exp-2", parent="exp-missing", root="exp-2")

    audit = audit_experiment_lineage(manifest=manifest, context=_incomplete())

    severities = {v.severity for v in audit.violations}
    assert severities == {
        LineageViolationSeverity.VIOLATION,
        LineageViolationSeverity.INDETERMINATE,
    }
    assert audit.verdict is LineageAuditVerdict.VIOLATION


# ---- Fail-closed construction ----


def test_context_requires_real_bool() -> None:
    with pytest.raises(ValueError):
        LineageAuditContext(history_complete=1)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        LineageAuditContext(history_complete="yes")  # type: ignore[arg-type]


def test_audit_verdict_is_a_validated_derived_invariant() -> None:
    violation = LineageViolation(
        code=LineageViolationCode.SELF_PARENT,
        severity=LineageViolationSeverity.VIOLATION,
        message="m",
    )

    with pytest.raises(ValueError):
        ExperimentLineageAudit(
            experiment_id="exp-1",
            verdict=LineageAuditVerdict.PASS,
            violations=(violation,),
            history_complete=True,
        )


def test_audit_rejects_malformed_children_and_raw_enums() -> None:
    with pytest.raises(ValueError):
        ExperimentLineageAudit(
            experiment_id="exp-1",
            verdict="pass",  # type: ignore[arg-type]
            violations=(),
            history_complete=True,
        )
    with pytest.raises(ValueError):
        ExperimentLineageAudit(
            experiment_id="exp-1",
            verdict=LineageAuditVerdict.PASS,
            violations=("not_a_violation",),  # type: ignore[arg-type]
            history_complete=True,
        )
    with pytest.raises(ValueError):
        LineageViolation(
            code="self_parent",  # type: ignore[arg-type]
            severity=LineageViolationSeverity.VIOLATION,
            message="m",
        )
    with pytest.raises(ValueError):
        LineageViolation(
            code=LineageViolationCode.SELF_PARENT,
            severity="violation",  # type: ignore[arg-type]
            message="m",
        )


def test_manifest_rejects_empty_identifiers() -> None:
    with pytest.raises(ValueError):
        _manifest("")
    with pytest.raises(ValueError):
        _manifest(schema_version="")
    with pytest.raises(ValueError):
        _manifest("exp-2", parent="", root="exp-1")


# ---- Permanent adversarial manifest (test-ID level anti-shrink) ----


def test_permanent_governance_adversarial_manifest_cannot_shrink() -> None:
    module_tests = set(globals())
    for test_id in PERMANENT_GOVERNANCE_ADVERSARIAL_TEST_IDS:
        assert test_id.lower() in module_tests, f"missing permanent adversarial test: {test_id}"
    assert len(PERMANENT_GOVERNANCE_ADVERSARIAL_TEST_IDS) == 17


# ---- Performance isolation ----


def test_no_performance_report_dependency() -> None:
    """Permanent structural test, checked via the AST rather than a raw
    substring scan so module prose cannot trip it.
    """

    import ast

    from src.services.strategy_lab import experiment_governance

    source = Path(experiment_governance.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)

    forbidden_identifiers = {
        "performance_models",
        "PerformanceReport",
        "cagr",
        "sharpe",
        "max_drawdown",
        "profit_factor",
        "win_rate",
    }

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name.split(".")[-1] not in forbidden_identifiers
        elif isinstance(node, ast.ImportFrom):
            assert (node.module or "").split(".")[-1] not in forbidden_identifiers
            for alias in node.names:
                assert alias.name not in forbidden_identifiers
        elif isinstance(node, ast.Name):
            assert node.id not in forbidden_identifiers
        elif isinstance(node, ast.Attribute):
            assert node.attr not in forbidden_identifiers


def test_governance_module_is_a_leaf_within_strategy_lab() -> None:
    """No intra-package imports, so exporting it cannot create a cycle."""

    import ast

    from src.services.strategy_lab import experiment_governance

    source = Path(experiment_governance.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            assert node.level == 0, f"relative import found: {ast.dump(node)}"
            assert not (node.module or "").startswith("src.services.strategy_lab")
