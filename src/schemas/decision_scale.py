# -*- coding: utf-8 -*-
"""Canonical score-to-decision scale shared by reports and DecisionSignal."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Optional


CANONICAL_DECISION_SCALE_VERSION = "decision-scale-v1"


@dataclass(frozen=True)
class DecisionScaleBand:
    min_score: int
    max_score: int
    signal_key: str
    action: str
    decision_type: str
    label_zh: str
    description_zh: str


CANONICAL_DECISION_SCALE: tuple[DecisionScaleBand, ...] = (
    DecisionScaleBand(80, 100, "strong_buy", "buy", "buy", "强烈买入", "高胜率机会，可执行买入/加仓计划"),
    DecisionScaleBand(60, 79, "buy", "buy", "buy", "买入", "偏积极机会，允许少量待确认项"),
    DecisionScaleBand(40, 59, "watch", "watch", "hold", "观望", "信号分歧或确认不足，等待触发条件"),
    DecisionScaleBand(20, 39, "reduce", "reduce", "sell", "减仓", "风险明显抬升，优先降低暴露"),
    DecisionScaleBand(0, 19, "sell", "sell", "sell", "卖出", "趋势或风险显著恶化，优先退出"),
)


CANONICAL_DECISION_SCALE_PROMPT_ZH = """## Canonical 评分与研究分级口径

- `sentiment_score` 表示“股票综合研究质量评分”，用于衡量该标的是否值得进入重点研究池，不代表短线买入强度。
- 80-100：A级，优先深入研究。
- 65-79：B级，值得持续观察。
- 50-64：C级，有一定亮点，但暂不优先。
- 0-49：D级，暂不进入重点观察池。

为兼容现有程序字段：
- `operation_advice` 固定输出“观望”。
- `decision_type` 固定输出 `hold`。
- `action` 固定输出 `watch`。
- 不允许根据 sentiment_score 自动映射为 buy/add/reduce/sell。
- 即使 sentiment_score >= 80，也不得因此输出买入、加仓、建仓、止损、止盈或仓位建议。
- `guardrail_reason` 可用于解释为何某只股票虽然研究评分较高，但仍仅作为研究候选，不产生交易动作。

评分应主要依据：
- 公司质量与护城河
- 营收、利润、EPS、自由现金流增长质量
- 最新财报与管理层指引
- 行业景气度
- 估值合理性
- 相对大盘及行业强弱
- 技术结构
- 最新新闻与催化剂

技术指标只能作为辅助项，不能因均线多头、MACD金叉、RSI等单一技术信号显著提高研究评分。
"""


def normalize_score(value: Any) -> Optional[int]:
    """Return a bounded integer score when possible."""

    try:
        score = int(float(value))
    except (TypeError, ValueError):
        return None
    if 0 <= score <= 100:
        return score
    return None


def decision_band_for_score(value: Any) -> Optional[DecisionScaleBand]:
    """Return the canonical decision band for a 0-100 score."""

    score = normalize_score(value)
    if score is None:
        return None
    for band in CANONICAL_DECISION_SCALE:
        if band.min_score <= score <= band.max_score:
            return band
    return None


def signal_key_for_score(value: Any) -> Optional[str]:
    band = decision_band_for_score(value)
    return band.signal_key if band else None


def action_for_score(value: Any) -> Optional[str]:
    band = decision_band_for_score(value)
    return band.action if band else None


def decision_type_for_score(value: Any) -> Optional[str]:
    band = decision_band_for_score(value)
    return band.decision_type if band else None


def score_band_metadata(value: Any) -> dict[str, Any]:
    """Return stable metadata for persistence and diagnostics."""

    score = normalize_score(value)
    band = decision_band_for_score(score)
    if score is None or band is None:
        return {}
    return {
        "scale_version": CANONICAL_DECISION_SCALE_VERSION,
        "score": score,
        "score_band": f"{band.min_score}-{band.max_score}",
        "signal_key": band.signal_key,
        "canonical_action": band.action,
        "canonical_decision_type": band.decision_type,
    }


def extract_decision_guardrail_reason(payload: Any) -> Optional[str]:
    """Extract an applied score/action guardrail reason from a result payload."""

    data = payload if isinstance(payload, Mapping) else {}
    dashboard = data.get("dashboard") if isinstance(data.get("dashboard"), Mapping) else {}
    calibration = (
        dashboard.get("decision_score_calibration")
        if isinstance(dashboard.get("decision_score_calibration"), Mapping)
        else {}
    )
    stability = (
        dashboard.get("decision_stability")
        if isinstance(dashboard.get("decision_stability"), Mapping)
        else {}
    )
    metadata = data.get("metadata") if isinstance(data.get("metadata"), Mapping) else {}

    stability_applied = stability.get("applied")
    include_stability_reason = stability_applied not in (False, 0, "0", "false", "False")
    candidates = [
        data.get("guardrail_reason"),
        data.get("downgrade_reason"),
        data.get("decision_score_guardrail_reason"),
        metadata.get("guardrail_reason"),
        metadata.get("downgrade_reason"),
        calibration.get("guardrail_reason"),
        calibration.get("downgrade_reason"),
    ]
    if include_stability_reason:
        candidates.extend(
            [
                stability.get("guardrail_reason"),
                stability.get("downgrade_reason"),
                stability.get("reason"),
            ]
        )

    for candidate in candidates:
        text = str(candidate or "").strip()
        if text:
            return text
    return None


def score_action_conflicts_without_guardrail(
    *,
    score: Any,
    action: Any,
    guardrail_reason: Any = None,
) -> bool:
    """Return True when a neutral action conflicts with a directional score."""

    if str(guardrail_reason or "").strip():
        return False
    normalized_action = str(action or "").strip().lower()
    if normalized_action not in {"hold", "watch"}:
        return False
    score_action = action_for_score(score)
    return score_action in {"buy", "reduce", "sell"}
