"""Edge Concentration Engine.

Answers a narrower question than "is this strategy good": does its
profit come from a broad base of trades, time periods, symbols, sectors,
and regimes, or does it depend on a tiny, fragile slice of them?
Strategy-independent; it consumes a caller-supplied sequence of trade
records and never reads PerformanceReport fields itself.

All concentration is measured against **Gross Positive PnL** -- the sum of
PnL across winning trades only (``pnl > 0``). Net PnL (winners minus
losers) is never used as a denominator here: it is unstable near zero and,
more importantly, using it (or sizing "Top N%" off the full trade count)
would let a caller dilute a genuinely concentrated edge by padding the
input with extra zero- or negative-PnL trades. Every "Top N%" population is
sized off ``positive_trade_count`` alone
(``max(1, ceil(positive_trade_count * fraction))``), and every contribution
evidence ratio (Top-1%/5%, Top-month(s), Top-symbol(s), Top-sector,
Top-regime) is denominated in Gross Positive PnL -- padding cannot move
either number, so padding cannot lower a reported concentration. The one
exception is HHI for a coverage-gated dimension (symbol/sector/regime):
once that dimension clears its metadata-coverage gate, its HHI is computed
on the known-metadata *conditional* distribution, not directly on Gross
Positive PnL -- see ``_dimension_with_missing_metadata`` and the paragraph
below for why.

This padding-invariance guarantee applies to *concentration results* --
comparisons between two samples that have both already cleared the
sparse-data eligibility gates below (``NO_POSITIVE_EDGE`` /
``INSUFFICIENT_DATA``). It says nothing about ``fragility_label`` when
padding pushes a sample *across* one of those eligibility boundaries (e.g.
from below ``minimum_trade_count`` to at/above it): that is expected,
desired sensitivity to genuinely having more evaluable data, not the
concentration-dilution failure mode this guarantee rules out.

Fragility Score is the max of **normalized HHI** (Herfindahl-Hirschman
Index) across the trade / month / eligible-symbol / eligible-sector /
eligible-regime dimensions -- a weakest-link aggregation, deliberately not
an average, so one badly concentrated dimension cannot be diluted by four healthy ones
(the same philosophy as the frozen Hard Gate rule: no averaging away a
single failure). Top-1%/Top-5%/Top-month/Top-3-months/Top-symbol/
Top-5-symbols/Top-sector/Top-regime contribution ratios are reported as
explanatory evidence only -- they never feed the score directly, because a
raw contribution share does not correct for how many groups exist (e.g.
"top symbol = 40%" means something very different with 3 symbols traded
than with 300).

Missing symbol/sector/regime metadata is never treated as zero risk. The
frozen minimal input contract is only ``timestamp`` + ``pnl``; ``symbol``,
``sector``, and ``regime`` are all optional dimension metadata, and a
missing one must degrade only that dimension, never block trade/month
concentration. A trade with an unknown symbol/sector/regime is not folded
into a synthetic ``"__missing__"`` bucket and scored as if it were a
normal, low-risk group; instead, the fraction of Gross Positive PnL sitting
in trades with unknown symbol/sector/regime is reported separately
(``symbol_missing_positive_pnl_share`` / ``sector_missing_positive_pnl_share``
/ ``regime_missing_positive_pnl_share``). Coverage is measured the same way
for all three -- ``known_metadata_positive_pnl / GrossPositivePnL`` -- and
when it falls below the configured minimum, that dimension is excluded from
the Fragility Score and its official contribution/HHI metrics come back as
``None`` ("unavailable"), never as a falsely reassuring low number computed
from a handful of known trades.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from math import ceil, isfinite
from typing import Any, Callable, Hashable, Mapping, Sequence

from .config import EdgeConcentrationConfig


class EdgeFragilityLabel(str, Enum):
    INSUFFICIENT_DATA = "insufficient_data"
    NO_POSITIVE_EDGE = "no_positive_edge"
    DIVERSIFIED = "diversified"
    MODERATE = "moderate"
    CONCENTRATED = "concentrated"
    EXTREME = "extreme"


@dataclass(frozen=True)
class TradeObservation:
    pnl: float
    timestamp: datetime
    symbol: str | None = None
    sector: str | None = None
    regime: str | None = None
    return_pct: float | None = None
    holding_period: float | None = None

    def __post_init__(self) -> None:
        if not isfinite(self.pnl):
            raise ValueError("pnl must be finite")
        if not isinstance(self.timestamp, datetime):
            raise ValueError("timestamp must be a datetime")
        if self.symbol is not None and not self.symbol.strip():
            raise ValueError("symbol must be a non-empty string or None, not an empty string")
        if self.sector is not None and not self.sector.strip():
            raise ValueError("sector must be a non-empty string or None, not an empty string")
        if self.regime is not None and not self.regime.strip():
            raise ValueError("regime must be a non-empty string or None, not an empty string")
        if self.return_pct is not None and not isfinite(self.return_pct):
            raise ValueError("return_pct must be finite when provided")
        if self.holding_period is not None:
            if not isfinite(self.holding_period) or self.holding_period < 0:
                raise ValueError("holding_period must be a non-negative finite value when provided")


@dataclass(frozen=True)
class EdgeConcentrationResult:
    trade_count: int
    positive_trade_count: int
    fragility_label: EdgeFragilityLabel
    warnings: tuple[str, ...]
    gross_positive_pnl: float | None = None
    fragility_score: float | None = None

    # Evidence-only contribution ratios. Never feed fragility_score.
    top_1pct_contribution: float | None = None
    top_5pct_contribution: float | None = None
    top_month_contribution: float | None = None
    top_3_months_contribution: float | None = None
    top_symbol_contribution: float | None = None
    top_5_symbols_contribution: float | None = None
    top_sector_contribution: float | None = None
    top_regime_contribution: float | None = None

    # HHI and normalized HHI per dimension. trade/month are always computed
    # once past the sparse-data gates; symbol/sector/regime are gated by
    # metadata_coverage and come back None ("unavailable") when ineligible.
    trade_hhi: float | None = None
    trade_hhi_normalized: float | None = None
    month_hhi: float | None = None
    month_hhi_normalized: float | None = None
    symbol_hhi: float | None = None
    symbol_hhi_normalized: float | None = None
    sector_hhi: float | None = None
    sector_hhi_normalized: float | None = None
    regime_hhi: float | None = None
    regime_hhi_normalized: float | None = None

    # Missing-metadata reporting. Populated whenever gross_positive_pnl is
    # known, independent of whether the dimension is eligible for scoring --
    # this is what "not treated as zero risk" means in practice.
    symbol_missing_positive_pnl_share: float | None = None
    sector_missing_positive_pnl_share: float | None = None
    regime_missing_positive_pnl_share: float | None = None
    symbol_metadata_coverage: float | None = None
    sector_metadata_coverage: float | None = None
    regime_metadata_coverage: float | None = None
    symbol_metadata_trade_count_coverage: float | None = None
    sector_metadata_trade_count_coverage: float | None = None
    regime_metadata_trade_count_coverage: float | None = None

    evidence: Mapping[str, Any] = field(default_factory=dict)


def evaluate_edge_concentration(
    *,
    trades: Sequence[TradeObservation],
    config: EdgeConcentrationConfig,
) -> EdgeConcentrationResult:
    """Evaluate how concentrated a strategy's profit is across trades, time,
    symbols, sectors, and regimes.

    ``trades`` is the full set of trade records for the evaluation window
    (winners and losers both included -- losers are needed for
    ``minimum_trade_count`` sample-size context even though they never enter
    a concentration ratio). Raises ``ValueError`` if ``trades`` is empty.

    Three distinct "cannot compute a trustworthy score" states are kept
    separate rather than collapsed into one generic failure, and checked in
    this fixed order:

    - ``NO_POSITIVE_EDGE`` (checked first, regardless of trade_count): zero
      winning trades (Gross Positive PnL is 0). Concentration of a
      nonexistent edge is undefined, not "perfectly diversified" and not a
      sample-size problem that more trades would fix -- ``fragility_score``
      is ``None``, never fabricated. A handful of all-losing trades reports
      this, not ``INSUFFICIENT_DATA``, even though it is also below
      ``minimum_trade_count``.
    - ``INSUFFICIENT_DATA``: too few total trades, or too few winning
      trades, to trust Top-N%/HHI figures. ``fragility_score`` is ``None``.
    - A real label (``DIVERSIFIED``/``MODERATE``/``CONCENTRATED``/
      ``EXTREME``) is only returned once there is at least one winning
      trade and both sample-size gates pass.
    """

    if not trades:
        raise ValueError("trades must not be empty")

    trade_count = len(trades)
    positive_trades = [t for t in trades if t.pnl > 0]
    positive_trade_count = len(positive_trades)
    gross_positive_pnl = sum(t.pnl for t in positive_trades)
    if not isfinite(gross_positive_pnl):
        raise ValueError(
            "gross_positive_pnl aggregation overflowed to a non-finite value; "
            "refusing to generate a concentration score"
        )

    if positive_trade_count == 0:
        return EdgeConcentrationResult(
            trade_count=trade_count,
            positive_trade_count=0,
            gross_positive_pnl=0.0,
            fragility_label=EdgeFragilityLabel.NO_POSITIVE_EDGE,
            warnings=("no_positive_edge: no winning trades, concentration is undefined",),
        )

    if trade_count < config.minimum_trade_count:
        return EdgeConcentrationResult(
            trade_count=trade_count,
            positive_trade_count=positive_trade_count,
            gross_positive_pnl=gross_positive_pnl,
            fragility_label=EdgeFragilityLabel.INSUFFICIENT_DATA,
            warnings=(
                f"insufficient_trade_count: have {trade_count}, "
                f"need at least {config.minimum_trade_count}",
            ),
        )

    if positive_trade_count < config.minimum_positive_trade_count:
        return EdgeConcentrationResult(
            trade_count=trade_count,
            positive_trade_count=positive_trade_count,
            gross_positive_pnl=gross_positive_pnl,
            fragility_label=EdgeFragilityLabel.INSUFFICIENT_DATA,
            warnings=(
                f"insufficient_positive_trade_count: have {positive_trade_count}, "
                f"need at least {config.minimum_positive_trade_count}",
            ),
        )

    warnings: list[str] = []
    evidence: dict[str, Any] = {}

    # --- Trade dimension -------------------------------------------------
    positive_pnls = [t.pnl for t in positive_trades]
    trade_hhi = _hhi(positive_pnls, gross_positive_pnl)
    trade_hhi_normalized = _normalized_hhi(trade_hhi, positive_trade_count)

    sorted_desc = sorted(positive_pnls, reverse=True)
    top1_count = max(1, ceil(positive_trade_count * config.top_fraction_small))
    top5_count = max(1, ceil(positive_trade_count * config.top_fraction_large))
    top_1pct_contribution = sum(sorted_desc[:top1_count]) / gross_positive_pnl
    top_5pct_contribution = sum(sorted_desc[:top5_count]) / gross_positive_pnl

    # --- Month dimension ---------------------------------------------------
    month_groups = _group_pnl(positive_trades, key=lambda t: (t.timestamp.year, t.timestamp.month))
    month_hhi = _hhi(list(month_groups.values()), gross_positive_pnl)
    month_hhi_normalized = _normalized_hhi(month_hhi, len(month_groups))
    sorted_months = sorted(month_groups.values(), reverse=True)
    top_month_contribution = sorted_months[0] / gross_positive_pnl
    top_3_months_contribution = sum(sorted_months[: config.top_months_window]) / gross_positive_pnl
    evidence["month_group_count"] = len(month_groups)

    # --- Symbol dimension (metadata-coverage gated) -----------------------
    (
        symbol_hhi,
        symbol_hhi_normalized,
        top_symbol_contribution,
        top_5_symbols_contribution,
        symbol_missing_share,
        symbol_coverage,
        symbol_trade_count_coverage,
    ) = _dimension_with_missing_metadata(
        positive_trades=positive_trades,
        gross_positive_pnl=gross_positive_pnl,
        key=lambda t: t.symbol,
        minimum_coverage=config.minimum_metadata_coverage,
        dimension_name="symbol",
        warnings=warnings,
        evidence=evidence,
        extra_top_count=config.top_symbols_count,
    )

    # --- Sector dimension (metadata-coverage gated) -----------------------
    (
        sector_hhi,
        sector_hhi_normalized,
        top_sector_contribution,
        _sector_extra_top,
        sector_missing_share,
        sector_coverage,
        sector_trade_count_coverage,
    ) = _dimension_with_missing_metadata(
        positive_trades=positive_trades,
        gross_positive_pnl=gross_positive_pnl,
        key=lambda t: t.sector,
        minimum_coverage=config.minimum_metadata_coverage,
        dimension_name="sector",
        warnings=warnings,
        evidence=evidence,
    )

    # --- Regime dimension (metadata-coverage gated) -----------------------
    (
        regime_hhi,
        regime_hhi_normalized,
        top_regime_contribution,
        _regime_extra_top,
        regime_missing_share,
        regime_coverage,
        regime_trade_count_coverage,
    ) = _dimension_with_missing_metadata(
        positive_trades=positive_trades,
        gross_positive_pnl=gross_positive_pnl,
        key=lambda t: t.regime,
        minimum_coverage=config.minimum_metadata_coverage,
        dimension_name="regime",
        warnings=warnings,
        evidence=evidence,
    )

    fragility_components = [trade_hhi_normalized, month_hhi_normalized]
    if symbol_hhi_normalized is not None:
        fragility_components.append(symbol_hhi_normalized)
    if sector_hhi_normalized is not None:
        fragility_components.append(sector_hhi_normalized)
    if regime_hhi_normalized is not None:
        fragility_components.append(regime_hhi_normalized)
    fragility_score = max(fragility_components)

    if fragility_score >= config.fragility_extreme_floor:
        label = EdgeFragilityLabel.EXTREME
    elif fragility_score >= config.fragility_concentrated_floor:
        label = EdgeFragilityLabel.CONCENTRATED
    elif fragility_score >= config.fragility_moderate_floor:
        label = EdgeFragilityLabel.MODERATE
    else:
        label = EdgeFragilityLabel.DIVERSIFIED

    return EdgeConcentrationResult(
        trade_count=trade_count,
        positive_trade_count=positive_trade_count,
        gross_positive_pnl=gross_positive_pnl,
        fragility_label=label,
        fragility_score=fragility_score,
        warnings=tuple(warnings),
        top_1pct_contribution=top_1pct_contribution,
        top_5pct_contribution=top_5pct_contribution,
        top_month_contribution=top_month_contribution,
        top_3_months_contribution=top_3_months_contribution,
        top_symbol_contribution=top_symbol_contribution,
        top_5_symbols_contribution=top_5_symbols_contribution,
        top_sector_contribution=top_sector_contribution,
        top_regime_contribution=top_regime_contribution,
        trade_hhi=trade_hhi,
        trade_hhi_normalized=trade_hhi_normalized,
        month_hhi=month_hhi,
        month_hhi_normalized=month_hhi_normalized,
        symbol_hhi=symbol_hhi,
        symbol_hhi_normalized=symbol_hhi_normalized,
        sector_hhi=sector_hhi,
        sector_hhi_normalized=sector_hhi_normalized,
        regime_hhi=regime_hhi,
        regime_hhi_normalized=regime_hhi_normalized,
        symbol_missing_positive_pnl_share=symbol_missing_share,
        sector_missing_positive_pnl_share=sector_missing_share,
        regime_missing_positive_pnl_share=regime_missing_share,
        symbol_metadata_coverage=symbol_coverage,
        sector_metadata_coverage=sector_coverage,
        regime_metadata_coverage=regime_coverage,
        symbol_metadata_trade_count_coverage=symbol_trade_count_coverage,
        sector_metadata_trade_count_coverage=sector_trade_count_coverage,
        regime_metadata_trade_count_coverage=regime_trade_count_coverage,
        evidence=evidence,
    )


def _group_pnl(
    trades: Sequence[TradeObservation], *, key: Callable[[TradeObservation], Hashable]
) -> dict[Hashable, float]:
    groups: dict[Any, float] = defaultdict(float)
    for trade in trades:
        groups[key(trade)] += trade.pnl
    for value in groups.values():
        if not isfinite(value):
            raise ValueError(
                "grouped pnl aggregation overflowed to a non-finite value; "
                "refusing to generate a concentration score"
            )
    return dict(groups)


def _hhi(values: Sequence[float], denominator: float) -> float:
    return sum((value / denominator) ** 2 for value in values)


def _normalized_hhi(hhi: float, group_count: int) -> float:
    """Map HHI's theoretical range [1/N, 1] onto [0, 1].

    N=1 (a single group holds everything) always normalizes to 1.0,
    regardless of the raw HHI value, since 1/N == 1 makes the ratio
    undefined -- perfect concentration by a single group is the maximal
    fragility signal by definition.
    """

    if group_count <= 1:
        return 1.0
    floor = 1.0 / group_count
    normalized = (hhi - floor) / (1.0 - floor)
    return max(0.0, min(1.0, normalized))


def _dimension_with_missing_metadata(
    *,
    positive_trades: Sequence[TradeObservation],
    gross_positive_pnl: float,
    key: Callable[[TradeObservation], str | None],
    minimum_coverage: float,
    dimension_name: str,
    warnings: list[str],
    evidence: dict[str, Any],
    extra_top_count: int | None = None,
) -> tuple[float | None, float | None, float | None, float | None, float, float, float]:
    """Shared symbol/sector/regime handling: missing metadata is reported,
    never silently folded into a scored bucket (no synthetic
    ``"__missing__"`` group) or treated as zero risk.

    Returns (hhi, hhi_normalized, top_contribution, extra_top_contribution,
    missing_share, coverage, trade_count_coverage). The first four are None
    ("unavailable") when coverage falls below ``minimum_coverage``.
    ``extra_top_contribution`` is only ever non-None when the caller passes
    ``extra_top_count`` (symbol's Top-5-symbols evidence metric; sector/regime
    don't use it and get None unconditionally).

    Once eligible, the HHI is computed over the known-metadata *conditional*
    distribution -- group pnl divided by ``known_positive_pnl``, not the
    full ``gross_positive_pnl`` -- so group shares sum to 1 and
    ``_normalized_hhi``'s [1/N, 1] range assumption actually holds. Using
    ``gross_positive_pnl`` here (as an earlier version of this function did)
    would leave shares summing to `coverage` (< 1 whenever any metadata is
    missing), silently deflating the raw HHI and producing a false-safe
    normalized value even for a genuinely concentrated known-sector split.
    ``top_contribution`` (and ``extra_top_contribution``) deliberately keep
    ``gross_positive_pnl`` as their denominator -- they answer "how much of
    *all* profit" came from this group/these groups, a different, still
    gross-denominated question from the others' Top-N% evidence metrics.
    """

    known_trades = [t for t in positive_trades if key(t) is not None]
    known_positive_pnl = sum(t.pnl for t in known_trades)
    if not isfinite(known_positive_pnl):
        raise ValueError(
            f"{dimension_name} known_positive_pnl aggregation overflowed to a "
            "non-finite value; refusing to generate a concentration score"
        )
    missing_share = (gross_positive_pnl - known_positive_pnl) / gross_positive_pnl
    coverage = known_positive_pnl / gross_positive_pnl
    trade_count_coverage = len(known_trades) / len(positive_trades)

    evidence[f"{dimension_name}_known_group_count"] = len({key(t) for t in known_trades})

    if coverage < minimum_coverage:
        warnings.append(f"insufficient_{dimension_name}_metadata")
        return None, None, None, None, missing_share, coverage, trade_count_coverage

    groups = _group_pnl(known_trades, key=key)
    hhi = _hhi(list(groups.values()), known_positive_pnl)
    hhi_normalized = _normalized_hhi(hhi, len(groups))
    top_contribution = max(groups.values()) / gross_positive_pnl
    extra_top_contribution = None
    if extra_top_count is not None:
        sorted_groups = sorted(groups.values(), reverse=True)
        extra_top_contribution = sum(sorted_groups[:extra_top_count]) / gross_positive_pnl
    return (
        hhi,
        hhi_normalized,
        top_contribution,
        extra_top_contribution,
        missing_share,
        coverage,
        trade_count_coverage,
    )
