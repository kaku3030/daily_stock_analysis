# -*- coding: utf-8 -*-
"""Normalize best-effort earnings and valuation evidence for research candidates."""

from __future__ import annotations

from typing import Any

EARNINGS_ALIASES: dict[str, tuple[str, ...]] = {
    "earnings_date": ("earnings_date", "latest_earnings_date", "report_date", "fiscal_date"),
    "revenue_growth": ("revenue_growth", "revenue_growth_yoy", "revenueGrowth", "revenue_yoy", "sales_growth"),
    "eps_growth": ("eps_growth", "eps_growth_yoy", "earnings_growth", "earningsGrowth"),
    "net_income_growth": ("net_income_growth", "net_income_growth_yoy", "profit_growth", "netIncomeGrowth"),
    "gross_margin": ("gross_margin", "gross_margin_pct", "grossMargins"),
    "operating_margin": ("operating_margin", "operating_margin_pct", "operatingMargins"),
    "free_cash_flow": ("free_cash_flow", "freeCashflow", "fcf"),
    "guidance": ("guidance", "management_guidance", "outlook", "company_outlook"),
}

VALUATION_ALIASES: dict[str, tuple[str, ...]] = {
    "forward_pe": ("forward_pe", "forwardPE", "forward_pe_ratio"),
    "peg_ratio": ("peg_ratio", "pegRatio", "peg"),
    "price_to_sales": ("price_to_sales", "priceToSalesTrailing12Months", "ps_ratio"),
    "fcf_yield": ("fcf_yield", "free_cash_flow_yield", "freeCashFlowYield"),
}


def extract_financial_snapshot(pick: dict[str, Any]) -> dict[str, Any]:
    """Return a stable financial snapshot without inventing unavailable metrics.

    Values are preserved as supplied by the upstream provider. In particular, growth
    and margin values are not automatically multiplied by 100 because providers may
    expose either fractions or percentages.
    """

    dsa_context = pick.get("dsa_context")
    if not isinstance(dsa_context, dict):
        dsa_context = {}
    fundamentals = dsa_context.get("fundamentals")
    if not isinstance(fundamentals, dict):
        fundamentals = {}

    valuation: dict[str, Any] = {}
    pe_ratio = _usable(pick.get("pe_ratio"))
    pb_ratio = _usable(pick.get("pb_ratio"))
    if pe_ratio is not None:
        valuation["pe_ratio"] = pe_ratio
    if pb_ratio is not None:
        valuation["pb_ratio"] = pb_ratio
    for canonical, aliases in VALUATION_ALIASES.items():
        found = _find_first(fundamentals, aliases)
        if found is not None:
            valuation[canonical] = found

    earnings: dict[str, Any] = {}
    for canonical, aliases in EARNINGS_ALIASES.items():
        found = _find_first(fundamentals, aliases)
        if found is not None:
            earnings[canonical] = found

    coverage = fundamentals.get("coverage")
    if not isinstance(coverage, dict):
        coverage = {}

    evidence_count = len(valuation) + len(earnings)
    if fundamentals and evidence_count >= 4:
        confidence = "high"
    elif fundamentals or evidence_count >= 2:
        confidence = "medium"
    elif evidence_count:
        confidence = "low"
    else:
        confidence = "none"

    mode = "fundamentals" if fundamentals else ("valuation_only" if valuation else "none")
    return {
        "mode": mode,
        "confidence": confidence,
        "valuation": valuation,
        "earnings": earnings,
        "fundamentals": fundamentals,
        "coverage": coverage,
        "source_payload": str(dsa_context.get("source_payload") or ""),
        "warnings": [str(item) for item in dsa_context.get("warnings", []) if item],
    }


def _find_first(payload: Any, aliases: tuple[str, ...]) -> Any:
    alias_set = {alias.casefold() for alias in aliases}
    for key, value in _walk_items(payload):
        if key.casefold() in alias_set:
            usable = _usable(value)
            if usable is not None:
                return usable
    return None


def _walk_items(value: Any):
    if isinstance(value, dict):
        for key, child in value.items():
            yield str(key), child
            if isinstance(child, (dict, list, tuple)):
                yield from _walk_items(child)
    elif isinstance(value, (list, tuple)):
        for child in value:
            if isinstance(child, (dict, list, tuple)):
                yield from _walk_items(child)


def _usable(value: Any) -> Any:
    if value is None or value == "":
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    return None
