"""Builds the formal, immutable SDK source-inspection artifact (Part A of
the Offline Closure Pack). Run once per SDK version to (re)generate the
artifact; never overwrites a prior file -- each run gets a new revision
number if one already exists.

Usage:
    python build_source_inspection.py
"""

from __future__ import annotations

import hashlib
import inspect
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from recorder import utc_now_iso  # noqa: E402

import futu as ft  # noqa: E402
import futu.common.open_context_base as ocb  # noqa: E402


def _src(obj) -> str:
    try:
        return inspect.getsource(obj)
    except Exception as exc:
        return f"<unavailable: {exc!r}>"


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _fact(
    fact_id, module, cls, method, public_or_private, source, observed_semantic, confidence,
    excerpt_lines=None,
) -> dict:
    full_source = source
    excerpt = full_source if excerpt_lines is None else "\n".join(full_source.splitlines()[:excerpt_lines]) + "\n    ..."
    return {
        "fact_id": fact_id,
        "sdk_version": getattr(ft, "__version__", "unknown"),
        "module": module,
        "class": cls,
        "method": method,
        "public_or_private": public_or_private,
        "source_hash": _hash(full_source),
        "source_location_or_qualified_name": f"{module}.{cls}.{method}" if cls else f"{module}.{method}",
        "source_excerpt": excerpt,
        "observed_semantic": observed_semantic,
        "confidence": confidence,
    }


