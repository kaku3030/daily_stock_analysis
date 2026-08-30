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

from src.repositories.candidate_pool_repo import (
    CandidatePoolRepository,
    candidate_to_dict,
)
from src.services.screening.config import Config
from src.services.screening.earnings_valuation_radar import (
    build_earnings_valuation_radar,
    earnings_valuation_radar_markdown,
)
from src.services.screening.industry_radar import (
    build_industry_radar,
    industry_radar_markdown,
)
from src.services.screening.pipeline import screen

logger = logging.getLogger(__name__)


def _enabled(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


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
        reason = str(
            pick.get("ranking_reason") or pick.get("llm_thesis") or "待进一步研究"
        ).replace("|", "/")
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
    labels = {
        "active": "持续关注",
        "watching": "观察降温",
        "retired": "暂时退出",
    }
    for status in ("active", "watching", "retired"):
        rows = [row for row in candidates if row.get("status") == status]
        if not rows:
            continue
        lines.extend(
            [
                f"## {labels[status]}",
                "",
                "| 等级 | 股票 | 研究分 | 行业 | 入选次数 | 连续未入选 | 最近入选 | 核心理由 | 主要风险 |",
                "|---|---|---:|---|---:|---:|---|---|---|",
            ]
        )
        for row in rows:
            reason = str(row.get("ranking_reason") or "待进一步研究").replace("|", "/")
            risk = str(row.get("risk_summary") or "未识别重大风险").replace("|", "/")
            last_selected = str(row.get("last_selected_at") or "")[:10]
            lines.append(
                f"| {row.get('grade', '')} | {row.get('code', '')} {row.get('name', '')} | "
                f"{float(row.get('score') or 0):.1f} | {row.get('industry', '')} | "
                f"{int(row.get('selected_count') or 0)} | {int(row.get('missed_runs') or 0)} | "
                f"{last_selected} | {reason} | {risk} |"
            )
        lines.append("")
    if len(lines) == 5:
        lines.append("当前候选池为空。")
    return "\n".join(lines).rstrip() + "\n"


def _write_industry_radar(candidates: list[dict], output_dir: Path) -> None:
    radar = build_industry_radar(candidates)
    (output_dir / "us_research_industry_radar.json").write_text(
        json.dumps(radar, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    (output_dir / "us_research_industry_radar.md").write_text(
        industry_radar_markdown(radar),
        encoding="utf-8",
    )


def _write_earnings_valuation_radar(
    candidates: list[dict],
    output_dir: Path,
) -> None:
    radar = build_earnings_valuation_radar(candidates)
    (output_dir / "us_research_earnings_valuation_radar.json").write_text(
        json.dumps(radar, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    (output_dir / "us_research_earnings_valuation_radar.md").write_text(
        earnings_valuation_radar_markdown(radar),
        encoding="utf-8",
    )


def _sync_candidate_pool(payload: dict, output_dir: Path) -> None:
    """Persist picks and emit long-lived research radar snapshots."""

    try:
        repo = CandidatePoolRepository()
        stats = repo.sync_from_screen_result(payload)
        candidates = [
            candidate_to_dict(record)
            for record in repo.list_candidates(market="us", include_retired=True)
        ]
        (output_dir / "us_research_candidate_pool.json").write_text(
            json.dumps(candidates, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        (output_dir / "us_research_candidate_pool.md").write_text(
            _candidate_pool_markdown(candidates),
            encoding="utf-8",
        )
        _write_industry_radar(candidates, output_dir)
        _write_earnings_valuation_radar(candidates, output_dir)
        logger.info(
            "Candidate pool synced: inserted=%d updated=%d aged=%d watching=%d "
            "retired=%d reactivated=%d financial_snapshots=%d",
            stats.inserted,
            stats.updated,
            stats.aged,
            stats.watching,
            stats.retired,
            stats.reactivated,
            stats.financial_snapshots,
        )
    except Exception:
        logger.exception(
            "Candidate pool sync failed; daily research report remains available"
        )


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
        daily_enrich_max_candidates=max(
            20,
            int(os.getenv("US_RESEARCH_DAILY_CANDIDATES", "40")),
        ),
        collect_llm_candidate_context=True,
        candidate_context_max_candidates=max(
            5,
            int(os.getenv("US_RESEARCH_CONTEXT_CANDIDATES", "20")),
        ),
        post_analyzers=["scorecard"],
        config=config,
    )
    payload = asdict(result)
    (output_dir / "us_research_candidates.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    (output_dir / "us_research_candidates.md").write_text(
        _markdown(payload),
        encoding="utf-8",
    )
    _sync_candidate_pool(payload, output_dir)
    logger.info(
        "US research scan completed with %d candidates",
        len(payload.get("picks", [])),
    )
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
    raise SystemExit(main())
