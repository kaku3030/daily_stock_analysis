from dataclasses import replace
from datetime import datetime, timezone
from hashlib import sha256
import json

import pytest

import src.services.strategy_lab.provider_recorded_fixture as binding
from src.services.a_share_provider_lineage import RealtimeSourceLineage
from src.services.strategy_lab.provider_recorded_fixture import (
    A0_AUTHORITY_SOURCE_REF,
    A1_AUTHORITY_SOURCE_REF,
    NORMALIZER_SHA256,
    NORMALIZER_VERSION,
    PROVIDER_RECORDED_FIXTURE_SCHEMA_VERSION,
    VerifiedCapturedProviderAuthority,
    capture_current_a_share_provider_authority,
    convert_sealed_capture_to_provider_fixture,
    diagnose_current_provider_authority,
)
from src.services.strategy_lab.raw_capture import (
    NORMALIZATION_LINEAGE_VERSION,
    RAW_CAPTURE_MANIFEST_VERSION,
    encode_raw_capture,
    load_sealed_raw_capture,
)
from src.services.strategy_lab.recorded_fixture import REPRESENTATION_NORMALIZED_LICENSED_CSV
from src.services.strategy_lab.replay_contract import InMemoryEventStore, stable_hash

UTC = timezone.utc
TOOL_COMMIT = "05b872b2da9eb077070b4aa3ef1261671f3825ce"
TOOL_BLOB = "890e3bdca155e6eb65095d9ba7160aeba78a0f48"


def artifact_payload(*, status="OK", response="2026-09-10T10:00:01Z", rows=None, diagnostics=None):
    if rows is None:
        rows = [
            {
                "datetime": "2026-09-09T01:45:00+00:00",
                "open": "10.00",
                "high": "10.20",
                "low": "9.90",
                "close": "10.10",
                "volume": "12345",
            },
            {
                "datetime": "2026-09-09T02:00:00+00:00",
                "open": "10.10",
                "high": "10.30",
                "low": "10.00",
                "close": "10.25",
                "volume": "23456",
            },
        ]
    return {
        "schema_version": "raw-provider-capture-v0.1",
        "capture_id": "capture-akshare-em-aware-001",
        "provider_label": "AKSHARE_EASTMONEY_EVIDENCE_ONLY",
        "capture_tool_repository": "kaku3030/stock-razor",
        "capture_tool_path": "tools/provider_semantics/a_share/canonical_aware_fixture_probe.py",
        "capture_tool_commit_sha": TOOL_COMMIT,
        "capture_tool_blob_sha": TOOL_BLOB,
        "sdk_version": "research-fixture",
        "opend_version": "not-applicable",
        "artifact_created_at_utc": "2026-09-10T10:00:04Z",
        "observations": [
            {
                "observation_id": "history-cn-15m-1",
                "status": status,
                "operation": "history",
                "symbol": "000001.SZ",
                "ktype": "K_15M",
                "session": "REGULAR",
                "autype": "NONE",
                "request_params": {"trade_date": "2026-09-09"},
                "request_started_at_utc": "2026-09-10T10:00:00Z",
                "response_received_at_utc": response,
                "parent_observed_at_utc": "2026-09-10T10:00:02Z",
                "raw_payload": {"raw_rows": rows},
                "serialization_diagnostics": diagnostics or [],
            }
        ],
    }


def write_sealed(tmp_path, payload=None):
    payload = payload or artifact_payload()
    artifact_bytes = encode_raw_capture(payload)
    artifact_path = tmp_path / "capture.json"
    artifact_path.write_bytes(artifact_bytes)
    manifest = {
        "schema_version": RAW_CAPTURE_MANIFEST_VERSION,
        "capture_id": payload["capture_id"],
        "artifact_filename": artifact_path.name,
        "artifact_sha256": sha256(artifact_bytes).hexdigest(),
        "sealed_at_utc": "2026-09-10T10:00:05Z",
    }
    manifest_path = tmp_path / "capture.manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    return load_sealed_raw_capture(artifact_path, manifest_path)


def capture_authority(sealed):
    return capture_current_a_share_provider_authority(
        sealed,
        observation_id="history-cn-15m-1",
        source_token="akshare_em",
        endpoint_id="akshare.eastmoney_intraday",
        market="cn",
    )


def make_fixture(tmp_path):
    sealed = write_sealed(tmp_path)
    authority = capture_authority(sealed)
    fixture = convert_sealed_capture_to_provider_fixture(
        sealed,
        observation_id="history-cn-15m-1",
        authority=authority,
        fixture_id="provider-fixture-cn-001",
    )
    return sealed, authority, fixture


