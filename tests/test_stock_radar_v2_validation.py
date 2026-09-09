from copy import deepcopy
from datetime import date, datetime, timedelta, timezone

import pytest

from src.services.stock_radar_v2.notifications import RadarNotifier
from src.services.stock_radar_v2.validation import DailyQA, ValidationQueue, WeeklyCalibration


def _resolved(queue: ValidationQueue, signal_type: str, outcomes: list[str]) -> None:
    for index, outcome in enumerate(outcomes):
        item = queue.enqueue(
            signal_id=f"{signal_type}-{index}",
            signal_type=signal_type,
            signal_state="confirmed",
            evidence={"index": index},
        )
        queue.resolve(item.validation_id, outcome)


def test_validation_queue_only_accepts_confirmed_signals() -> None:
    queue = ValidationQueue()
    with pytest.raises(ValueError, match="Confirmed"):
        queue.enqueue(signal_id="s1", signal_type="breakout", signal_state="candidate")


def test_queue_lists_signal_types_and_persisted_calibration_reviews() -> None:
    queue = ValidationQueue()
    _resolved(queue, "breakout", ["failed"] * 7 + ["passed"] * 3)
    _resolved(queue, "reversal", ["passed"])

    WeeklyCalibration(queue).evaluate("breakout", production_weights={})

    assert queue.signal_types() == ["breakout", "reversal"]
    reviews = queue.calibration_reviews()
    assert reviews[0]["signal_type"] == "breakout"
    assert reviews[0]["requires_manual_promotion"] == 1


def test_daily_qa_summarizes_without_changing_signal() -> None:
    queue = ValidationQueue()
    signal = {"id": "s1", "state": "confirmed", "signal_confidence": 72}
    before = deepcopy(signal)
    item = queue.enqueue(
        signal_id=signal["id"],
        signal_type="breakout",
        signal_state=signal["state"],
        created_at=datetime.now(timezone.utc),
    )
    queue.resolve(item.validation_id, "failed")

    summary = DailyQA(queue).summarize("breakout")

    assert summary["failed"] == 1
    assert signal == before


def test_validation_queue_canonicalizes_supplied_aware_timestamps_to_utc() -> None:
    queue = ValidationQueue()
    plus_eight = timezone(timedelta(hours=8))
    local_timestamp = datetime(2026, 9, 10, 0, 30, tzinfo=plus_eight)

    item = queue.enqueue(
        signal_id="s-utc",
        signal_type="breakout",
        signal_state="confirmed",
        created_at=local_timestamp,
    )
    resolved = queue.resolve(
        item.validation_id,
        "passed",
        resolved_at=local_timestamp,
    )

    assert resolved.created_at == "2026-09-09T16:30:00+00:00"
    assert resolved.resolved_at == "2026-09-09T16:30:00+00:00"


def test_validation_queue_rejects_naive_explicit_timestamps() -> None:
    queue = ValidationQueue()
    naive = datetime(2026, 9, 10, 0, 30)

    with pytest.raises(ValueError, match="timezone-aware"):
        queue.enqueue(
            signal_id="s-naive",
            signal_type="breakout",
            signal_state="confirmed",
            created_at=naive,
        )

    item = queue.enqueue(
        signal_id="s-aware",
        signal_type="breakout",
        signal_state="confirmed",
    )
    with pytest.raises(ValueError, match="timezone-aware"):
        queue.resolve(item.validation_id, "passed", resolved_at=naive)


def test_validation_queue_rejects_falsy_non_datetime_timestamps() -> None:
    queue = ValidationQueue()
    for bad in (False, 0, ""):
        with pytest.raises(ValueError, match="must be a datetime"):
            queue.enqueue(
                signal_id=f"bad-{bad!r}",
                signal_type="breakout",
                signal_state="confirmed",
                created_at=bad,  # type: ignore[arg-type]
            )

    item = queue.enqueue(
        signal_id="s-aware",
        signal_type="breakout",
        signal_state="confirmed",
    )
    for bad in (False, 0, ""):
        with pytest.raises(ValueError, match="must be a datetime"):
            queue.resolve(item.validation_id, "passed", resolved_at=bad)  # type: ignore[arg-type]


