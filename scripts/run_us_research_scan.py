"""Run the fail-open daily US research candidate scan."""

import json
import logging
import os
import sys
from dataclasses import asdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.repositories.candidate_pool_repo import CandidatePoolRepository, candidate_to_dict
from src.repositories.financial_change_repo import (
    CandidateFinancialChangeRepository,
    financial_change_to_dict,
)
from src.repositories.research_priority_repo import ResearchPriorityEventRepository
from src.services.screening.config import Config
from src.services.screening.earnings_valuation_radar import (
    build_earnings_valuation_radar,
    earnings_valuation_radar_markdown,
)
from src.services.screening.financial_change_radar import (
    build_financial_change_radar,
    financial_change_radar_markdown,
)
from src.services.screening.industry_radar import build_industry_radar, industry_radar_markdown
from src.services.screening.pipeline import screen
from src.services.screening.research_priority import (
    build_research_priority_events,
    research_priority_markdown,
)
from src.services.screening.research_priority_notifications import dispatch_research_priority_alerts
from src.services.screening.research_priority_transition import (
    build_research_priority_alerts,
    research_priority_alerts_markdown,
)

logger = logging.getLogger(__name__)
RESEARCH_ALERT_FLAG = "--send-research-alerts"
RESEARCH_ALERT_MAX_PER_RUN = 5


