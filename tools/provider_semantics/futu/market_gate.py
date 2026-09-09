"""Wave 2 harness hardening: the market-session gate as a pure, testable
function, extracted from the ad-hoc inline check used in wave2r1_runner.py.

A run must never be allowed to start fault injection, and must never be
allowed to report itself as empirical F17/F18 evidence, unless this
function says the market is genuinely active.
"""

from __future__ import annotations

ACTIVE_HK_STATES = frozenset({"MORNING", "AFTERNOON"})


def is_market_active(market_state: str | None) -> bool:
    """True only for states this harness has confirmed correspond to a
    genuinely live regular HK session. Anything else (CLOSED,
    AFTER_HOURS_END, None, an unrecognized string) is treated as inactive
    -- fail closed, never fail open.
    """

    return market_state in ACTIVE_HK_STATES
