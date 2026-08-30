"""Layered technical research primitives.

The package deliberately describes market state instead of emitting trading
orders.  Selection and deep-research consumers can therefore share the same
evidence while applying different scoring policies.
"""

from .models import MultiTimeframeTechnicalResult, PriceStructure, TimeframeState
from .technical_analyzer import TechnicalAnalyzer

__all__ = [
    "MultiTimeframeTechnicalResult",
    "PriceStructure",
    "TechnicalAnalyzer",
    "TimeframeState",
]
