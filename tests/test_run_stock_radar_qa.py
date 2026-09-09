import json
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pytest

from scripts.run_stock_radar_qa import run
from src.services.stock_radar_v2.validation import ValidationQueue


def _resolved(
    database,
    signal_type: str,
    outcomes: list[str],
    *,
    created_at: datetime | None = None,
) -> None:
    queue = ValidationQueue(database)
    for index, outcome in enumerate(outcomes):
        item = queue.enqueue(
            signal_id=f"{signal_type}-{index}",
            signal_type=signal_type,
            signal_state="confirmed",
            created_at=created_at,
        )
        queue.resolve(item.validation_id, outcome, resolved_at=created_at)


def test_daily_run_uses_main_sqlite_and_writes_reports(tmp_path, monkeypatch) -> None:
    database = tmp_path / "stock_analysis.db"
    reports = tmp_path / "reports"
    monkeypatch.setenv("DATABASE_PATH", str(database))
    monkeypatch.setenv("STOCK_RADAR_QA_OUTPUT_DIR", str(reports))
    monkeypatch.setenv("STOCK_RADAR_TIMEZONE", "Asia/Shanghai")

    # Deterministically reproduce the old defect: 00:30 Shanghai belongs to
    # local Sep 10 but is still Sep 9 in UTC. ValidationQueue stores UTC ISO
    # timestamps, while DailyQA reports by the configured local calendar day.
    now = datetime(2026, 9, 10, 0, 30, tzinfo=ZoneInfo("Asia/Shanghai"))
    _resolved(
        database,
        "breakout",
        ["passed"],
        created_at=now.astimezone(timezone.utc),
    )

    result = run(
        "daily",
        now=now,
    )

    payload = json.loads((reports / "stock_radar_daily_qa.json").read_text("utf-8"))
    assert result["day"] == "2026-09-10"
    assert result["daily"][0]["signal_type"] == "breakout"
    assert payload["signal_types"][0]["total"] == 1
    assert payload["signal_types"][0]["passed"] == 1
    assert "不构成交易建议" in (reports / "stock_radar_daily_qa.md").read_text("utf-8")


def test_daily_run_normalizes_injected_utc_clock_before_selecting_local_day(tmp_path, monkeypatch) -> None:
    database = tmp_path / "stock_analysis.db"
    reports = tmp_path / "reports"
    monkeypatch.setenv("DATABASE_PATH", str(database))
    monkeypatch.setenv("STOCK_RADAR_QA_OUTPUT_DIR", str(reports))
    monkeypatch.setenv("STOCK_RADAR_TIMEZONE", "Asia/Shanghai")

    local_now = datetime(2026, 9, 10, 0, 30, tzinfo=ZoneInfo("Asia/Shanghai"))
    utc_now = local_now.astimezone(timezone.utc)
    _resolved(database, "breakout", ["passed"], created_at=utc_now)

    result = run("daily", now=utc_now)

    assert result["day"] == "2026-09-10"
    assert result["daily"][0]["total"] == 1


def test_daily_run_rejects_naive_injected_clock(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "stock_analysis.db"))
    monkeypatch.setenv("STOCK_RADAR_QA_OUTPUT_DIR", str(tmp_path / "reports"))
    monkeypatch.setenv("STOCK_RADAR_TIMEZONE", "Asia/Shanghai")

    with pytest.raises(ValueError, match="timezone-aware"):
        run("daily", now=datetime(2026, 9, 10, 0, 30))


def test_daily_run_uses_half_open_configured_local_day_boundaries(tmp_path, monkeypatch) -> None:
    database = tmp_path / "stock_analysis.db"
    reports = tmp_path / "reports"
    monkeypatch.setenv("DATABASE_PATH", str(database))
    monkeypatch.setenv("STOCK_RADAR_QA_OUTPUT_DIR", str(reports))
    monkeypatch.setenv("STOCK_RADAR_TIMEZONE", "Asia/Shanghai")
    zone = ZoneInfo("Asia/Shanghai")

    queue = ValidationQueue(database)
    local_times = (
        datetime(2026, 9, 9, 23, 59, 59, tzinfo=zone),   # previous local day
        datetime(2026, 9, 10, 0, 0, 1, tzinfo=zone),     # target local day
        datetime(2026, 9, 11, 0, 0, 0, tzinfo=zone),     # next local day boundary
    )
    for index, local_created_at in enumerate(local_times):
        utc_created_at = local_created_at.astimezone(timezone.utc)
        item = queue.enqueue(
            signal_id=f"breakout-boundary-{index}",
            signal_type="breakout",
            signal_state="confirmed",
            created_at=utc_created_at,
        )
        queue.resolve(item.validation_id, "passed", resolved_at=utc_created_at)

    result = run(
        "daily",
        now=datetime(2026, 9, 10, 12, 0, tzinfo=zone),
    )
    payload = json.loads((reports / "stock_radar_daily_qa.json").read_text("utf-8"))

    assert result["day"] == "2026-09-10"
    assert result["daily"][0]["total"] == 1
    assert payload["signal_types"][0]["total"] == 1


def test_weekly_run_creates_review_but_does_not_send_without_flag(tmp_path, monkeypatch) -> None:
    database = tmp_path / "stock_analysis.db"
    reports = tmp_path / "reports"
    monkeypatch.setenv("DATABASE_PATH", str(database))
    monkeypatch.setenv("STOCK_RADAR_QA_OUTPUT_DIR", str(reports))
    _resolved(database, "breakout", ["failed"] * 7 + ["passed"] * 3)
    dispatched = []

    result = run("weekly", send_alerts=False, notification_sink=dispatched.append)

    assert result["weekly"][0]["qa_alert"] is True
    assert len(result["events"]) == 1
    assert dispatched == []
    assert len(ValidationQueue(database).calibration_reviews()) == 1


def test_weekly_run_dispatches_qa_alert_only_when_enabled(tmp_path, monkeypatch) -> None:
    database = tmp_path / "stock_analysis.db"
    monkeypatch.setenv("DATABASE_PATH", str(database))
    monkeypatch.setenv("STOCK_RADAR_QA_OUTPUT_DIR", str(tmp_path / "reports"))
    _resolved(database, "reversal", ["failed"] * 7 + ["passed"] * 3)
    dispatched = []

    run("weekly", send_alerts=True, notification_sink=dispatched.append)

    assert [event.event_type for event in dispatched] == ["signal_qa_alert"]


def test_auto_runs_weekly_only_on_monday(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "stock_analysis.db"))
    monkeypatch.setenv("STOCK_RADAR_QA_OUTPUT_DIR", str(tmp_path / "reports"))

    monday = run("auto", now=datetime(2026, 8, 31, tzinfo=ZoneInfo("Asia/Shanghai")))
    tuesday = run("auto", now=datetime(2026, 9, 1, tzinfo=ZoneInfo("Asia/Shanghai")))

    assert "weekly" in monday
    assert "weekly" not in tuesday
