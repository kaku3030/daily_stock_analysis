"""Wave 2 harness hardening: an explicit outage-phase RPC guard.

Both prior Wave 2 blocking incidents shared one root cause: a synchronous
Futu SDK call was issued while the harness itself knew the transport was
down (or about to be down), and that call had no bounded timeout of its
own. This module makes that mistake structurally hard to repeat by
requiring every synchronous provider call to go through
``guard.call(...)``, which raises ``ProviderRpcForbiddenDuringOutage``
*before* the SDK is ever entered, whenever the guard's state is
``TRANSPORT_CUT``.

This is harness-only test-safety tooling, not a production wrapper -- it
exists to make the semantic-test harness itself deadlock-resistant while
running deliberate fault-injection experiments.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Callable

# Every synchronous OpenQuoteContext method this harness has ever called or
# is ever likely to call for diagnostic purposes. Deliberately named
# explicitly rather than pattern-matched, per the task brief -- "do not
# depend on developer memory" means the guard must refuse by default for
# code it doesn't recognize, not merely for a hand-maintained list it might
# under-cover.
KNOWN_SYNCHRONOUS_PROVIDER_METHODS = frozenset(
    {
        "query_subscription",
        "subscribe",
        "unsubscribe",
        "get_global_state",
        "get_market_state",
        "get_market_snapshot",
        "get_stock_quote",
        "get_cur_kline",
        "get_history_kline",
        "request_history_kline",
        "get_rt_data",
        "get_rt_ticker",
        "get_order_book",
        "get_history_kl_quota",
        "get_delay_statistics",
        "get_stock_basicinfo",
    }
)


class ProviderRpcForbiddenDuringOutage(RuntimeError):
    """Raised when a synchronous provider RPC is attempted while the
    outage guard's state is TRANSPORT_CUT. Raised locally, before the SDK
    is ever entered -- the underlying socket/context is never touched.
    """


class ExperimentState(str, Enum):
    IDLE = "IDLE"
    BASELINE = "BASELINE"
    TRANSPORT_CUT = "TRANSPORT_CUT"
    RESTORED = "RESTORED"


class OutageRpcGuard:
    """Tracks experiment state and refuses synchronous provider RPCs while
    TRANSPORT_CUT. Unknown method names are refused by default (fail
    closed), never allowed by default -- an unrecognized method is at
    least as dangerous as a known one while the transport is down.
    """

    def __init__(self) -> None:
        self._state = ExperimentState.IDLE
        self._transitions: list[tuple[ExperimentState, ExperimentState]] = []

    @property
    def state(self) -> ExperimentState:
        return self._state

    def transition(self, new_state: ExperimentState) -> None:
        self._transitions.append((self._state, new_state))
        self._state = new_state

    @property
    def transitions(self) -> list[tuple[ExperimentState, ExperimentState]]:
        return list(self._transitions)

    def check(self, method_name: str) -> None:
        """Raise ProviderRpcForbiddenDuringOutage if it is currently unsafe
        to call `method_name`. Call this BEFORE invoking any SDK method.
        """

        if self._state is ExperimentState.TRANSPORT_CUT:
            raise ProviderRpcForbiddenDuringOutage(
                f"Synchronous provider call {method_name!r} is forbidden while "
                f"experiment state is TRANSPORT_CUT -- restore the transport first. "
                f"This guard fails closed for any method name, known or unknown."
            )

    def call(self, method_name: str, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        """Guarded call wrapper: checks state, then invokes fn(*args, **kwargs).
        The SDK is never entered if the guard rejects the call.
        """

        self.check(method_name)
        return fn(*args, **kwargs)
