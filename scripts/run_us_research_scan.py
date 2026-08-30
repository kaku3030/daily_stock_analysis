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

from src.services.screening.config import Config
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
    logger.info("US research scan completed with %d candidates", len(payload.get("picks", [])))
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
    raise SystemExit(main())
