"""Wave 2 -- connection / recovery / subscription persistence.

LEVEL 0 (context-only) fault injection only. LEVEL 1 (transport
interruption) and LEVEL 2 (OpenD restart) are NOT exercised in this run --
see the module docstring in ``fault_injector.py`` and the Wave 2 Closure
report for why: a safe, non-machine-wide method to sever only this
process's transport to OpenD without reaching into a shared, undocumented
NetManager singleton's private internals was not identified, and OpenD
restart requires an explicit operator opt-in this task did not receive.

Read-only / market-data only. No trading/account-state APIs are ever
called. ``ft.OpenSecTradeContext`` is never imported or referenced.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fault_injector import find_listening_pid, level0_close_context  # noqa: E402
from lifecycle_recorder import LifecycleRecorder  # noqa: E402
from recorder import build_run_metadata, harness_version_hash, new_run_dir, utc_now_iso  # noqa: E402

import futu as ft  # noqa: E402


def _payload_hash(payload: dict) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode("utf-8")).hexdigest()[:16]


def make_recording_context_class(recorder: LifecycleRecorder, quote_context_id_holder: dict):
    """Subclass OpenQuoteContext to capture the genuinely SDK-exposed
    on_disconnect(conn_id, reason, msg) hook as structured lifecycle
    evidence, distinguishing CloseReason.Close (client-initiated) from any
    other reason -- while always calling super() so the SDK's own internal
    state machine (including its own auto-reconnect logic) is unaffected.
    """

    class RecordingQuoteContext(ft.OpenQuoteContext):
        def on_disconnect(self, conn_id, reason, msg):
            recorder.record_lifecycle(
                event_type="CONNECTION_ERROR" if str(reason) != "CloseReason.Close" else "CONTEXT_CLOSE_END",
                origin="PROVIDER_SDK",
                quote_context_id=quote_context_id_holder.get("current"),
                raw_provider_timestamp=None,
                raw_payload={"conn_id": conn_id, "reason": str(reason), "msg": msg},
            )
            return super().on_disconnect(conn_id, reason, msg)

    return RecordingQuoteContext


def make_recording_quote_handler(recorder: LifecycleRecorder, quote_context_id_holder: dict, market: str):
    class _Handler(ft.StockQuoteHandlerBase):
        def on_recv_rsp(self, rsp_pb):
            ret_code, data = super().on_recv_rsp(rsp_pb)
            if ret_code != ft.RET_OK:
                recorder.record_lifecycle(
                    event_type="DATA_CALLBACK", origin="PROVIDER_SDK",
                    quote_context_id=quote_context_id_holder.get("current"),
                    stream_type="QUOTE", raw_ret_code=ret_code, raw_error_text=str(data),
                )
                return ft.RET_ERROR, data
            for row in data.to_dict(orient="records"):
                recorder.record_lifecycle(
                    event_type="DATA_CALLBACK", origin="PROVIDER_SDK",
                    quote_context_id=quote_context_id_holder.get("current"),
                    symbol=row.get("code"), stream_type="QUOTE",
                    raw_provider_timestamp=row.get("data_time"), raw_payload=row, raw_ret_code=ret_code,
                )
            return ft.RET_OK, data

    return _Handler()


def make_recording_kline_handler(recorder: LifecycleRecorder, quote_context_id_holder: dict, stream_type: str):
    class _Handler(ft.CurKlineHandlerBase):
        def on_recv_rsp(self, rsp_pb):
            ret_code, data = super().on_recv_rsp(rsp_pb)
            if ret_code != ft.RET_OK:
                recorder.record_lifecycle(
                    event_type="DATA_CALLBACK", origin="PROVIDER_SDK",
                    quote_context_id=quote_context_id_holder.get("current"),
                    stream_type=stream_type, raw_ret_code=ret_code, raw_error_text=str(data),
                )
                return ft.RET_ERROR, data
            for row in data.to_dict(orient="records"):
                recorder.record_lifecycle(
                    event_type="DATA_CALLBACK", origin="PROVIDER_SDK",
                    quote_context_id=quote_context_id_holder.get("current"),
                    symbol=row.get("code"), stream_type=stream_type,
                    raw_provider_timestamp=row.get("time_key"), raw_payload=row, raw_ret_code=ret_code,
                )
            return ft.RET_OK, data

    return _Handler()


def wait_for_kline_events(recorder: LifecycleRecorder, symbol: str, min_count: int, timeout_s: float) -> list[dict]:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        events = [
            e for e in recorder.read_lifecycle()
            if e["event_type"] == "DATA_CALLBACK" and e["stream_type"] == "K_1M" and e["symbol"] == symbol
        ]
        if len(events) >= min_count:
            return events
        time.sleep(1)
    return [
        e for e in recorder.read_lifecycle()
        if e["event_type"] == "DATA_CALLBACK" and e["stream_type"] == "K_1M" and e["symbol"] == symbol
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Wave 2 connection/recovery/persistence experiments (Level 0 only)")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=11111)
    parser.add_argument("--symbol", default="HK.00700")
    parser.add_argument("--output-dir", default=str(Path(__file__).resolve().parent / "runs"))
    parser.add_argument("--f22-repetitions", type=int, default=5)
    parser.add_argument("--f17-cycles", type=int, default=2)
    parser.add_argument("--f17-outage-seconds", type=int, default=170)
    parser.add_argument("--allow-opend-restart", action="store_true", help="NOT used by this Level-0-only runner")
    args = parser.parse_args(argv)

    runtime_run_id = str(uuid.uuid4())
    run_dir = new_run_dir(Path(args.output_dir))
    recorder = LifecycleRecorder(run_dir, runtime_run_id=runtime_run_id)

    quote_context_id_holder: dict = {"current": None}
    RecordingQuoteContext = make_recording_context_class(recorder, quote_context_id_holder)

    def new_ctx(attempt_id: str) -> ft.OpenQuoteContext:
        recorder.record_lifecycle(event_type="CONTEXT_CREATE_BEGIN", origin="HARNESS", connection_attempt_id=attempt_id)
        try:
            ctx = RecordingQuoteContext(host=args.host, port=args.port)
        except Exception as exc:
            recorder.record_lifecycle(
                event_type="CONTEXT_CREATE_ERROR", origin="HARNESS", connection_attempt_id=attempt_id,
                raw_error_text=repr(exc),
            )
            raise
        qcid = str(uuid.uuid4())[:8]
        quote_context_id_holder["current"] = qcid
        recorder.record_lifecycle(
            event_type="CONTEXT_CREATE_OK", origin="HARNESS",
            connection_attempt_id=attempt_id, quote_context_id=qcid,
        )
        return ctx

    def close_ctx(ctx, reason_label: str) -> None:
        recorder.record_lifecycle(
            event_type="CONTEXT_CLOSE_BEGIN", origin="HARNESS",
            quote_context_id=quote_context_id_holder.get("current"), raw_payload={"reason_label": reason_label},
        )
        level0_close_context(ctx)
        # CONTEXT_CLOSE_END is also recorded by on_disconnect (PROVIDER_SDK
        # origin) above when the SDK actually fires the hook; this harness
        # does not assume it always will, so no HARNESS-origin CLOSE_END is
        # separately manufactured here.

    def query_sub(ctx, label: str) -> dict:
        recorder.record_lifecycle(
            event_type="QUERY_SUBSCRIPTION_CALL", origin="HARNESS",
            quote_context_id=quote_context_id_holder.get("current"), raw_payload={"label": label},
        )
        ret, data = ctx.query_subscription(is_all_conn=True)
        recorder.record_lifecycle(
            event_type="QUERY_SUBSCRIPTION_CALL", origin="PROVIDER_SDK",
            quote_context_id=quote_context_id_holder.get("current"),
            raw_ret_code=ret, raw_payload=data if isinstance(data, dict) else {"raw_repr": repr(data)},
        )
        return data if isinstance(data, dict) else {}

    def do_subscribe(ctx, symbols: list, subtypes: list, attempt_id: str) -> tuple:
        recorder.record_lifecycle(
            event_type="SUBSCRIBE_CALL_BEGIN", origin="HARNESS", connection_attempt_id=attempt_id,
            quote_context_id=quote_context_id_holder.get("current"),
            raw_payload={"symbols": symbols, "subtypes": [str(s) for s in subtypes]},
        )
        ret, err = ctx.subscribe(symbols, subtypes, subscribe_push=True)
        recorder.record_lifecycle(
            event_type="SUBSCRIBE_CALL_RETURN", origin="PROVIDER_SDK", connection_attempt_id=attempt_id,
            quote_context_id=quote_context_id_holder.get("current"), raw_ret_code=ret, raw_error_text=str(err) if ret != 0 else None,
        )
        return ret, err

    def do_unsubscribe(ctx, symbols: list, subtypes: list) -> tuple:
        recorder.record_lifecycle(
            event_type="UNSUBSCRIBE_CALL_BEGIN", origin="HARNESS",
            quote_context_id=quote_context_id_holder.get("current"),
            raw_payload={"symbols": symbols, "subtypes": [str(s) for s in subtypes]},
        )
        ret, err = ctx.unsubscribe(symbols, subtypes)
        recorder.record_lifecycle(
            event_type="UNSUBSCRIBE_CALL_RETURN", origin="PROVIDER_SDK",
            quote_context_id=quote_context_id_holder.get("current"), raw_ret_code=ret, raw_error_text=str(err) if ret != 0 else None,
        )
        return ret, err

    # ---- 0/1: connect, safety recording ----
    pid, image_name = find_listening_pid(args.port)
    ctx = new_ctx("initial")
    ret, global_state = ctx.get_global_state()
    recorder.write_metadata({
        **build_run_metadata(
            host=args.host, port=args.port, futu_sdk_version=getattr(ft, "__version__", "unknown"),
            opend_version=str(global_state.get("server_ver")) if isinstance(global_state, dict) else None,
            opend_raw_global_state=global_state if isinstance(global_state, dict) else {"raw_repr": repr(global_state)},
            harness_version_hash=harness_version_hash(),
        ),
        "purpose": "Wave 2: connection/recovery/subscription-persistence, LEVEL 0 only",
        "opend_pid": pid,
        "opend_image_name": image_name,
        "trd_logined": global_state.get("trd_logined") if isinstance(global_state, dict) else None,
        "qot_logined": global_state.get("qot_logined") if isinstance(global_state, dict) else None,
        "market_hk": global_state.get("market_hk") if isinstance(global_state, dict) else None,
        "level1_transport_interruption_used": False,
        "level2_opend_restart_used": False,
        "cli_args": vars(args),
        "runtime_run_id": runtime_run_id,
    })
    print(f"Run directory: {run_dir}")
    print(f"OpenD PID={pid} image={image_name}, market_hk={global_state.get('market_hk')}")

    subtypes = [ft.SubType.QUOTE, ft.SubType.K_1M]

    # ---- Baseline ----
    do_subscribe(ctx, [args.symbol], subtypes, "initial")
    ctx.set_handler(make_recording_quote_handler(recorder, quote_context_id_holder, "HK"))
    ctx.set_handler(make_recording_kline_handler(recorder, quote_context_id_holder, "K_1M"))
    sub_state = query_sub(ctx, "baseline")
    print("Baseline subscription state:", sub_state.get("sub_list"))
    time.sleep(20)
    baseline_klines = wait_for_kline_events(recorder, args.symbol, min_count=1, timeout_s=30)
    if baseline_klines:
        last = baseline_klines[-1]
        recorder.record_lifecycle(
            event_type="BASELINE_CHECKPOINT", origin="HARNESS", quote_context_id=quote_context_id_holder.get("current"),
            symbol=args.symbol, stream_type="K_1M",
            raw_provider_timestamp=last["raw_payload"].get("time_key"),
            raw_payload={"last_payload_hash": _payload_hash(last["raw_payload"]), "callback_count_so_far": len(baseline_klines)},
        )
    print(f"Baseline K_1M events observed: {len(baseline_klines)}")

    # ---- F22 / F23: unsubscribe + callback-drain barrier, N repetitions ----
    f22_results = []
    for rep in range(args.f22_repetitions):
        do_subscribe(ctx, [args.symbol], [ft.SubType.QUOTE], f"f22_rep{rep}_ensure")
        time.sleep(3)
        pre_seq = recorder.next_seq()
        recorder.record_lifecycle(event_type="UNSUBSCRIBE_CALL_BEGIN", origin="HARNESS", quote_context_id=quote_context_id_holder.get("current"), raw_payload={"rep": rep, "test": "F23_barrier"})
        t0 = time.monotonic_ns()
        ret, err = ctx.unsubscribe([args.symbol], [ft.SubType.QUOTE])
        t1 = time.monotonic_ns()
        return_seq = recorder.next_seq()
        recorder.record_lifecycle(
            event_type="UNSUBSCRIBE_CALL_RETURN", origin="PROVIDER_SDK", quote_context_id=quote_context_id_holder.get("current"),
            raw_ret_code=ret, raw_error_text=str(err) if ret != 0 else None,
            raw_payload={"rep": rep, "call_duration_ns": t1 - t0},
        )
        post_sub = query_sub(ctx, f"f22_rep{rep}_post")
        time.sleep(6)
        events_after = [
            e for e in recorder.read_lifecycle()
            if e["local_event_seq"] > return_seq and e["event_type"] == "DATA_CALLBACK"
            and e["stream_type"] == "QUOTE" and e["symbol"] == args.symbol
        ]
        f22_results.append({
            "rep": rep, "unsubscribe_ret": ret, "unsubscribe_err": str(err) if ret != 0 else None,
            "immediate_query_subscription_sub_list": post_sub.get("sub_list"),
            "post_return_callback_count": len(events_after),
        })
        print(f"F22/F23 rep {rep}: ret={ret}, post-return callbacks={len(events_after)}, sub_list={post_sub.get('sub_list')}")

    # ---- F21 boundary B: close ctx, new ctx, check push WITHOUT calling subscribe() ----
    do_subscribe(ctx, [args.symbol], subtypes, "before_boundary_b")
    time.sleep(3)
    close_ctx(ctx, "boundary_B_close")
    time.sleep(2)
    ctx2 = new_ctx("boundary_b")
    boundary_b_pre_query = query_sub(ctx2, "boundary_b_new_context_no_subscribe_yet")
    ctx2.set_handler(make_recording_quote_handler(recorder, quote_context_id_holder, "HK"))
    ctx2.set_handler(make_recording_kline_handler(recorder, quote_context_id_holder, "K_1M"))
    seq_before_wait = recorder.next_seq()
    time.sleep(10)
    unsolicited_events = [
        e for e in recorder.read_lifecycle()
        if e["local_event_seq"] > seq_before_wait and e["event_type"] == "DATA_CALLBACK" and e["symbol"] == args.symbol
    ]
    print(f"F21 boundary B: sub_list on new context before any subscribe() = {boundary_b_pre_query.get('sub_list')}; "
          f"unsolicited callbacks in 10s without subscribe() = {len(unsolicited_events)}")

    # Restore working state for F17.
    do_subscribe(ctx2, [args.symbol], subtypes, "restore_after_boundary_b")
    ctx = ctx2

    # ---- F34: safe failure shapes ----
    f34_results = []
    closed_probe_ctx = new_ctx("f34_closed_probe")
    close_ctx(closed_probe_ctx, "f34_closed_probe_close")
    time.sleep(1)
    try:
        ret, data = closed_probe_ctx.query_subscription(is_all_conn=True)
        f34_results.append({"case": "query_subscription_on_closed_context", "ret": ret, "data_repr": repr(data)[:300], "exception": None})
    except Exception as exc:
        f34_results.append({"case": "query_subscription_on_closed_context", "ret": None, "data_repr": None, "exception": f"{type(exc).__name__}: {exc}"})

    # IMPORTANT (found empirically, see Wave 2 Closure report): the SDK's
    # synchronous OpenQuoteContext.__init__ retries _init_connect_sync()
    # forever (sleep(_reconnect_interval)=6s between attempts) whenever
    # _auto_reconnect is True (its hardcoded default) and the target is
    # unreachable -- there is no bounded timeout. Calling this in-process
    # against an unreachable port hung the harness itself for ~39 minutes
    # in an earlier run. Isolated in a subprocess with a hard wall-clock
    # timeout so a hang here can never hang the harness again; the timeout
    # itself IS the raw evidence for this failure shape.
    import subprocess as _subprocess

    probe_code = (
        "import futu as ft\n"
        f"ft.OpenQuoteContext(host={args.host!r}, port=65432)\n"
    )
    t0 = time.monotonic_ns()
    try:
        proc = _subprocess.run(
            [sys.executable, "-c", probe_code], capture_output=True, text=True, timeout=15,
        )
        t1 = time.monotonic_ns()
        f34_results.append({
            "case": "connect_to_wrong_port", "outcome": "subprocess_returned",
            "returncode": proc.returncode, "stderr_tail": proc.stderr[-500:], "duration_ns": t1 - t0,
        })
    except _subprocess.TimeoutExpired:
        t1 = time.monotonic_ns()
        f34_results.append({
            "case": "connect_to_wrong_port", "outcome": "TIMEOUT_NO_RETURN_WITHIN_15S",
            "duration_ns": t1 - t0,
            "note": "OpenQuoteContext.__init__ with is_async_connect=False retries _init_connect_sync() "
            "indefinitely (6s between attempts) when _auto_reconnect=True (the SDK default) and the "
            "target is unreachable -- confirmed by direct SDK source inspection AND this empirical hang.",
        })

    recorder.record_lifecycle(event_type="PROVIDER_EVENT", origin="HARNESS", raw_payload={"f34_results": f34_results})
    print("F34 failure shapes:", json.dumps(f34_results, default=str))

    # ---- F17 / F18: interruption cycles via context close+recreate ----
    f17_cycles = []
    for cycle in range(args.f17_cycles):
        pre_klines = [
            e for e in recorder.read_lifecycle()
            if e["event_type"] == "DATA_CALLBACK" and e["stream_type"] == "K_1M" and e["symbol"] == args.symbol
        ]
        pre_fault_last = pre_klines[-1] if pre_klines else None
        recorder.record_lifecycle(
            event_type="FAULT_INJECTION_BEGIN", origin="HARNESS", quote_context_id=quote_context_id_holder.get("current"),
            raw_payload={
                "cycle": cycle, "method": "LEVEL0_context_close_then_recreate",
                "pre_fault_last_time_key": pre_fault_last["raw_payload"].get("time_key") if pre_fault_last else None,
                "pre_fault_last_payload_hash": _payload_hash(pre_fault_last["raw_payload"]) if pre_fault_last else None,
                "outage_seconds_planned": args.f17_outage_seconds,
            },
        )
        outage_start_seq = recorder.next_seq()
        close_ctx(ctx, f"f17_cycle{cycle}_outage")
        time.sleep(args.f17_outage_seconds)
        recorder.record_lifecycle(event_type="FAULT_INJECTION_END", origin="HARNESS", raw_payload={"cycle": cycle})

        ctx = new_ctx(f"f17_cycle{cycle}_recovery")
        recovery_query = query_sub(ctx, f"f17_cycle{cycle}_recovery_pre_subscribe")
        ctx.set_handler(make_recording_quote_handler(recorder, quote_context_id_holder, "HK"))
        ctx.set_handler(make_recording_kline_handler(recorder, quote_context_id_holder, "K_1M"))
        do_subscribe(ctx, [args.symbol], subtypes, f"f17_cycle{cycle}_recovery")

        post_recovery_klines = wait_for_kline_events(recorder, args.symbol, min_count=3, timeout_s=90)
        post_recovery_new = [e for e in post_recovery_klines if e["local_event_seq"] > outage_start_seq]
        first_n = post_recovery_new[:20]
        f17_cycles.append({
            "cycle": cycle,
            "pre_fault_last_time_key": pre_fault_last["raw_payload"].get("time_key") if pre_fault_last else None,
            "recovery_query_subscription_sub_list_before_subscribe_call": recovery_query.get("sub_list"),
            "post_recovery_event_count": len(post_recovery_new),
            "first_n_post_recovery": [
                {
                    "observed_at_utc": e["observed_at_utc"],
                    "local_event_seq": e["local_event_seq"],
                    "thread_id": e["thread_id"],
                    "time_key": e["raw_payload"].get("time_key"),
                    "payload_hash": _payload_hash(e["raw_payload"]),
                }
                for e in first_n
            ],
        })
        print(f"F17 cycle {cycle}: post-recovery events={len(post_recovery_new)}, "
              f"first time_key(s)={[e['raw_payload'].get('time_key') for e in first_n[:5]]}")

    recorder.write_observations({
        "note": "Full narrative is in the Wave 2 Closure report. See lifecycle.jsonl for complete raw evidence.",
        "f22_f23_results": f22_results,
        "f21_boundary_b": {
            "sub_list_before_subscribe": boundary_b_pre_query.get("sub_list"),
            "unsolicited_callback_count_10s": len(unsolicited_events),
        },
        "f34_results": f34_results,
        "f17_cycles": f17_cycles,
    })

    try:
        ctx.close()
    except Exception:
        pass
    print(f"Done. Raw evidence in: {run_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