def test_a4b_keeps_a3_static_representation_unchanged_and_uses_separate_variant(tmp_path):
    _, _, fixture = make_fixture(tmp_path)
    assert REPRESENTATION_NORMALIZED_LICENSED_CSV == "NORMALIZED_FROM_LICENSED_PUBLIC_CSV"
    assert fixture.schema_version == PROVIDER_RECORDED_FIXTURE_SCHEMA_VERSION
    assert not hasattr(fixture, "representation")


def test_valid_verified_capture_converts_with_one_to_one_lineage(tmp_path):
    sealed, authority, fixture = make_fixture(tmp_path)
    assert len(fixture.rows) == len(fixture.row_lineages) == 2
    assert fixture.available_at == datetime(2026, 9, 10, 10, 0, 1, tzinfo=UTC)
    assert fixture.observed_at == datetime(2026, 9, 10, 10, 0, 2, tzinfo=UTC)
    assert fixture.authority.digest == authority.digest
    assert fixture.raw_artifact_sha256 == sealed.manifest.artifact_sha256
    assert fixture.normalizer_version == NORMALIZER_VERSION
    assert fixture.normalizer_sha256 == NORMALIZER_SHA256
    assert fixture.rows[0]["datetime"] == "2026-09-09T01:45:00.000000Z"
    assert fixture.row_lineages[1]["raw_path"].endswith("raw_rows[1]")
    assert all(item["schema_version"] == NORMALIZATION_LINEAGE_VERSION for item in fixture.row_lineages)


def test_verified_authority_cannot_be_constructed_directly():
    with pytest.raises(TypeError, match="capture-time factory"):
        VerifiedCapturedProviderAuthority()


def test_uninitialized_verified_authority_object_is_rejected_before_use(tmp_path):
    sealed = write_sealed(tmp_path)
    fake = object.__new__(VerifiedCapturedProviderAuthority)
    with pytest.raises(ValueError, match="not verified"):
        convert_sealed_capture_to_provider_fixture(
            sealed,
            observation_id="history-cn-15m-1",
            authority=fake,
            fixture_id="uninitialized-authority",
        )


def test_unverified_or_wrong_type_cannot_convert(tmp_path):
    _, authority, _ = make_fixture(tmp_path)
    with pytest.raises(ValueError, match="verified SealedRawCapture"):
        convert_sealed_capture_to_provider_fixture(
            object(),
            observation_id="history-cn-15m-1",
            authority=authority,
            fixture_id="bad",
        )


def test_capture_time_authority_is_digest_bound_to_raw_artifact(tmp_path):
    sealed, authority, _ = make_fixture(tmp_path)
    assert authority.raw_artifact_sha256 == sealed.manifest.artifact_sha256
    assert authority.captured_at == datetime(2026, 9, 10, 10, 0, 2, tzinfo=UTC)
    assert authority.a0_authority_source_ref == A0_AUTHORITY_SOURCE_REF
    assert authority.a1_authority_source_ref == A1_AUTHORITY_SOURCE_REF
    canonical = authority.canonical_payload()
    assert canonical["digest"] == stable_hash({k: v for k, v in canonical.items() if k != "digest"})


def test_internal_authority_payload_tamper_is_revalidated_before_conversion(tmp_path):
    sealed, authority, _ = make_fixture(tmp_path)
    object.__setattr__(authority._payload, "source_token", "forged")
    with pytest.raises(ValueError, match="digest mismatch"):
        convert_sealed_capture_to_provider_fixture(
            sealed,
            observation_id="history-cn-15m-1",
            authority=authority,
            fixture_id="tampered-authority",
        )


def test_wrong_source_endpoint_cannot_be_captured_as_a1_authority(tmp_path):
    sealed = write_sealed(tmp_path)
    with pytest.raises(ValueError, match="not admitted by accepted A1"):
        capture_current_a_share_provider_authority(
            sealed,
            observation_id="history-cn-15m-1",
            source_token="akshare_em",
            endpoint_id="akshare.eastmoney_spot",
        )


def test_unknown_source_cannot_be_captured_as_a0_authority(tmp_path):
    sealed = write_sealed(tmp_path)
    with pytest.raises(ValueError, match="not admitted by accepted A0"):
        capture_current_a_share_provider_authority(
            sealed,
            observation_id="history-cn-15m-1",
            source_token="unknown",
            endpoint_id="unknown.endpoint",
        )


def test_capture_factory_fails_loud_if_live_a0_no_longer_matches_pinned_source(monkeypatch, tmp_path):
    sealed = write_sealed(tmp_path)
    monkeypatch.setattr(binding, "CN_REALTIME_SOURCE_LINEAGE", {})
    with pytest.raises(RuntimeError, match="A0 provider authority changed"):
        capture_authority(sealed)