def test_daily_qa_compares_legacy_offset_rows_by_instant_not_iso_text() -> None:
    queue = ValidationQueue()
    connection = queue._connection
    rows = (
        (
            "legacy-before",
            "legacy-before",
            "breakout",
            "confirmed",
            "passed",
            "{}",
            "2026-09-09T23:59:59+08:00",
            None,
        ),
        (
            "legacy-inside",
            "legacy-inside",
            "breakout",
            "confirmed",
            "passed",
            "{}",
            "2026-09-10T00:00:01+08:00",
            None,
        ),
        (
            "legacy-next-boundary",
            "legacy-next-boundary",
            "breakout",
            "confirmed",
            "passed",
            "{}",
            "2026-09-11T00:00:00+08:00",
            None,
        ),
    )
    connection.executemany(
        """
        INSERT INTO stock_radar_validation_queue
            (validation_id, signal_id, signal_type, signal_state, outcome,
             evidence_json, created_at, resolved_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )
    connection.commit()

    summary = DailyQA(queue).summarize(
        "breakout",
        day=date(2026, 9, 10),
        timezone_name="Asia/Shanghai",
    )

    assert summary["total"] == 1
    assert summary["passed"] == 1


def test_daily_qa_rejects_ambiguous_legacy_naive_timestamp() -> None:
    queue = ValidationQueue()
    queue._connection.execute(
        """
        INSERT INTO stock_radar_validation_queue
            (validation_id, signal_id, signal_type, signal_state, outcome,
             evidence_json, created_at, resolved_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "legacy-naive",
            "legacy-naive",
            "breakout",
            "confirmed",
            "passed",
            "{}",
            "2026-09-10T00:30:00",
            None,
        ),
    )
    queue._connection.commit()

    with pytest.raises(ValueError, match="ambiguous legacy timestamps"):
        DailyQA(queue).summarize(
            "breakout",
            day=date(2026, 9, 10),
            timezone_name="Asia/Shanghai",
        )


def test_daily_qa_rejects_unparseable_legacy_timestamp() -> None:
    queue = ValidationQueue()
    queue._connection.execute(
        """
        INSERT INTO stock_radar_validation_queue
            (validation_id, signal_id, signal_type, signal_state, outcome,
             evidence_json, created_at, resolved_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "legacy-bad",
            "legacy-bad",
            "breakout",
            "confirmed",
            "passed",
            "{}",
            "not-a-timestamp",
            None,
        ),
    )
    queue._connection.commit()

    with pytest.raises(ValueError, match="ambiguous legacy timestamps"):
        DailyQA(queue).summarize(
            "breakout",
            day=date(2026, 9, 10),
            timezone_name="Asia/Shanghai",
        )


def test_seven_failures_in_last_ten_trigger_qa_alert_and_review() -> None:
    queue = ValidationQueue()
    _resolved(queue, "breakout", ["failed"] * 7 + ["passed"] * 3)
    events = []
    weights = {"structure": 0.6, "volume": 0.4}
    before = deepcopy(weights)

    result = WeeklyCalibration(
        queue,
        notifier=RadarNotifier(events.append),
    ).evaluate("breakout", production_weights=weights)

    assert result["qa_alert"] is True
    assert result["calibration_review_id"]
    assert result["weight_change_eligible"] is False
    assert result["production_weights_changed"] is False
    assert weights == before
    assert [event.event_type for event in events] == ["signal_qa_alert"]


def test_six_failures_in_last_ten_do_not_trigger_alert() -> None:
    queue = ValidationQueue()
    _resolved(queue, "breakout", ["failed"] * 6 + ["passed"] * 4)
    events = []
    result = WeeklyCalibration(queue, notifier=RadarNotifier(events.append)).evaluate(
        "breakout",
        production_weights={"structure": 1.0},
    )
    assert result["qa_alert"] is False
    assert events == []


def test_thirty_samples_only_create_candidate_version_for_manual_promotion() -> None:
    queue = ValidationQueue()
    _resolved(queue, "reversal", ["passed"] * 20 + ["failed"] * 10)

    result = WeeklyCalibration(queue).evaluate(
        "reversal",
        production_weights={"structure": 0.5, "risk": 0.5},
    )

    assert result["weight_change_eligible"] is True
    assert result["candidate_version"].startswith("reversal-candidate-")
    assert result["requires_validation"] is True
    assert result["requires_manual_promotion"] is True
    assert result["production_weights_changed"] is False
