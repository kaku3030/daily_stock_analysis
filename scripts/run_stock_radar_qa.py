"""Run Stock Radar V2 QA against the stateful research database."""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping
from zoneinfo import ZoneInfo

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.services.stock_radar_v2.notifications import RadarNotification, RadarNotifier
from src.services.stock_radar_v2.runtime_notifications import NotificationServiceRadarSink
from src.services.stock_radar_v2.validation import DailyQA, ValidationQueue, WeeklyCalibration

logger = logging.getLogger(__name__)


def _production_weights() -> Mapping[str, Any]:
    raw = os.getenv("STOCK_RADAR_PRODUCTION_WEIGHTS_JSON", "").strip()
    if not raw:
        return {}
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError("STOCK_RADAR_PRODUCTION_WEIGHTS_JSON must be a JSON object")
    return value


def _weights_for(signal_type: str, weights: Mapping[str, Any]) -> Mapping[str, float]:
    scoped = weights.get(signal_type)
    selected = scoped if isinstance(scoped, dict) else weights
    return {
        str(key): float(value)
        for key, value in selected.items()
        if isinstance(value, (int, float))
    }


def _write_report(path: Path, payload: Any, markdown: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.with_suffix(".json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    path.with_suffix(".md").write_text(markdown, encoding="utf-8")


def _daily_markdown(rows: list[dict[str, Any]], day: str) -> str:
    lines = [
        "# Stock Radar V2 Daily QA",
        "",
        "> 研究质量记录，不构成交易建议或交易指令。",
        "",
        f"- 日期：{day}",
        "",
        "| 信号类型 | 总数 | 待验证 | 通过 | 失败 |",
        "|---|---:|---:|---:|---:|",
    ]
    for row in rows:
        lines.append(
            f"| {row['signal_type']} | {row['total']} | {row['pending']} | "
            f"{row['passed']} | {row['failed']} |"
        )
    if not rows:
        lines.extend(["", "本日尚无明确 Confirmed 信号进入 Validation Queue。"])
    return "\n".join(lines) + "\n"


def _weekly_markdown(rows: list[dict[str, Any]], day: str) -> str:
    lines = [
        "# Stock Radar V2 Weekly Calibration",
        "",
        "> 仅生成质量复核候选；不会自动修改生产权重，也不构成交易建议。",
        "",
        f"- 日期：{day}",
        "",
        "| 信号类型 | 已验证样本 | 最近窗口 | 失败数 | QA 告警 | 人工晋级 |",
        "|---|---:|---:|---:|---|---|",
    ]
    for row in rows:
        lines.append(
            f"| {row['signal_type']} | {row['sample_count']} | {row['recent_window']} | "
            f"{row['recent_failures']} | {'是' if row['qa_alert'] else '否'} | "
            f"{'必须' if row['requires_manual_promotion'] else '不适用'} |"
        )
    if not rows:
        lines.extend(["", "当前没有可校准的 Confirmed 信号样本。"])
    return "\n".join(lines) + "\n"


def run(
    action: str,
    *,
    send_alerts: bool = False,
    now: datetime | None = None,
    notification_sink: Any | None = None,
) -> dict[str, Any]:
    timezone_name = os.getenv("STOCK_RADAR_TIMEZONE", "Asia/Shanghai")
    current = now or datetime.now(ZoneInfo(timezone_name))
    database = Path(os.getenv("DATABASE_PATH", "data/stock_analysis.db"))
    output_dir = Path(os.getenv("STOCK_RADAR_QA_OUTPUT_DIR", "reports/screening"))
    database.parent.mkdir(parents=True, exist_ok=True)

    queue = ValidationQueue(database)
    signal_types = queue.signal_types()
    events: list[RadarNotification] = []
    external_sink = notification_sink
    if send_alerts and external_sink is None:
        try:
            external_sink = NotificationServiceRadarSink()
        except Exception as exc:
            logger.warning("Stock Radar notification service unavailable: %s", exc)

    def collect(event: RadarNotification) -> None:
        events.append(event)
        if send_alerts and external_sink is not None:
            external_sink(event)

    notifier = RadarNotifier(collect)
    result: dict[str, Any] = {"day": current.date().isoformat(), "events": events}
    run_daily = action in {"daily", "auto"}
    run_weekly = action == "weekly" or (action == "auto" and current.weekday() == 0)

    if run_daily:
        daily_rows = [
            DailyQA(queue).summarize(signal_type, day=current.date())
            for signal_type in signal_types
        ]
        result["daily"] = daily_rows
        _write_report(
            output_dir / "stock_radar_daily_qa",
            {"day": result["day"], "signal_types": daily_rows},
            _daily_markdown(daily_rows, result["day"]),
        )

    if run_weekly:
        weights = _production_weights()
        weekly_rows = [
            WeeklyCalibration(queue, notifier=notifier).evaluate(
                signal_type,
                production_weights=_weights_for(signal_type, weights),
            )
            for signal_type in signal_types
        ]
        result["weekly"] = weekly_rows
        _write_report(
            output_dir / "stock_radar_weekly_calibration",
            {"day": result["day"], "signal_types": weekly_rows},
            _weekly_markdown(weekly_rows, result["day"]),
        )

    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--action", choices=("daily", "weekly", "auto"), default="auto")
    parser.add_argument("--send-alerts", action="store_true")
    args = parser.parse_args(argv)
    result = run(args.action, send_alerts=args.send_alerts)
    print(
        "Stock Radar QA complete: "
        f"daily={len(result.get('daily', []))}, "
        f"weekly={len(result.get('weekly', []))}, "
        f"alerts={len(result['events'])}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