def test_current_authority_drift_is_diagnostic_only(monkeypatch, tmp_path):
    _, authority, fixture = make_fixture(tmp_path)
    original_digest = fixture.fixture_digest
    drifted = RealtimeSourceLineage(
        source_token="akshare_em",
        adapter_id="future-adapter",
        upstream_lineage_id="future-upstream",
        endpoint_id="future.endpoint",
        markets=("cn",),
    )
    monkeypatch.setattr(binding, "CN_REALTIME_SOURCE_LINEAGE", {"akshare_em": drifted})
    diagnostic = diagnose_current_provider_authority(authority)
    assert diagnostic.status == "CURRENT_AUTHORITY_DRIFT"
    assert "adapter_id" in diagnostic.differences
    assert fixture.fixture_digest == original_digest


def test_authority_bound_to_different_raw_artifact_fails_closed(tmp_path_factory):
    first = write_sealed(tmp_path_factory.mktemp("first"))
    payload = artifact_payload()
    payload["capture_id"] = "capture-akshare-em-aware-002"
    second = write_sealed(tmp_path_factory.mktemp("second"), payload)
    authority = capture_authority(first)
    with pytest.raises(ValueError, match="different raw artifact"):
        convert_sealed_capture_to_provider_fixture(
            second,
            observation_id="history-cn-15m-1",
            authority=authority,
            fixture_id="cross-bound",
        )


def test_naive_row_datetime_is_never_localized_by_guesswork(tmp_path):
    payload = artifact_payload()
    payload["observations"][0]["raw_payload"]["raw_rows"][0]["datetime"] = "2026-09-09T09:45:00"
    sealed = write_sealed(tmp_path, payload)
    authority = capture_authority(sealed)
    with pytest.raises(ValueError, match="must be timezone-aware"):
        convert_sealed_capture_to_provider_fixture(
            sealed,
            observation_id="history-cn-15m-1",
            authority=authority,
            fixture_id="naive-row",
        )


def test_numeric_float_is_not_silently_coerced_to_decimal_text(tmp_path):
    payload = artifact_payload()
    payload["observations"][0]["raw_payload"]["raw_rows"][0]["open"] = 10.0
    sealed = write_sealed(tmp_path, payload)
    authority = capture_authority(sealed)
    with pytest.raises(ValueError, match="non-empty trimmed string"):
        convert_sealed_capture_to_provider_fixture(
            sealed,
            observation_id="history-cn-15m-1",
            authority=authority,
            fixture_id="numeric-coercion",
        )


def test_empty_raw_rows_cannot_become_provider_recorded_fixture(tmp_path):
    sealed = write_sealed(tmp_path, artifact_payload(rows=[]))
    authority = capture_authority(sealed)
    with pytest.raises(ValueError, match="non-empty raw_rows"):
        convert_sealed_capture_to_provider_fixture(
            sealed,
            observation_id="history-cn-15m-1",
            authority=authority,
            fixture_id="empty",
        )


def test_timeout_or_non_pit_observation_cannot_convert(tmp_path_factory):
    authority = capture_authority(write_sealed(tmp_path_factory.mktemp("authority")))
    sealed = write_sealed(
        tmp_path_factory.mktemp("timeout"),
        artifact_payload(status="TIMEOUT", response=None),
    )
    with pytest.raises(ValueError, match="not eligible for point-in-time"):
        convert_sealed_capture_to_provider_fixture(
            sealed,
            observation_id="history-cn-15m-1",
            authority=authority,
            fixture_id="timeout",
        )


def test_serialization_diagnostic_blocks_conversion(tmp_path_factory):
    authority = capture_authority(write_sealed(tmp_path_factory.mktemp("authority")))
    sealed = write_sealed(
        tmp_path_factory.mktemp("diagnostic"),
        artifact_payload(diagnostics=["upstream coercion observed"]),
    )
    with pytest.raises(ValueError, match="not eligible for point-in-time"):
        convert_sealed_capture_to_provider_fixture(
            sealed,
            observation_id="history-cn-15m-1",
            authority=authority,
            fixture_id="diag",
        )


def test_event_time_after_verified_available_at_fails_closed(tmp_path):
    payload = artifact_payload()
    payload["observations"][0]["raw_payload"]["raw_rows"][1]["datetime"] = "2026-09-10T10:00:01.500000Z"
    sealed = write_sealed(tmp_path, payload)
    authority = capture_authority(sealed)
    with pytest.raises(ValueError, match="after verified available_at"):
        convert_sealed_capture_to_provider_fixture(
            sealed,
            observation_id="history-cn-15m-1",
            authority=authority,
            fixture_id="future-row",
        )


