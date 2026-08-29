# -*- coding: utf-8 -*-
"""
Shared defaults for trading skills.

This module centralises:
1. The default active skill set used by agent entrypoints
2. The fallback skill subset used by the multi-agent router
3. Common prompt fragments that previously drifted across multiple files
4. Helper utilities for skill-specific agent naming
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Dict, Iterable, List, Optional


_BUILTIN_SKILLS_DIR = Path(__file__).resolve().parent.parent.parent.parent / "strategies"

SKILL_AGENT_PREFIX = "skill_"
LEGACY_STRATEGY_AGENT_PREFIX = "strategy_"
SKILL_CONSENSUS_AGENT_NAME = "skill_consensus"
LEGACY_STRATEGY_CONSENSUS_AGENT_NAME = "strategy_consensus"

CORE_TRADING_SKILL_POLICY_ZH = """## 默认研究筛选基线（必须严格遵守）

当前激活的 skills 可以补充细化分析视角，但所有分析应以“优质股票筛选与研究优先级判断”为核心，不直接生成交易执行建议。

### 1. 公司质量优先

- 优先评估公司的行业地位、竞争优势、护城河与商业模式质量
- 关注盈利能力、自由现金流、ROE/ROIC、毛利率及其变化趋势
- 不得因为短期股价上涨或技术形态强势，就提高公司质量评分
- 公司质量明显不足时，即使技术面强，也不得列为A级候选

### 2. 增长质量

- 重点关注营收、净利润、EPS、自由现金流的同比与环比趋势
- 判断增长是否加速、稳定或明显放缓
- 优先关注增长具有持续性且利润质量同步改善的公司
- 若营收增长但利润率、现金流明显恶化，应降低评分

### 3. 最新财报与管理层指引

- 必须优先使用最新可确认财报
- 应尽可能明确最新财报日期和报告期
- 重点分析营收、EPS、利润率、现金流、核心业务分部和管理层指引
- 若无法确认最新财报，必须标记“财报数据待核实”
- 不得把旧财报描述为最新财报
- 管理层下调指引、增长放缓或利润率恶化属于重要负面因素

### 4. 行业景气与竞争格局

- 判断所属行业未来1-3年的景气趋势
- 关注需求增长、资本开支、库存周期、供需格局及竞争变化
- 优先选择处于上升周期且具备行业领先地位的公司
- 行业景气下行时，应降低候选优先级

### 5. 估值合理性

- 结合 Forward PE、PEG、PS、自由现金流估值及历史估值区间进行综合判断
- 不以单一PE高低判断公司贵或便宜
- 高估值公司必须说明未来增长是否足以消化当前估值
- 若估值明显透支增长预期，应降低研究评分

### 6. 相对强度

- 比较个股相对于所属行业、QQQ/SPY或对应市场指数的表现
- 持续跑赢行业和大盘可作为正面辅助信号
- 相对强度只能作为辅助，不得取代公司基本面分析

### 7. 技术结构仅作辅助

- MA5、MA10、MA20、MACD、RSI、成交量等只用于判断趋势质量和市场确认度
- 不要求必须满足 MA5 > MA10 > MA20 才能进入候选池
- 不得因单一均线多头排列、MACD金叉或RSI强势显著提高研究评分
- 股价乖离较大时可以标记短期追高风险，但不得因此否定公司的长期研究价值
- 技术面用于辅助判断“当前市场是否认可基本面逻辑”，而不是生成买点

### 8. 新闻与催化剂

- 优先使用有明确日期和来源的最新新闻
- 区分已发生事实、管理层表态、市场传闻和模型推断
- 关注产品发布、订单、资本开支、监管变化、并购、行业政策和重大合作
- 新闻数据不足时应明确写“当前新闻数据不足”，不得写“近期无重大新闻”

### 9. 风险排查重点

重点检查：
- 最新财报不及预期
- 管理层下调指引
- 毛利率或自由现金流恶化
- 估值明显透支增长
- 行业景气反转
- 重大减持或内部人异常卖出
- 监管处罚、诉讼、产品安全问题
- 重大客户依赖或供应链风险

### 10. 禁止生成交易执行建议

本系统用于选股筛选和研究优先级排序，不用于自动交易。

因此：
- 不提供具体买入价
- 不提供加仓价
- 不提供止损价
- 不提供止盈目标
- 不提供真实仓位比例
- 不输出“轻仓试探”“回踩买入”“无条件减仓”等交易执行指令
- 若现有JSON字段要求这些内容，统一填写“N/A”或“仅用于选股研究”

