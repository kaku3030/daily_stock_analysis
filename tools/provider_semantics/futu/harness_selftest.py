"""Self-tests for harness MECHANICS only.

These tests verify the recorder/model plumbing works correctly (JSONL
append, immutability, UTC timestamps, monotonic sequencing, secret
scrubbing, result-status validation). They use a mocked/fake callback only
to exercise that plumbing -- nothing here tests or claims anything about
real Futu provider semantics. Any actual provider-semantics claim must come
from a live run against a reachable OpenD (see wave1_runner.py), never from
these mocks.

Run with:
    python -m pytest harness_selftest.py -v
"""

from __future__ import annotations

import json
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from models import SemanticTestResult, TestStatus, raw_event, scrub_secrets  # noqa: E402
from recorder import EvidenceRecorder, new_run_dir, utc_now_iso  # noqa: E402


@pytest.fixture
def tmp_runs_dir(tmp_path):
    return tmp_path / "runs"


def test_new_run_dir_is_unique_and_does_not_collide(tmp_runs_dir):
    tmp_runs_dir.mkdir()
    first = new_run_dir(tmp_runs_dir)
    first.mkdir()
    second = new_run_dir(tmp_runs_dir)
    assert first != second
    assert not second.exists()


def test_jsonl_append_preserves_order_and_content(tmp_runs_dir):
    run_dir = new_run_dir(tmp_runs_dir)
    recorder = EvidenceRecorder(run_dir)

    recorder.record_event(
        provider="futu", market="HK", symbol="HK.00700", stream_type="QUOTE",
        event_type="push", raw_payload={"last_price": 100.0},
    )
    recorder.record_event(
        provider="futu", market="HK", symbol="HK.00700", stream_type="QUOTE",
        event_type="push", raw_payload={"last_price": 101.0},
    )

    events = recorder.read_events()
    assert len(events) == 2
    assert events[0]["raw_payload"]["last_price"] == 100.0
    assert events[1]["raw_payload"]["last_price"] == 101.0
    assert events[0]["event_seq_local"] < events[1]["event_seq_local"]

    # File is genuinely append-only JSONL: two lines, each valid JSON.
    lines = (run_dir / "events.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    for line in lines:
        json.loads(line)  # must not raise


def test_second_recorder_cannot_reuse_a_run_dir(tmp_runs_dir):
    run_dir = new_run_dir(tmp_runs_dir)
    EvidenceRecorder(run_dir)
    with pytest.raises(FileExistsError):
        EvidenceRecorder(run_dir)


def test_metadata_cannot_be_overwritten(tmp_runs_dir):
    run_dir = new_run_dir(tmp_runs_dir)
    recorder = EvidenceRecorder(run_dir)
    recorder.write_metadata({"a": 1})
    with pytest.raises(FileExistsError):
        recorder.write_metadata({"a": 2})
    # Original content survives untouched.
    assert json.loads((run_dir / "metadata.json").read_text(encoding="utf-8"))["a"] == 1


def test_observations_and_results_cannot_be_overwritten(tmp_runs_dir):
    run_dir = new_run_dir(tmp_runs_dir)
    recorder = EvidenceRecorder(run_dir)
    recorder.write_observations({"x": 1})
    with pytest.raises(FileExistsError):
        recorder.write_observations({"x": 2})
    recorder.write_results([{"test_id": "F01"}])
    with pytest.raises(FileExistsError):
        recorder.write_results([{"test_id": "F02"}])


def test_events_file_is_never_reopened_in_write_truncate_mode(tmp_runs_dir):
    """Guards against a future edit accidentally switching append -> write."""

    run_dir = new_run_dir(tmp_runs_dir)
    recorder = EvidenceRecorder(run_dir)
    recorder.record_event(provider="futu", market=None, symbol=None, stream_type="QUOTE", event_type="push", raw_payload={"n": 1})
    size_after_first = (run_dir / "events.jsonl").stat().st_size
    recorder.record_event(provider="futu", market=None, symbol=None, stream_type="QUOTE", event_type="push", raw_payload={"n": 2})
    size_after_second = (run_dir / "events.jsonl").stat().st_size
    assert size_after_second > size_after_first  # grew, was not truncated


def test_utc_now_iso_is_timezone_aware_and_utc():
    text = utc_now_iso()
    parsed = datetime.fromisoformat(text)
    assert parsed.tzinfo is not None
    assert parsed.utcoffset().total_seconds() == 0


def test_monotonic_sequence_strictly_increasing_under_concurrency(tmp_runs_dir):
    run_dir = new_run_dir(tmp_runs_dir)
    recorder = EvidenceRecorder(run_dir)
    seqs: list[int] = []
    lock = threading.Lock()

    def worker():
        for _ in range(50):
            seq = recorder.next_seq()
            with lock:
                seqs.append(seq)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(seqs) == len(set(seqs)), "sequence numbers must never repeat across threads"
    assert sorted(seqs) == list(range(1, len(seqs) + 1))


def test_secrets_are_scrubbed_before_touching_disk(tmp_runs_dir):
    run_dir = new_run_dir(tmp_runs_dir)
    recorder = EvidenceRecorder(run_dir)
    recorder.record_event(
        provider="futu", market=None, symbol=None, stream_type="QUOTE", event_type="push",
        raw_payload={"last_price": 1.0, "api_key": "SECRET-VALUE-123", "nested": {"access_token": "SECRET-TOKEN"}},
    )
    raw_text = (run_dir / "events.jsonl").read_text(encoding="utf-8")
    assert "SECRET-VALUE-123" not in raw_text
    assert "SECRET-TOKEN" not in raw_text
    events = recorder.read_events()
    assert events[0]["raw_payload"]["api_key"] == "<redacted-by-harness>"
    assert events[0]["raw_payload"]["nested"]["access_token"] == "<redacted-by-harness>"
    # Non-secret fields survive untouched.
    assert events[0]["raw_payload"]["last_price"] == 1.0


def test_scrub_secrets_is_pure_and_recursive():
    payload = {"password": "x", "list": [{"token": "y"}, {"ok": "z"}]}
    scrubbed = scrub_secrets(payload)
    assert scrubbed["password"] == "<redacted-by-harness>"
    assert scrubbed["list"][0]["token"] == "<redacted-by-harness>"
    assert scrubbed["list"][1]["ok"] == "z"
    # Original input is untouched (pure function).
    assert payload["password"] == "x"


def test_result_requires_valid_status_enum():
    with pytest.raises(ValueError):
        SemanticTestResult(
            test_id="F01", provider="futu", sdk_version="1", opend_version="1",
            started_at_utc=utc_now_iso(), ended_at_utc=utc_now_iso(),
            market="HK", symbol="HK.00700", stream_type="QUOTE",
            precondition="p", action="a", raw_evidence_paths=["events.jsonl"],
            status="VERIFIED",  # str, not TestStatus -- must be rejected
            observations=[], limitations=[], implementation_consequence="c",
        )


def test_result_requires_at_least_one_raw_evidence_path():
    with pytest.raises(ValueError):
        SemanticTestResult(
            test_id="F01", provider="futu", sdk_version="1", opend_version="1",
            started_at_utc=utc_now_iso(), ended_at_utc=utc_now_iso(),
            market="HK", symbol="HK.00700", stream_type="QUOTE",
            precondition="p", action="a", raw_evidence_paths=[],
            status=TestStatus.UNRESOLVED,
            observations=[], limitations=[], implementation_consequence="c",
        )


def test_result_to_dict_round_trips_status_as_plain_string():
    result = SemanticTestResult(
        test_id="F01", provider="futu", sdk_version="1", opend_version="1",
        started_at_utc=utc_now_iso(), ended_at_utc=utc_now_iso(),
        market="HK", symbol="HK.00700", stream_type="QUOTE",
        precondition="p", action="a", raw_evidence_paths=["events.jsonl"],
        status=TestStatus.PARTIALLY_VERIFIED,
        observations=["obs"], limitations=["lim"], implementation_consequence="c",
    )
    payload = result.to_dict()
    assert payload["semantic_result"]["status"] == "PARTIALLY_VERIFIED"
    json.dumps(payload)  # must be JSON-serializable end to end


class _FakeMockedProviderCallback:
    """A fake callback shape used ONLY to prove the recorder can ingest a
    provider-shaped payload without special-casing it. This does NOT stand
    in for -- and must never be cited as evidence about -- real Futu
    behavior.
    """

    def __init__(self, recorder: EvidenceRecorder):
        self._recorder = recorder

    def deliver(self, symbol: str, payload: dict) -> None:
        self._recorder.record_event(
            provider="futu-MOCK-FOR-MECHANICS-TEST-ONLY",
            market="HK",
            symbol=symbol,
            stream_type="QUOTE",
            event_type="push",
            raw_payload=payload,
        )


def test_recorder_ingests_a_mocked_callback_shape_without_dropping_fields(tmp_runs_dir):
    run_dir = new_run_dir(tmp_runs_dir)
    recorder = EvidenceRecorder(run_dir)
    fake = _FakeMockedProviderCallback(recorder)
    fake.deliver("HK.00700", {"data_time": "2026-01-01 10:00:00", "last_price": 300.0, "odd_field_1": "keep-me"})

    events = recorder.read_events()
    assert len(events) == 1
    assert events[0]["provider"] == "futu-MOCK-FOR-MECHANICS-TEST-ONLY"
    assert events[0]["raw_payload"]["odd_field_1"] == "keep-me", "fields must not be dropped for looking irrelevant"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