def build() -> dict:
    facts = []

    ctor_sig = str(inspect.signature(ft.OpenQuoteContext.__init__))
    facts.append({
        "fact_id": "F-SDK-001",
        "sdk_version": getattr(ft, "__version__", "unknown"),
        "module": "futu.quote.open_quote_context",
        "class": "OpenQuoteContext",
        "method": "__init__",
        "public_or_private": "public",
        "source_hash": _hash(_src(ft.OpenQuoteContext.__init__)),
        "source_location_or_qualified_name": "futu.quote.open_quote_context.OpenQuoteContext.__init__",
        "source_excerpt": ctor_sig,
        "observed_semantic": f"Public constructor signature: {ctor_sig}. No timeout, reconnect-interval, "
        f"max-attempts, or auto-reconnect-disable parameter exists among these.",
        "confidence": "SOURCE_VERIFIED",
    })

    facts.append(_fact(
        "F-SDK-002", "futu.common.open_context_base", "OpenContextBase", "__init__", "private (base class, not directly public API)",
        _src(ocb.OpenContextBase.__init__),
        "Sets self._auto_reconnect = True unconditionally (hardcoded, no parameter). Sets "
        "self._keep_alive_interval=10, self._conn_alive_timeout=33, self._reconnect_interval=6, "
        "self._query_timeout=12. When is_async_connect is False (default), loops "
        "'while True: ret=self._init_connect_sync(); if RET_OK: return; if not self._auto_reconnect: return; "
        "sleep(self._reconnect_interval)' -- unconditional retry with no attempt counter or bound when the "
        "target is unreachable and _auto_reconnect remains True (its unconditional default).",
        "SOURCE_VERIFIED",
    ))

    facts.append(_fact(
        "F-SDK-003", "futu.common.open_context_base", "OpenContextBase", "_init_connect_sync", "private",
        _src(ocb.OpenContextBase._init_connect_sync),
        "Calls self._connect_sync() then self._send_init_connect_sync(); on success, calls "
        "self.on_api_socket_reconnected() UNCONDITIONALLY -- i.e. every time a connection is established, "
        "not only on a genuine reconnect after a prior failure, but also on the very first connect.",
        "SOURCE_VERIFIED",
    ))

    facts.append(_fact(
        "F-SDK-004", "futu.common.open_context_base", "OpenContextBase", "_wait_reconnect", "private",
        _src(ocb.OpenContextBase._wait_reconnect),
        "If self._auto_reconnect is False, logs and returns (no reconnect attempted) -- this is the ONLY "
        "place auto-reconnect is actually skipped. Otherwise schedules self._reconnect via a "
        "threading.Timer(wait_reconnect_interval, ...), default 6 seconds.",
        "SOURCE_VERIFIED",
    ))

    facts.append(_fact(
        "F-SDK-005", "futu.common.open_context_base", "OpenContextBase", "_reconnect", "private",
        _src(ocb.OpenContextBase._reconnect),
        "Calls self._init_connect_sync(); on failure, closes the socket, clears state, and calls "
        "self._wait_reconnect(self._reconnect_interval) again if self._auto_reconnect is still True -- "
        "an unbounded retry cycle with a constant 6-second interval; no exponential backoff, no attempt "
        "counter, no maximum-retries field anywhere in this method or the ones it calls.",
        "SOURCE_VERIFIED",
    ))

    facts.append(_fact(
        "F-SDK-006", "futu.common.open_context_base", "OpenContextBase", "close", "public (abstract, overridden concretely by subclasses)",
        _src(ocb.OpenContextBase.close),
        "The ONLY place self._auto_reconnect is ever set to False: 'if reason is CloseReason.Close: "
        "self._auto_reconnect = False'. A client-initiated close() therefore permanently disables further "
        "auto-reconnect for that context object; any other CloseReason leaves auto-reconnect enabled.",
        "SOURCE_VERIFIED",
    ))

    facts.append(_fact(
        "F-SDK-007", "futu.quote.open_quote_context", "OpenQuoteContext", "on_disconnect", "public (overridable hook)",
        _src(ft.OpenQuoteContext.on_disconnect),
        "Logs the disconnect (info for CloseReason.Close, warning otherwise), sets status CLOSED, clears "
        "request state, and -- regardless of reason -- calls self._wait_reconnect() if self._auto_reconnect "
        "is still True at that point (which it will be for every reason except a prior client close()).",
        "SOURCE_VERIFIED",
    ))

    facts.append(_fact(
        "F-SDK-008", "futu.quote.open_quote_context", "OpenQuoteContext", "on_api_socket_reconnected", "public (overridable hook)",
        _src(ft.OpenQuoteContext.on_api_socket_reconnected),
        "Reads self._sub_record.get_sub_list() (a LOCAL, client-side, in-process record of previously "
        "issued subscriptions), and for each (code_list, subtype_list, ...) tuple calls "
        "self._reconnect_subscribe(...) -- a fresh, real subscribe request sent to OpenD. This is called "
        "unconditionally from _init_connect_sync on every successful connect (see F-SDK-003), including the "
        "very first connect of a context's lifetime.",
        "SOURCE_VERIFIED",
    ))

    facts.append(_fact(
        "F-SDK-009", "futu.quote.open_quote_context", "OpenQuoteContext", "_reconnect_subscribe", "private",
        _src(ft.OpenQuoteContext._reconnect_subscribe),
        "Splits the code list into K-line vs. non-K-line subtypes for batching, then calls "
        "self._subscribe_impl(...) -- the SAME underlying implementation a normal subscribe() call uses -- "
        "with is_first_push=True, subscribe_push=True. This is a genuine fresh subscribe request, not a "
        "cache replay or backfill request; it carries no information about what was missed while "
        "disconnected.",
        "SOURCE_VERIFIED",
    ))

    facts.append(_fact(
        "F-SDK-010", "futu.quote.open_quote_context", "OpenQuoteContext", "unsubscribe", "public",
        _src(ft.OpenQuoteContext.unsubscribe),
        "Client-side implementation contains NO rate-limiting, cooldown, or minimum-hold-time logic of any "
        "kind -- it validates params, updates the local self._sub_record, and sends a synchronous unsubscribe "
        "request to OpenD via query_processor, returning RET_ERROR with OpenD's own message text if OpenD "
        "rejects it. Any minimum-hold-time restriction observed empirically is therefore necessarily "
        "OpenD/server-side, not implemented anywhere in this installed client package.",
        "SOURCE_VERIFIED",
    ))

    facts.append(_fact(
        "F-SDK-011", "futu.quote.open_quote_context", "OpenQuoteContext", "_check_subscribe_param", "private",
        _src(ft.OpenQuoteContext._check_subscribe_param),
        "Pure syntactic validation only (non-empty lists, valid SubType keys, valid code string format). "
        "No timing, quota, or rate-limit logic of any kind.",
        "SOURCE_VERIFIED",
    ))

    facts.append(_fact(
        "F-SDK-012", "futu.quote.open_quote_context", "OpenQuoteContext", "query_subscription", "public",
        _src(ft.OpenQuoteContext.query_subscription),
        "Synchronous request/response call through the same _get_sync_query_processor machinery as most "
        "other OpenQuoteContext methods (see F-SDK-013). No special-cased disconnected-state short-circuit "
        "was found in this method's own body -- its blocking behavior when disconnected depends on the "
        "shared synchronous query path, which is why it was empirically observed to block during a "
        "transport outage in Wave 2 R1 (see EVIDENCE_INDEX in the semantic contract).",
        "PARTIAL",
    ))

    # Synchronous query machinery shared by most OpenQuoteContext methods.
    facts.append(_fact(
        "F-SDK-013", "futu.common.open_context_base", "OpenContextBase", "_get_sync_query_processor", "private",
        _src(ocb.OpenContextBase._get_sync_query_processor) if hasattr(ocb.OpenContextBase, "_get_sync_query_processor") else "<not found on OpenContextBase>",
        "Shared synchronous request/response dispatch path used by query_subscription, subscribe, "
        "unsubscribe, get_global_state, get_market_snapshot, and most other request-style OpenQuoteContext "
        "methods. No per-call timeout parameter is exposed publicly; behavior when the connection is down "
        "or mid-reconnect was not exhaustively traced for every caller, hence PARTIAL rather than "
        "SOURCE_VERIFIED for the general claim (only query_subscription's blocking was directly observed "
        "empirically).",
        "PARTIAL",
    ) if hasattr(ocb.OpenContextBase, "_get_sync_query_processor") else _fact(
        "F-SDK-013", "futu.common.open_context_base", "OpenContextBase", "_get_sync_query_processor", "private",
        "<method not found under this exact name in this SDK version>",
        "Could not locate this exact method name in the installed 10.08.6808 source; the shared synchronous "
        "dispatch mechanism exists (referenced by unsubscribe/query_subscription source) but its precise "
        "qualified location was not re-verified in this pass.",
        "UNRESOLVED",
    ))

    facts.append(_fact(
        "F-SDK-014", "futu.quote.open_quote_context", "OpenQuoteContext", "get_stock_quote (docstring)", "public",
        _src(ft.OpenQuoteContext.get_stock_quote),
        "Docstring explicitly states: 'data_time ... 时间（美股默认是美东时间，港股A股默认是北京时间）' -- "
        "i.e. 'time (US stocks default to US Eastern time, HK/A-share stocks default to Beijing time)'. This "
        "is a DIRECT, SOURCE-LEVEL, documented statement of QUOTE data_time's timezone semantics -- stronger "
        "than the unverified interpretation_candidate assumption used in prior empirical delay computations.",
        "SOURCE_VERIFIED",
    ))

    return {
        "artifact_type": "sdk_source_inspection",
        "analysis_revision": "offline_v1",
        "created_at": utc_now_iso(),
        "sdk_version": getattr(ft, "__version__", "unknown"),
        "answers": {
            "AUTO_RECONNECT_DEFAULT": "True (hardcoded, private attribute _auto_reconnect, no public control)",
            "PUBLIC_AUTO_RECONNECT_DISABLE": "NO_OBSERVED",
            "PUBLIC_RECONNECT_POLICY_CONTROL": "NO_OBSERVED",
            "PUBLIC_SYNC_CONNECT_TIMEOUT": "NO_OBSERVED",
            "RECONNECT_INTERVAL": "6 seconds (private _reconnect_interval, constant, no backoff)",
            "MAX_RETRIES": "NONE_OBSERVED (no attempt counter or cap found anywhere in the reconnect path; "
            "empirically confirmed via 193 consecutive real retries in Wave 2 Closure R1 with no change in "
            "cadence or a give-up event)",
            "AUTO_RESUBSCRIBE_SOURCE_PATH": "OpenContextBase._init_connect_sync -> OpenQuoteContext."
            "on_api_socket_reconnected -> OpenQuoteContext._reconnect_subscribe -> OpenQuoteContext."
            "_subscribe_impl (a fresh subscribe request using the client-local _sub_record cache; not a "
            "server-side replay/backfill mechanism)",
            "QUERY_SUBSCRIPTION_BLOCKING_PATH": "Shares the generic synchronous request/response dispatch "
            "path with most other OpenQuoteContext methods; no disconnected-state short-circuit was found "
            "in query_subscription's own body specifically. PARTIAL confidence for the general claim; "
            "SOURCE_VERIFIED + empirically confirmed for the specific blocking behavior actually observed.",
        },
        "facts": facts,
    }


def main() -> int:
    artifact = build()
    out_dir = Path(__file__).resolve().parent / "derived"
    out_dir.mkdir(exist_ok=True)
    out_path = out_dir / "source_inspection_offline_v1.json"
    if out_path.exists():
        existing = sorted(out_dir.glob("source_inspection_offline_v*.json"))
        out_path = out_dir / f"source_inspection_offline_v{len(existing) + 1}.json"
    out_path.write_text(json.dumps(artifact, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote: {out_path}")
    print(f"Fact count: {len(artifact['facts'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