最终目标是回答：
“这是不是一家值得进一步研究的优质公司？”
而不是回答：
“现在应该怎么买卖这只股票？”
"""

TECHNICAL_SKILL_RULES_EN = """## Default Skill Baseline

Treat the currently activated skills as the primary analysis lens, but keep the
following default risk controls as the shared baseline:

- Bullish alignment: MA5 > MA10 > MA20
- Bias from MA5 < 2% -> ideal buy zone; 2-5% -> small position; > 5% -> no chase
- Shrink-pullback to MA5 is the preferred entry rhythm
- Below MA20 -> hold off unless the active skill explicitly proves a better setup
"""


def get_default_trading_skill_policy(*, explicit_skill_selection: bool) -> str:
    """Return the legacy default trading baseline only for implicit/default runs.

    When a caller explicitly chooses a skill (via request payload or config),
    analysis should follow that selected skill alone instead of silently
    layering the old bull-trend baseline on top.
    """
    if explicit_skill_selection:
        return ""
    return CORE_TRADING_SKILL_POLICY_ZH


def get_default_technical_skill_policy(*, explicit_skill_selection: bool) -> str:
    """Return the technical-agent baseline only for implicit/default runs."""
    if explicit_skill_selection:
        return ""
    return TECHNICAL_SKILL_RULES_EN


@lru_cache(maxsize=1)
def _load_builtin_skill_catalog() -> tuple[object, ...]:
    try:
        from src.agent.skills.base import load_skills_from_directory

        return tuple(load_skills_from_directory(_BUILTIN_SKILLS_DIR))
    except Exception:
        return ()


def _coerce_priority(value: object, default: int = 100) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _normalize_available_ids(available_skill_ids: Optional[Iterable[str]]) -> List[str]:
    normalized: List[str] = []
    if available_skill_ids is None:
        return normalized
    for skill_id in available_skill_ids:
        if isinstance(skill_id, str):
            cleaned = skill_id.strip()
            if cleaned and cleaned not in normalized:
                normalized.append(cleaned)
    return normalized


def _normalize_skill_inputs(
    skills: Optional[Iterable[object]],
    available_skill_ids: Optional[Iterable[str]] = None,
) -> tuple[List[object], List[str]]:
    normalized_available = _normalize_available_ids(available_skill_ids)

    if skills is None:
        return list(_load_builtin_skill_catalog()), normalized_available

    skill_pool: List[object] = []
    for item in skills:
        if isinstance(item, str):
            cleaned = item.strip()
            if cleaned and cleaned not in normalized_available:
                normalized_available.append(cleaned)
            continue
        if item is not None:
            skill_pool.append(item)
    return skill_pool, normalized_available


def _sort_skill_pool(skills: Iterable[object]) -> List[object]:
    return sorted(
        skills,
        key=lambda skill: (
            _coerce_priority(getattr(skill, "default_priority", 100)),
            str(getattr(skill, "display_name", "") or getattr(skill, "name", "")),
            str(getattr(skill, "name", "")),
        ),
    )


def _iter_candidate_skills(
    skills: Optional[Iterable[object]],
    *,
    available_skill_ids: Optional[Iterable[str]] = None,
    user_invocable_only: bool = True,
) -> tuple[List[object], List[str]]:
    skill_pool, normalized_available = _normalize_skill_inputs(skills, available_skill_ids)
    available_lookup = set(normalized_available)

    candidates: List[object] = []
    for skill in _sort_skill_pool(skill_pool):
        skill_id = str(getattr(skill, "name", "")).strip()
        if not skill_id:
            continue
        if user_invocable_only and not bool(getattr(skill, "user_invocable", True)):
            continue
        if available_lookup and skill_id not in available_lookup:
            continue
        candidates.append(skill)

    return candidates, normalized_available


def _slice_skill_ids(skill_ids: List[str], max_count: Optional[int]) -> List[str]:
    if max_count is None:
        return skill_ids
    return skill_ids[:max_count]


def _pick_primary_default_skill_id(candidates: List[object]) -> str:
    preferred = [
        str(getattr(skill, "name", "")).strip()
        for skill in candidates
        if bool(getattr(skill, "default_active", False))
    ]
    if preferred:
        return preferred[0]

    fallback = [str(getattr(skill, "name", "")).strip() for skill in candidates]
    if fallback:
        return fallback[0]

    return ""


def get_default_active_skill_ids(
    skills: Optional[Iterable[object]] = None,
    max_count: Optional[int] = None,
    available_skill_ids: Optional[Iterable[str]] = None,
) -> List[str]:
    candidates, normalized_available = _iter_candidate_skills(
        skills,
        available_skill_ids=available_skill_ids,
    )
    default_skill_id = _pick_primary_default_skill_id(candidates)
    if default_skill_id:
        return _slice_skill_ids([default_skill_id], max_count)

    return _slice_skill_ids(normalized_available[:1], max_count)


def get_default_router_skill_ids(
    skills: Optional[Iterable[object]] = None,
    max_count: Optional[int] = None,
    available_skill_ids: Optional[Iterable[str]] = None,
) -> List[str]:
    candidates, normalized_available = _iter_candidate_skills(
        skills,
        available_skill_ids=available_skill_ids,
    )
    preferred = [
        str(getattr(skill, "name", "")).strip()
        for skill in candidates
        if bool(getattr(skill, "default_router", False))
    ]
    if preferred:
        return _slice_skill_ids(preferred, max_count)

    return get_default_active_skill_ids(
        candidates,
        max_count=max_count,
        available_skill_ids=normalized_available,
    )


def get_regime_skill_ids(
    regime: str,
    skills: Optional[Iterable[object]] = None,
    max_count: Optional[int] = None,
    available_skill_ids: Optional[Iterable[str]] = None,
) -> List[str]:
    candidates, normalized_available = _iter_candidate_skills(
        skills,
        available_skill_ids=available_skill_ids,
    )
    regime_name = (regime or "").strip().lower()
    if regime_name:
        matched = []
        for skill in candidates:
            market_regimes = getattr(skill, "market_regimes", None) or []
            normalized_regimes = {
                str(item).strip().lower()
                for item in market_regimes
                if str(item).strip()
            }
            if regime_name in normalized_regimes:
                matched.append(str(getattr(skill, "name", "")).strip())
        if matched:
            return _slice_skill_ids(matched, max_count)

    return get_default_router_skill_ids(
        candidates,
        max_count=max_count,
        available_skill_ids=normalized_available,
    )


def get_primary_default_skill_id(
    skills: Optional[Iterable[object]] = None,
    available_skill_ids: Optional[Iterable[str]] = None,
) -> str:
    defaults = get_default_active_skill_ids(skills, max_count=1, available_skill_ids=available_skill_ids)
    return defaults[0] if defaults else ""


def _build_regime_skill_ids(skills: Iterable[object]) -> Dict[str, List[str]]:
    regime_map: Dict[str, List[str]] = {}
    for skill in _sort_skill_pool(skills):
        skill_id = str(getattr(skill, "name", "")).strip()
        if not skill_id:
            continue
        for regime in getattr(skill, "market_regimes", None) or []:
            regime_name = str(regime).strip().lower()
            if not regime_name:
                continue
            regime_map.setdefault(regime_name, []).append(skill_id)
    return regime_map


DEFAULT_ACTIVE_SKILL_IDS: tuple[str, ...] = tuple(get_default_active_skill_ids())
DEFAULT_ROUTER_SKILL_IDS: tuple[str, ...] = tuple(get_default_router_skill_ids())
PRIMARY_DEFAULT_SKILL_ID = get_primary_default_skill_id()
REGIME_SKILL_IDS: Dict[str, List[str]] = _build_regime_skill_ids(_load_builtin_skill_catalog())


def build_skill_agent_name(skill_id: str) -> str:
    return f"{SKILL_AGENT_PREFIX}{skill_id}"


def extract_skill_id(agent_name: Optional[str]) -> Optional[str]:
    if not agent_name or not isinstance(agent_name, str):
        return None
    for prefix in (SKILL_AGENT_PREFIX, LEGACY_STRATEGY_AGENT_PREFIX):
        if agent_name.startswith(prefix):
            return agent_name[len(prefix):]
    return None


def is_skill_agent_name(agent_name: Optional[str]) -> bool:
    return extract_skill_id(agent_name) is not None


def is_skill_consensus_name(agent_name: Optional[str]) -> bool:
    return agent_name in {SKILL_CONSENSUS_AGENT_NAME, LEGACY_STRATEGY_CONSENSUS_AGENT_NAME}
