import json
from datetime import datetime
from zoneinfo import ZoneInfo

from scripts.run_stock_radar_qa import run
from src.services.stock_radar_v2.validation import ValidationQueue


def _resolved(database, signal_type: str, outcomes: list[str]) -> None:
    queue = ValidationQueue(database)
    for index, outcome in enumerate(outcomes):
        item = queue.enqueue(
            signal_id=f"{signal_type}-{index}",
            signal_type=signal_type,
            signal_state="confirmed",
        )
        queue.resolve(item.validation_id, outcome)


def test_daily_run_uses_main_sqlite_and_writes_reports(tmp_path, monkeypatch) -> None:
    database = tmp_path / "stock_analysis.db"
    reports = tmp_path / "reports"
    monkeypatch.setenv("DATABASE_PATH", str(database))
    monkeypatch.setenv("STOCK_RADAR_QA_OUTPUT_DIR", str(reports))
    _resolved(database, "breakout", ["passed"])
    now = datetime.now(ZoneInfo("Asia/Shanghai"))

    result = run(
        "daily",
        now=now,
    )

    payload = json.loads((reports / "stock_radar_daily_qa.json").read_text("utf-8"))
    assert result["daily"][0]["signal_type"] == "breakout"
    assert payload["signal_types"][0]["total"] == 1
    assert "不构成交易建议" in (reports / "stock_radar_daily_qa.md").read_text("utf-8")


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
