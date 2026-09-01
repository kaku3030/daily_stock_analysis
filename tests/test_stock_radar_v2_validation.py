from copy import deepcopy
from datetime import datetime, timezone

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
