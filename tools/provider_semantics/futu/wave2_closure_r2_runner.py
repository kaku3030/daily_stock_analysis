"""Wave 2 Closure R2 -- active-session reconnect/catch-up empirical
qualification (F17, F18, AUTO_RESUBSCRIBE, F15).

Builds on the safe Level-1 proxy mechanics already exercised in
wave2r1_runner.py, but fixes the one thing that runner got wrong: it is
now structurally impossible for this script to issue a synchronous Futu
RPC while the proxy transport is cut. Every RPC call site goes through an
``OutageRpcGuard`` (outage_guard.py), and no RPC call is even attempted
between ``guard.transition(TRANSPORT_CUT)`` and
``guard.transition(RESTORED)`` -- not "guarded and caught", genuinely
absent from the code path, so the prior ~19-minute query_subscription
deadlock cannot recur even in principle.

Does NOT touch OpenD (no restart/kill), does NOT touch firewall/network
configuration, does NOT call any trading API, does not implement any
production code. Collects evidence only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lifecycle_recorder import LifecycleRecorder  # noqa: E402
from outage_guard import ExperimentState, OutageRpcGuard, ProviderRpcForbiddenDuringOutage  # noqa: E402
from recorder import build_run_metadata, harness_version_hash, new_run_dir, utc_now_iso  # noqa: E402
from transport_proxy import TransportProxy  # noqa: E402

import futu as ft  # noqa: E402

HKT = timezone(timedelta(hours=8))


def _payload_hash(payload) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode("utf-8")).hexdigest()[:16]


def _hkt_now() -> datetime:
    return datetime.now(timezone.utc).astimezone(HKT)


def _minutes_left_in_session(hkt_now: datetime) -> float | None:
    """Fixed-clock estimate only (no calendar/holiday awareness) -- used
    purely as a defensive floor alongside the live get_global_state check,
    never as the sole authority for whether the market is open.
    """

    t = hkt_now.time()
    morning_end = hkt_now.replace(hour=12, minute=0, second=0, microsecond=0)
    afternoon_end = hkt_now.replace(hour=16, minute=0, second=0, microsecond=0)
    if t < morning_end.time():
        return (morning_end - hkt_now).total_seconds() / 60.0
    if t < afternoon_end.time():
        return (afternoon_end - hkt_now).total_seconds() / 60.0
    return None


def make_recording_context_class(recorder: LifecycleRecorder, ctx_id_holder: dict):
    class RecordingQuoteContext(ft.OpenQuoteContext):
        def on_disconnect(self, conn_id, reason, msg):
            recorder.record_lifecycle(
                event_type="CONNECTION_ERROR",
                origin="PROVIDER_SDK",
                quote_context_id=ctx_id_holder.get("current"),
                connection_attempt_id=ctx_id_holder.get("cycle_tag"),
                raw_payload={
                    "conn_id": conn_id,
                    "reason": str(reason),
                    "msg": msg,
                    "is_client_initiated_close": str(reason) == "CloseReason.Close",
                    "python_ctx_object_id": id(self),
                },
            )
            return super().on_disconnect(conn_id, reason, msg)

        def on_api_socket_reconnected(self, *args, **kwargs):
            recorder.record_lifecycle(
                event_type="PROVIDER_EVENT",
                origin="PROVIDER_SDK",
                quote_context_id=ctx_id_holder.get("current"),
                connection_attempt_id=ctx_id_holder.get("cycle_tag"),
                raw_payload={"sdk_event": "on_api_socket_reconnected", "python_ctx_object_id": id(self)},
            )
            return super().on_api_socket_reconnected(*args, **kwargs)

    return RecordingQuoteContext


def make_quote_handler(recorder: LifecycleRecorder, ctx_id_holder: dict):
    class _H(ft.StockQuoteHandlerBase):
        def on_recv_rsp(self, rsp_pb):
            ret_code, data = super().on_recv_rsp(rsp_pb)
            if ret_code != ft.RET_OK:
                return ft.RET_ERROR, data
            for row in data.to_dict(orient="records"):
                recorder.record_lifecycle(
                    event_type="DATA_CALLBACK", origin="PROVIDER_SDK",
                    quote_context_id=ctx_id_holder.get("current"),
                    connection_attempt_id=ctx_id_holder.get("cycle_tag"),
                    symbol=row.get("code"), stream_type="QUOTE",
                    raw_provider_timestamp=row.get("data_time"), raw_payload=row, raw_ret_code=ret_code,
                )
            return ft.RET_OK, data
    return _H()


def make_kline_handler(recorder: LifecycleRecorder, ctx_id_holder: dict):
    class _H(ft.CurKlineHandlerBase):
        def on_recv_rsp(self, rsp_pb):
            ret_code, data = super().on_recv_rsp(rsp_pb)
            if ret_code != ft.RET_OK:
                return ft.RET_ERROR, data
            for row in data.to_dict(orient="records"):
                recorder.record_lifecycle(
                    event_type="DATA_CALLBACK", origin="PROVIDER_SDK",
                    quote_context_id=ctx_id_holder.get("current"),
                    connection_attempt_id=ctx_id_holder.get("cycle_tag"),
                    symbol=row.get("code"), stream_type="K_1M",
                    raw_provider_timestamp=row.get("time_key"), raw_payload=row, raw_ret_code=ret_code,
                )
            return ft.RET_OK, data
    return _H()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Wave 2 Closure R2: active-session reconnect/catch-up evidence")
    parser.add_argument("--opend-host", default="127.0.0.1")
    parser.add_argument("--opend-port", type=int, default=11111)
    parser.add_argument("--proxy-port", type=int, default=23457)
    parser.add_argument("--symbol", default="HK.00700")
    parser.add_argument("--output-dir", default=str(Path(__file__).resolve().parent / "runs"))
    parser.add_argument("--max-cycles", type=int, default=3)
    parser.add_argument("--cut-seconds", type=int, default=170, help="Hold time; must span >=2 K_1M interval boundaries")
    parser.add_argument("--post-recovery-wait-seconds", type=int, default=260, help="Bounded wait for >=2 future K_1M opportunities after first recovery")
    parser.add_argument("--min-session-minutes-to-start-cycle", type=float, default=6.0)
    args = parser.parse_args(argv)

    runtime_run_id = str(uuid.uuid4())
    run_dir = new_run_dir(Path(args.output_dir))
    recorder = LifecycleRecorder(run_dir, runtime_run_id=runtime_run_id)
    guard = OutageRpcGuard()
    ctx_id_holder: dict = {"current": None, "cycle_tag": None}

    # ---- upfront session gate (this is an explicit RPC, done while guard is IDLE -- always safe) ----
    probe_ctx = ft.OpenQuoteContext(host=args.opend_host, port=args.opend_port)
    ret, global_state = probe_ctx.get_global_state()
    probe_ctx.close()
    market_hk = global_state.get("market_hk") if isinstance(global_state, dict) else None
    market_active = market_hk in ("MORNING", "AFTERNOON")
    start_hkt = _hkt_now()
    minutes_left = _minutes_left_in_session(start_hkt)

    print(f"HK SESSION STATUS: {market_hk} (active={market_active}), HKT now={start_hkt.isoformat()}, "
          f"fixed-clock minutes_left_estimate={minutes_left}")

    if not market_active or minutes_left is None or minutes_left < args.min_session_minutes_to_start_cycle:
        recorder.write_metadata({
            **build_run_metadata(
                host=args.opend_host, port=args.opend_port, futu_sdk_version=getattr(ft, "__version__", "unknown"),
                opend_version=str(global_state.get("server_ver")) if isinstance(global_state, dict) else None,
                opend_raw_global_state=global_state if isinstance(global_state, dict) else {"raw_repr": repr(global_state)},
                harness_version_hash=harness_version_hash(),
            ),
            "purpose": "Wave 2 Closure R2: active-session reconnect/catch-up (F17/F18/AUTO_RESUBSCRIBE/F15)",
            "market_hk": market_hk,
            "market_active": market_active,
            "session_gate_result": "DEFERRED_SESSION_NOT_ACTIVE_OR_INSUFFICIENT_TIME",
            "start_hkt": start_hkt.isoformat(),
            "minutes_left_estimate": minutes_left,
            "runtime_run_id": runtime_run_id,
        })
        print("R2 DEFERRED — SESSION NOT ACTIVE")
        return 2

    recorder.write_metadata({
        **build_run_metadata(
            host=args.opend_host, port=args.opend_port, futu_sdk_version=getattr(ft, "__version__", "unknown"),
            opend_version=str(global_state.get("server_ver")) if isinstance(global_state, dict) else None,
            opend_raw_global_state=global_state if isinstance(global_state, dict) else {"raw_repr": repr(global_state)},
            harness_version_hash=harness_version_hash(),
        ),
        "purpose": "Wave 2 Closure R2: active-session reconnect/catch-up (F17/F18/AUTO_RESUBSCRIBE/F15)",
        "market_hk": market_hk,
        "market_active": market_active,
        "start_hkt": start_hkt.isoformat(),
        "minutes_left_estimate": minutes_left,
        "cli_args": vars(args),
        "runtime_run_id": runtime_run_id,
    })
    print(f"Run directory: {run_dir}")

    # ---- proxy + context setup (once; reused across all cycles) ----
    proxy = TransportProxy("127.0.0.1", args.proxy_port, args.opend_host, args.opend_port)
    proxy.start()
    time.sleep(0.3)

    def drain_proxy_events(label: str) -> None:
        for ev in proxy.drain_events():
            recorder.record_lifecycle(event_type="PROVIDER_EVENT", origin="HARNESS", raw_payload={"proxy_event": ev, "label": label})

    RecordingQuoteContext = make_recording_context_class(recorder, ctx_id_holder)
    ctx_id_holder["current"] = str(uuid.uuid4())[:8]
    ctx_id_holder["cycle_tag"] = "baseline"
    recorder.record_lifecycle(event_type="CONTEXT_CREATE_BEGIN", origin="HARNESS", quote_context_id=ctx_id_holder["current"], raw_payload={"via": "proxy"})
    try:
        ctx = RecordingQuoteContext(host="127.0.0.1", port=args.proxy_port)
    except Exception as exc:
        recorder.record_lifecycle(event_type="CONTEXT_CREATE_ERROR", origin="HARNESS", raw_error_text=repr(exc))
        proxy.stop()
        print("BASELINE: TEST_BLOCKED_SAFETY / PROXY_INVALID -- context creation through proxy failed")
        return 1
    recorder.record_lifecycle(event_type="CONTEXT_CREATE_OK", origin="HARNESS", quote_context_id=ctx_id_holder["current"], raw_payload={"python_ctx_object_id": id(ctx)})
    drain_proxy_events("after_create")

    ctx.set_handler(make_quote_handler(recorder, ctx_id_holder))
    ctx.set_handler(make_kline_handler(recorder, ctx_id_holder))

    guard.transition(ExperimentState.BASELINE)
    recorder.record_lifecycle(event_type="SUBSCRIBE_CALL_BEGIN", origin="HARNESS", quote_context_id=ctx_id_holder["current"], raw_payload={"symbols": [args.symbol], "subtypes": ["QUOTE", "K_1M"]})
    ret, err = guard.call("subscribe", ctx.subscribe, [args.symbol], [ft.SubType.QUOTE, ft.SubType.K_1M], subscribe_push=True)
    recorder.record_lifecycle(event_type="SUBSCRIBE_CALL_RETURN", origin="PROVIDER_SDK", quote_context_id=ctx_id_holder["current"], raw_ret_code=ret, raw_error_text=str(err) if ret != 0 else None)
    drain_proxy_events("after_subscribe")

    qret, qdata = guard.call("query_subscription", ctx.query_subscription, is_all_conn=True)
    recorder.record_lifecycle(event_type="QUERY_SUBSCRIPTION_CALL", origin="PROVIDER_SDK", quote_context_id=ctx_id_holder["current"], raw_ret_code=qret, raw_payload=qdata if isinstance(qdata, dict) else {"raw_repr": repr(qdata)})

    # Wait for stable baseline flow: at least 2 distinct K_1M time_keys and
    # at least one QUOTE event before the first fault cycle.
    baseline_deadline = time.time() + 90
    kline_keys_seen: list[str] = []
    quote_seen = False
    while time.time() < baseline_deadline:
        drain_proxy_events("baseline_window")
        events_now = recorder.read_lifecycle()
        kline_keys_seen = sorted({
            e["raw_provider_timestamp"] for e in events_now
            if e["event_type"] == "DATA_CALLBACK" and e["stream_type"] == "K_1M" and e["symbol"] == args.symbol
        })
        quote_seen = any(e["event_type"] == "DATA_CALLBACK" and e["stream_type"] == "QUOTE" and e["symbol"] == args.symbol for e in events_now)
        if len(kline_keys_seen) >= 2 and quote_seen:
            break
        time.sleep(2)

    baseline_ok = ret == 0 and isinstance(qdata, dict) and qdata.get("sub_list") and len(kline_keys_seen) >= 1 and quote_seen
    print(f"BASELINE: subscribe ret={ret}, sub_list_present={bool(qdata.get('sub_list')) if isinstance(qdata, dict) else False}, "
          f"kline_keys_seen={kline_keys_seen}, quote_seen={quote_seen}, ok={baseline_ok}")
    if not baseline_ok:
        recorder.write_observations({"status": "TEST_BLOCKED_SAFETY", "reason": "baseline flow did not stabilize within 90s"})
        try:
            guard.transition(ExperimentState.RESTORED)
            ctx.close()
        except Exception:
            pass
        proxy.stop()
        return 1

    # ---- cycle loop ----
    cycle_summaries = []
    for cycle_num in range(1, args.max_cycles + 1):
        now_hkt = _hkt_now()
        minutes_left = _minutes_left_in_session(now_hkt)
        gret, gstate = guard.call("get_global_state", ctx.get_global_state)
        market_hk_now = gstate.get("market_hk") if isinstance(gstate, dict) else None
        if market_hk_now not in ("MORNING", "AFTERNOON") or minutes_left is None or minutes_left < args.min_session_minutes_to_start_cycle:
            print(f"CYCLE {cycle_num}: skipping -- session no longer active/sufficient "
                  f"(market_hk={market_hk_now}, minutes_left={minutes_left})")
            break

        ctx_id_holder["cycle_tag"] = f"cycle{cycle_num}"
        recorder.record_lifecycle(event_type="BASELINE_CHECKPOINT", origin="HARNESS", quote_context_id=ctx_id_holder["current"], connection_attempt_id=ctx_id_holder["cycle_tag"], raw_payload={"phase": "cycle_start", "cycle": cycle_num, "market_hk": market_hk_now, "minutes_left_estimate": minutes_left})
        print(f"\n=== CYCLE {cycle_num} START (market_hk={market_hk_now}, minutes_left~{minutes_left:.1f}) ===")

        # ---- PHASE A: pre-fault ----
        events_now = recorder.read_lifecycle()
        pre_kline = [e for e in events_now if e["event_type"] == "DATA_CALLBACK" and e["stream_type"] == "K_1M" and e["symbol"] == args.symbol]
        pre_quote = [e for e in events_now if e["event_type"] == "DATA_CALLBACK" and e["stream_type"] == "QUOTE" and e["symbol"] == args.symbol]
        last_pre_kline = pre_kline[-1] if pre_kline else None
        last_pre_quote = pre_quote[-1] if pre_quote else None
        established_before = [
            e for e in events_now if e["event_type"] == "PROVIDER_EVENT" and e.get("raw_payload", {}).get("proxy_event", {}).get("event") == "CONNECTION_ESTABLISHED"
        ]
        recorder.record_lifecycle(
            event_type="BASELINE_CHECKPOINT", origin="HARNESS", quote_context_id=ctx_id_holder["current"], connection_attempt_id=ctx_id_holder["cycle_tag"],
            raw_payload={
                "phase": "pre_fault", "cycle": cycle_num,
                "last_pre_fault_kline_time_key": last_pre_kline["raw_provider_timestamp"] if last_pre_kline else None,
                "last_pre_fault_quote_data_time": last_pre_quote["raw_provider_timestamp"] if last_pre_quote else None,
                "last_pre_fault_kline_hash": _payload_hash(last_pre_kline["raw_payload"]) if last_pre_kline else None,
                "proxy_connections_established_so_far": len(established_before),
                "python_ctx_object_id": id(ctx),
            },
        )

        # ---- PHASE B: cut (NO RPCs of any kind in this block) ----
        guard.transition(ExperimentState.TRANSPORT_CUT)
        cut_monotonic_ns = time.monotonic_ns()
        cut_started_hkt = _hkt_now()
        recorder.record_lifecycle(event_type="FAULT_INJECTION_BEGIN", origin="HARNESS", quote_context_id=ctx_id_holder["current"], connection_attempt_id=ctx_id_holder["cycle_tag"], raw_payload={"method": "LEVEL1_proxy_cut", "cut_monotonic_ns": cut_monotonic_ns, "cut_started_hkt": cut_started_hkt.isoformat()})
        proxy.cut()
        drain_proxy_events("at_cut")

        disconnect_seen_at = None
        for _ in range(int(args.cut_seconds * 2)):
            time.sleep(0.5)
            events_now = recorder.read_lifecycle()
            conn_errors = [e for e in events_now if e["event_type"] == "CONNECTION_ERROR" and e["connection_attempt_id"] == ctx_id_holder["cycle_tag"]]
            if conn_errors and disconnect_seen_at is None:
                disconnect_seen_at = conn_errors[0]
            drain_proxy_events("outage_window")
        recorder.record_lifecycle(event_type="FAULT_INJECTION_END", origin="HARNESS", quote_context_id=ctx_id_holder["current"], connection_attempt_id=ctx_id_holder["cycle_tag"], raw_payload={"phase": "cut_window_end"})

        refused_attempts = [
            e for e in recorder.read_lifecycle()
            if e["event_type"] == "PROVIDER_EVENT" and e.get("raw_payload", {}).get("proxy_event", {}).get("event") == "CONNECTION_REFUSED_DURING_CUT"
            and e.get("raw_payload", {}).get("label") in ("at_cut", "outage_window")
        ]
        disconnect_reason = disconnect_seen_at["raw_payload"].get("reason") if disconnect_seen_at else None
        print(f"CYCLE {cycle_num} CUT: held {args.cut_seconds}s, on_disconnect_observed={disconnect_seen_at is not None}, "
              f"reason={disconnect_reason}, refused_reconnect_attempts={len(refused_attempts)}")

        # ---- PHASE C: restore ----
        proxy.restore()
        guard.transition(ExperimentState.RESTORED)
        restored_hkt = _hkt_now()
        recorder.record_lifecycle(event_type="FAULT_INJECTION_END", origin="HARNESS", quote_context_id=ctx_id_holder["current"], connection_attempt_id=ctx_id_holder["cycle_tag"], raw_payload={"phase": "restore", "restored_hkt": restored_hkt.isoformat()})

        # Do NOT manually subscribe(). Observe whether SDK auto-resubscribe
        # restores data-plane flow on its own, and keep observing for
        # further future progress once it does.
        first_recovery_deadline = time.time() + 60
        first_post_recovery_kline = None
        first_post_recovery_quote = None
        while time.time() < first_recovery_deadline:
            drain_proxy_events("post_restore_window")
            events_now = recorder.read_lifecycle()
            post_kline = [e for e in events_now if e["event_type"] == "DATA_CALLBACK" and e["stream_type"] == "K_1M" and e["symbol"] == args.symbol and e["monotonic_ns"] > cut_monotonic_ns]
            post_quote = [e for e in events_now if e["event_type"] == "DATA_CALLBACK" and e["stream_type"] == "QUOTE" and e["symbol"] == args.symbol and e["monotonic_ns"] > cut_monotonic_ns]
            if post_kline and first_post_recovery_kline is None:
                first_post_recovery_kline = post_kline[0]
            if post_quote and first_post_recovery_quote is None:
                first_post_recovery_quote = post_quote[0]
            if first_post_recovery_kline is not None and first_post_recovery_quote is not None:
                break
            time.sleep(2)

        # Continue observing for >=2 FUTURE K_1M progress opportunities
        # beyond the first recovered one, bounded.
        future_deadline = time.time() + args.post_recovery_wait_seconds
        distinct_post_recovery_keys: list[str] = []
        while time.time() < future_deadline:
            events_now = recorder.read_lifecycle()
            post_kline_all = [e for e in events_now if e["event_type"] == "DATA_CALLBACK" and e["stream_type"] == "K_1M" and e["symbol"] == args.symbol and e["monotonic_ns"] > cut_monotonic_ns]
            distinct_post_recovery_keys = sorted({e["raw_provider_timestamp"] for e in post_kline_all})
            if len(distinct_post_recovery_keys) >= 3:  # first recovered + 2 future
                break
            time.sleep(3)

        established_after = [
            e for e in recorder.read_lifecycle()
            if e["event_type"] == "PROVIDER_EVENT" and e.get("raw_payload", {}).get("proxy_event", {}).get("event") == "CONNECTION_ESTABLISHED"
        ]

        summary = {
            "cycle": cycle_num,
            "last_pre_fault_kline_time_key": last_pre_kline["raw_provider_timestamp"] if last_pre_kline else None,
            "last_pre_fault_quote_data_time": last_pre_quote["raw_provider_timestamp"] if last_pre_quote else None,
            "cut_seconds_held": args.cut_seconds,
            "disconnect_observed": disconnect_seen_at is not None,
            "disconnect_reason": disconnect_reason,
            "refused_reconnect_attempts_during_cut": len(refused_attempts),
            "auto_resubscribe_data_return_without_manual_subscribe": (first_post_recovery_kline is not None or first_post_recovery_quote is not None),
            "first_post_recovery_kline_time_key": first_post_recovery_kline["raw_provider_timestamp"] if first_post_recovery_kline else None,
            "first_post_recovery_kline_hash": _payload_hash(first_post_recovery_kline["raw_payload"]) if first_post_recovery_kline else None,
            "first_post_recovery_quote_data_time": first_post_recovery_quote["raw_provider_timestamp"] if first_post_recovery_quote else None,
            "distinct_post_recovery_kline_time_keys_observed": distinct_post_recovery_keys,
            "proxy_connections_established_before_cycle": len(established_before),
            "proxy_connections_established_after_cycle": len(established_after),
            "python_ctx_object_id_pre": id(ctx),
            "python_ctx_object_id_post": id(ctx),
        }
        recorder.record_lifecycle(event_type="BASELINE_CHECKPOINT", origin="HARNESS", quote_context_id=ctx_id_holder["current"], connection_attempt_id=ctx_id_holder["cycle_tag"], raw_payload={"phase": "cycle_summary", **summary})
        cycle_summaries.append(summary)
        print(f"CYCLE {cycle_num} SUMMARY: {json.dumps(summary, default=str)}")

    # ---- final state, close ----
    final_hkt = _hkt_now()
    recorder.write_observations({
        "market_hk_at_start": market_hk,
        "start_hkt": start_hkt.isoformat(),
        "end_hkt": final_hkt.isoformat(),
        "cycles_completed": len(cycle_summaries),
        "cycle_summaries": cycle_summaries,
        "outage_guard_transitions": [(str(a), str(b)) for a, b in guard.transitions],
    })

    try:
        guard.transition(ExperimentState.RESTORED)
        ctx.close()
    except Exception:
        pass
    proxy.stop()
    print(f"\nDone. Raw evidence in: {run_dir}")
    print(f"Cycles completed: {len(cycle_summaries)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