def test_lineage_count_mismatch_fails_closed(tmp_path):
    _, _, fixture = make_fixture(tmp_path)
    with pytest.raises(ValueError, match="one-to-one normalization lineage"):
        replace(fixture, row_lineages=fixture.row_lineages[:-1])


def test_stale_tampered_lineage_digest_fails_closed(tmp_path):
    _, _, fixture = make_fixture(tmp_path)
    first = dict(fixture.row_lineages[0])
    first["lineage_digest"] = "0" * 64
    tampered = (first, *fixture.row_lineages[1:])
    with pytest.raises(ValueError, match="normalization lineage digest mismatch"):
        replace(fixture, row_lineages=tampered)


def test_unknown_lineage_schema_cannot_be_rehashed_into_acceptance(tmp_path):
    _, _, fixture = make_fixture(tmp_path)
    first = dict(fixture.row_lineages[0])
    first["schema_version"] = "raw-normalization-lineage-v999"
    first["lineage_digest"] = stable_hash({k: v for k, v in first.items() if k != "lineage_digest"})
    tampered = (first, *fixture.row_lineages[1:])
    with pytest.raises(ValueError, match="lineage version mismatch"):
        replace(fixture, row_lineages=tampered)


def test_reordered_lineage_fails_closed(tmp_path):
    _, _, fixture = make_fixture(tmp_path)
    with pytest.raises(ValueError, match="row order/path mismatch"):
        replace(fixture, row_lineages=tuple(reversed(fixture.row_lineages)))


def test_identical_conversion_is_100_of_100_deterministic(tmp_path):
    sealed = write_sealed(tmp_path)
    authority = capture_authority(sealed)
    digests = {
        convert_sealed_capture_to_provider_fixture(
            sealed,
            observation_id="history-cn-15m-1",
            authority=authority,
            fixture_id="deterministic",
        ).fixture_digest
        for _ in range(100)
    }
    assert len(digests) == 1


def test_raw_artifact_tamper_after_load_is_reverified_before_conversion(tmp_path):
    sealed = write_sealed(tmp_path)
    authority = capture_authority(sealed)
    object.__setattr__(sealed, "_artifact_bytes", sealed._artifact_bytes + b"\n")
    with pytest.raises(ValueError, match="digest verification failed"):
        convert_sealed_capture_to_provider_fixture(
            sealed,
            observation_id="history-cn-15m-1",
            authority=authority,
            fixture_id="tamper",
        )


def test_materialized_events_retain_raw_authority_lineage_and_entry_gate_closed(tmp_path):
    _, authority, fixture = make_fixture(tmp_path)
    events = fixture.materialize_events()
    assert len(events) == 2
    assert all(event.source_kind == "PROVIDER" for event in events)
    assert all(event.source_token == "akshare_em" for event in events)
    assert all(event.endpoint_id == "akshare.eastmoney_intraday" for event in events)
    assert all(event.payload["provider_authority_digest"] == authority.digest for event in events)
    assert all(event.payload["raw_artifact_sha256"] == fixture.raw_artifact_sha256 for event in events)
    assert all(event.payload["entry_gate"] == "CLOSED" for event in events)


def test_historical_resolver_admits_events_without_consulting_current_manifest(monkeypatch, tmp_path):
    _, _, fixture = make_fixture(tmp_path)
    monkeypatch.setattr(binding, "CN_REALTIME_SOURCE_LINEAGE", {})
    monkeypatch.setattr(binding, "CN_INTRADAY_ENDPOINT_EXTENSIONS", {})
    store = InMemoryEventStore(source_authority_resolver=fixture.historical_authority_resolver())
    for event in fixture.materialize_events():
        assert store.append(event) == "ACCEPTED"
    assert all("captured-provider-authority:sha256:" in event.source_authority_ref for event in store.events)


def test_conversion_has_no_current_registry_or_provider_side_effect_dependency(monkeypatch, tmp_path):
    sealed, authority, _ = make_fixture(tmp_path)

    class ExplodingRegistry:
        def get(self, *args, **kwargs):
            raise AssertionError("conversion must not consult current registry")

    monkeypatch.setattr(binding, "CN_REALTIME_SOURCE_LINEAGE", ExplodingRegistry())
    monkeypatch.setattr(binding, "CN_INTRADAY_ENDPOINT_EXTENSIONS", ExplodingRegistry())
    fixture = convert_sealed_capture_to_provider_fixture(
        sealed,
        observation_id="history-cn-15m-1",
        authority=authority,
        fixture_id="side-effect-free",
    )
    assert len(fixture.rows) == 2