def _enabled(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _research_alert_dispatch_enabled() -> bool:
    return RESEARCH_ALERT_FLAG in sys.argv[1:]


def _markdown(payload: dict) -> str:
    lines = [
        "# 美股每日研究候选",
        "",
        "> 用于确定进一步研究优先级，不构成交易建议。",
        "",
        f"- 策略：{payload.get('strategy', 'us_research_priority')}",
        f"- 初始股票数：{payload.get('snapshot_count', 0)}",
        f"- 筛选后数量：{payload.get('after_filter_count', 0)}",
        "",
        "| 排名 | 股票 | 研究分 | 行业 | 核心理由 | 主要风险 |",
        "|---:|---|---:|---|---|---|",
    ]
    for pick in payload.get("picks", []):
        reason = str(pick.get("ranking_reason") or pick.get("llm_thesis") or "待进一步研究").replace("|", "/")
        risk = str(pick.get("risk_summary") or "未识别重大风险").replace("|", "/")
        lines.append(
            f"| {pick.get('rank', '')} | {pick.get('code', '')} {pick.get('name', '')} | "
            f"{float(pick.get('final_score') or 0):.1f} | {pick.get('industry', '')} | {reason} | {risk} |"
        )
    degradations = payload.get("degradation") or []
    if degradations:
        lines.extend(["", "## 数据限制", "", *[f"- {item}" for item in degradations]])
    return "\n".join(lines) + "\n"


def _candidate_pool_markdown(candidates: list[dict]) -> str:
    lines = [
        "# 美股长期研究候选池",
        "",
        "> 等级反映最近一次研究评分；状态反映最近多次健康扫描中的持续入选情况。",
        "> active=持续关注，watching=连续2次未入选，retired=连续5次未入选。重新入选会自动恢复 active。",
        "",
    ]
    labels = {"active": "持续关注", "watching": "观察降温", "retired": "暂时退出"}
    for status in ("active", "watching", "retired"):
        rows = [row for row in candidates if row.get("status") == status]
        if not rows:
            continue
        lines.extend([
            f"## {labels[status]}",
            "",
            "| 等级 | 股票 | 研究分 | 优先级 | 行业 | 入选次数 | 连续未入选 | 最近入选 | 核心理由 | 主要风险 |",
            "|---|---|---:|---|---|---:|---:|---|---|---|",
        ])
        for row in rows:
            reason = str(row.get("ranking_reason") or "待进一步研究").replace("|", "/")
            risk = str(row.get("risk_summary") or "未识别重大风险").replace("|", "/")
            last_selected = str(row.get("last_selected_at") or "")[:10]
            priority = row.get("research_priority") or {}
            lines.append(
                f"| {row.get('grade', '')} | {row.get('code', '')} {row.get('name', '')} | "
                f"{float(row.get('score') or 0):.1f} | {priority.get('priority_level', '-')} | "
                f"{row.get('industry', '')} | {int(row.get('selected_count') or 0)} | "
                f"{int(row.get('missed_runs') or 0)} | {last_selected} | {reason} | {risk} |"
            )
        lines.append("")
    if len(lines) == 5:
        lines.append("当前候选池为空。")
    return "\n".join(lines).rstrip() + "\n"


def _write_json_markdown(output_dir: Path, stem: str, payload: object, markdown: str) -> None:
    (output_dir / f"{stem}.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    (output_dir / f"{stem}.md").write_text(markdown, encoding="utf-8")


def _write_notification_diagnostics(
    output_dir: Path,
    *,
    enabled: bool,
    eligible_alerts: int,
    attempts: list[dict],
) -> None:
    payload = {
        "enabled": enabled,
        "eligible_alerts": eligible_alerts,
        "attempted": len(attempts),
        "successful": sum(bool(item.get("success")) for item in attempts),
        "attempts": attempts,
    }
    (output_dir / "us_research_priority_notifications.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )


def _sync_candidate_pool(payload: dict, output_dir: Path) -> None:
    try:
        market = str(payload.get("market") or "us").strip().lower()
        run_id = str(payload.get("run_id") or "")
        repo = CandidatePoolRepository()
        stats = repo.sync_from_screen_result(payload)

        change_repo = CandidateFinancialChangeRepository(repo.db)
        change_count = change_repo.sync_run(market, run_id)
        latest_changes = {
            row.code: financial_change_to_dict(row)
            for row in change_repo.list_latest(market)
        }

        candidates = [
            candidate_to_dict(record)
            for record in repo.list_candidates(market=market, include_retired=True)
        ]
        for candidate in candidates:
            candidate["financial_change"] = latest_changes.get(str(candidate.get("code") or ""), {})

        industry_radar = build_industry_radar(candidates)
        priority_events = build_research_priority_events(candidates, industry_radar)
        priority_repo = ResearchPriorityEventRepository(repo.db)
        previous_priority_events = priority_repo.latest_payload_map(market, exclude_run_id=run_id)
        priority_alerts = build_research_priority_alerts(priority_events, previous_priority_events)
        priority_event_count = priority_repo.sync_run(market, run_id, priority_events)

        alerts_enabled = _research_alert_dispatch_enabled()
        notification_results: list[dict] = []
        if alerts_enabled and priority_alerts and priority_event_count > 0:
            notification_results = dispatch_research_priority_alerts(
                priority_alerts,
                market=market,
                run_id=run_id,
                max_alerts=RESEARCH_ALERT_MAX_PER_RUN,
            )
        _write_notification_diagnostics(
            output_dir,
            enabled=alerts_enabled,
            eligible_alerts=len(priority_alerts),
            attempts=notification_results,
        )

        priority_map = {str(event.get("code") or ""): event for event in priority_events}
        alert_map = {str(alert.get("code") or ""): alert for alert in priority_alerts}
        for candidate in candidates:
            code = str(candidate.get("code") or "")
            candidate["research_priority"] = priority_map.get(code, {})
            candidate["research_alert"] = alert_map.get(code, {})

        _write_json_markdown(output_dir, "us_research_candidate_pool", candidates, _candidate_pool_markdown(candidates))
        _write_json_markdown(output_dir, "us_research_industry_radar", industry_radar, industry_radar_markdown(industry_radar))

        earnings_radar = build_earnings_valuation_radar(candidates)
        _write_json_markdown(
            output_dir,
            "us_research_earnings_valuation_radar",
            earnings_radar,
            earnings_valuation_radar_markdown(earnings_radar),
        )

        financial_radar = build_financial_change_radar(candidates)
        _write_json_markdown(
            output_dir,
            "us_research_financial_changes",
            financial_radar,
            financial_change_radar_markdown(financial_radar),
        )
        _write_json_markdown(
            output_dir,
            "us_research_priority_events",
            priority_events,
            research_priority_markdown(priority_events),
        )
        _write_json_markdown(
            output_dir,
            "us_research_priority_alerts",
            priority_alerts,
            research_priority_alerts_markdown(priority_alerts),
        )

        logger.info(
            "Candidate pool synced: inserted=%d updated=%d aged=%d watching=%d retired=%d "
            "reactivated=%d financial_snapshots=%d financial_changes=%d priority_events=%d "
            "priority_alerts=%d notification_attempts=%d",
            stats.inserted,
            stats.updated,
            stats.aged,
            stats.watching,
            stats.retired,
            stats.reactivated,
            stats.financial_snapshots,
            change_count,
            priority_event_count,
            len(priority_alerts),
            len(notification_results),
        )
    except Exception:
        logger.exception("Candidate pool sync failed; daily research report remains available")


def main() -> int:
    if not _enabled("US_RESEARCH_SCAN_ENABLED"):
        logger.info("US research scan disabled")
        return 0
    output_dir = Path(os.getenv("US_RESEARCH_SCAN_OUTPUT_DIR", "reports/screening"))
    output_dir.mkdir(parents=True, exist_ok=True)
    config = Config.from_env()
    result = screen(
        os.getenv("US_RESEARCH_STRATEGY", "us_research_priority"),
        market="us",
        max_output=max(1, int(os.getenv("US_RESEARCH_MAX_RESULTS", "10"))),
        use_llm=_enabled("US_RESEARCH_LLM_ENABLED", True),
        daily_enrich=True,
        daily_enrich_max_candidates=max(20, int(os.getenv("US_RESEARCH_DAILY_CANDIDATES", "40"))),
        collect_llm_candidate_context=True,
        candidate_context_max_candidates=max(5, int(os.getenv("US_RESEARCH_CONTEXT_CANDIDATES", "20"))),
        post_analyzers=["scorecard"],
        config=config,
    )
    payload = asdict(result)
    (output_dir / "us_research_candidates.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    (output_dir / "us_research_candidates.md").write_text(_markdown(payload), encoding="utf-8")
    _sync_candidate_pool(payload, output_dir)
    logger.info("US research scan completed with %d candidates", len(payload.get("picks", [])))
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
    raise SystemExit(main())
