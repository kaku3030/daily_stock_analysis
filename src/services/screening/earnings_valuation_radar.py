# -*- coding: utf-8 -*-
"""Earnings and valuation research radar built from persisted candidate evidence."""

from __future__ import annotations

from typing import Any


def build_earnings_valuation_radar(
    candidates: list[dict[str, Any]],
    *,
    include_watching: bool = True,
) -> list[dict[str, Any]]:
    """Build a deterministic evidence table; never infer missing fundamentals."""

    allowed = {"active", "watching"} if include_watching else {"active"}
    rows: list[dict[str, Any]] = []
    for candidate in candidates:
        if str(candidate.get("status") or "active") not in allowed:
            continue
        snapshot = candidate.get("financial_snapshot")
        if not isinstance(snapshot, dict):
            snapshot = {}
        valuation = snapshot.get("valuation") if isinstance(snapshot.get("valuation"), dict) else {}
        earnings = snapshot.get("earnings") if isinstance(snapshot.get("earnings"), dict) else {}
        rows.append(
            {
                "code": str(candidate.get("code") or ""),
                "name": str(candidate.get("name") or ""),
                "grade": str(candidate.get("grade") or ""),
                "research_score": _number(candidate.get("score")),
                "status": str(candidate.get("status") or ""),
                "industry": str(candidate.get("industry") or ""),
                "data_mode": str(snapshot.get("mode") or "none"),
                "confidence": str(snapshot.get("confidence") or "none"),
                "pe_ratio": valuation.get("pe_ratio"),
                "pb_ratio": valuation.get("pb_ratio"),
                "forward_pe": valuation.get("forward_pe"),
                "peg_ratio": valuation.get("peg_ratio"),
                "price_to_sales": valuation.get("price_to_sales"),
                "fcf_yield": valuation.get("fcf_yield"),
                "earnings_date": earnings.get("earnings_date"),
                "revenue_growth": earnings.get("revenue_growth"),
                "eps_growth": earnings.get("eps_growth"),
                "net_income_growth": earnings.get("net_income_growth"),
                "gross_margin": earnings.get("gross_margin"),
                "operating_margin": earnings.get("operating_margin"),
                "free_cash_flow": earnings.get("free_cash_flow"),
                "guidance": earnings.get("guidance"),
                "financial_data_updated_at": candidate.get("financial_data_updated_at"),
            }
        )

    confidence_order = {"high": 0, "medium": 1, "low": 2, "none": 3}
    rows.sort(
        key=lambda row: (
            confidence_order.get(str(row["confidence"]), 9),
            -float(row["research_score"]),
            str(row["code"]),
        )
    )
    return rows


def earnings_valuation_radar_markdown(rows: list[dict[str, Any]]) -> str:
    lines = [
        "# 美股财报与估值雷达",
        "",
        "> 仅展示当前数据源实际提供的财报/估值证据；缺失字段保持为空，不做推断。增长率和利润率保留上游原始单位。",
        "",
        "| 股票 | 等级 | 研究分 | PE | Forward PE | PEG | 营收增长 | EPS增长 | 财报日期 | 指引 | 数据置信度 |",
        "|---|---|---:|---:|---:|---:|---|---|---|---|---|",
    ]
    if not rows:
        lines.append("| 暂无候选 | - | - | - | - | - | - | - | - | - | - |")
        return "\n".join(lines) + "\n"

    for row in rows:
        guidance = _escape(_display(row.get("guidance"), max_len=36))
        lines.append(
            f"| {row.get('code', '')} {row.get('name', '')} | {row.get('grade', '')} | "
            f"{float(row.get('research_score') or 0):.1f} | {_display(row.get('pe_ratio'))} | "
            f"{_display(row.get('forward_pe'))} | {_display(row.get('peg_ratio'))} | "
            f"{_display(row.get('revenue_growth'))} | {_display(row.get('eps_growth'))} | "
            f"{_display(row.get('earnings_date'))} | {guidance} | {row.get('confidence', 'none')} |"
        )
    return "\n".join(lines) + "\n"


def _display(value: Any, *, max_len: int = 24) -> str:
    if value is None or value == "":
        return "-"
    if isinstance(value, float):
        text = f"{value:.2f}"
    else:
        text = str(value)
    return text if len(text) <= max_len else text[: max_len - 1] + "…"


def _escape(value: str) -> str:
    return value.replace("|", "/").replace("\n", " ")


def _number(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0
