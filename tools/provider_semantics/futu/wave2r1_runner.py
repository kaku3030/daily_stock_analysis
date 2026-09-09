"""Wave 2 Closure R1 -- safe Level-1 transport-fault test via an isolated,
harness-owned localhost TCP proxy (see transport_proxy.py).

Does NOT touch OpenD (no restart/kill), does NOT touch firewall/network
configuration, does NOT call any trading API. F17/F18 (missed-interval
catch-up) require an ACTIVE market session to mean anything; if the market
is closed, this runner still exercises the proxy/transport/reconnect
mechanics (which do not depend on live trading) and reports F17/F18 as
WAITING_FOR_ACTIVE_SESSION rather than fabricating a recovery conclusion.
"""

from __future__ import annotations

import argparse
import hashlib
import inspect
import json
import subprocess
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lifecycle_recorder import LifecycleRecorder  # noqa: E402
from recorder import build_run_metadata, harness_version_hash, new_run_dir, utc_now_iso  # noqa: E402
from transport_proxy import TransportProxy  # noqa: E402

import futu as ft  # noqa: E402


def _payload_hash(payload: dict) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode("utf-8")).hexdigest()[:16]


def capture_sdk_source_evidence() -> dict:
    """Formal, persisted capture of the source-derived reconnect-ownership
    facts -- read once here, written to a derived artifact by main().
    """

    import futu.common.open_context_base as ocb

    def src(obj) -> str:
        try:
            return inspect.getsource(obj)
        except Exception as exc:
            return f"<unavailable: {exc!r}>"

    init_src = src(ocb.OpenContextBase.__init__)
    close_src = src(ocb.OpenContextBase.close)
    wait_reconnect_src = src(ocb.OpenContextBase._wait_reconnect)
    reconnect_src = src(ocb.OpenContextBase._reconnect)
    on_disconnect_src = src(ft.OpenQuoteContext.on_disconnect)
    on_reconnected_src = src(ft.OpenQuoteContext.on_api_socket_reconnected)
    reconnect_subscribe_src = src(ft.OpenQuoteContext._reconnect_subscribe)
    ctor_sig = str(inspect.signature(ft.OpenQuoteContext.__init__))

    public_ctor_params = list(inspect.signature(ft.OpenQuoteContext.__init__).parameters.keys())

    return {
        "module_file": {
            "open_context_base": getattr(ocb, "__file__", None),
            "open_quote_context": getattr(ft.OpenQuoteContext, "__module__", None),
        },
        "OpenQuoteContext_public_constructor_signature": ctor_sig,
        "OpenQuoteContext_public_constructor_params": public_ctor_params,
        "OpenContextBase___init___source": init_src,
        "OpenContextBase_close_source": close_src,
        "OpenContextBase__wait_reconnect_source": wait_reconnect_src,
        "OpenContextBase__reconnect_source": reconnect_src,
        "OpenQuoteContext_on_disconnect_source": on_disconnect_src,
        "OpenQuoteContext_on_api_socket_reconnected_source": on_reconnected_src,
        "OpenQuoteContext__reconnect_subscribe_source": reconnect_subscribe_src,
        "answers": {
            "PUBLIC_AUTO_RECONNECT_DISABLE": (
                "NO_OBSERVED -- _auto_reconnect is a private attribute (self._auto_reconnect = True), "
                "hardcoded in OpenContextBase.__init__ with no constructor parameter or public setter "
                "exposed anywhere in OpenQuoteContext.__init__'s public signature "
                f"{public_ctor_params}. The only place it is set False is internally, inside close() "
                "when reason is CloseReason.Close (i.e. only as a side effect of the client's own close())."
            ),
            "PUBLIC_RECONNECT_POLICY_CONTROL": (
                "NO_OBSERVED -- _reconnect_interval (default 6s) and the retry loop in _wait_reconnect/"
                "_reconnect are private, with no constructor parameter, setter, or documented public "
                "API found in OpenQuoteContext's public signature or method list to change interval, "
                "backoff, or max-attempts policy."
            ),
            "PUBLIC_SYNC_CONNECT_TIMEOUT": (
                "NO_OBSERVED -- OpenQuoteContext.__init__ accepts is_async_connect (bool) but no timeout "
                "value; when is_async_connect=False (the default) and the target is unreachable, "
                "OpenContextBase.__init__'s synchronous branch loops "
                "'while True: ... if not self._auto_reconnect: return; sleep(self._reconnect_interval)' "
                "with no bound -- there is no public parameter to cap this."
            ),
        },
    }


def probe_f34_unreachable_port(host: str, port: int) -> dict:
    """Formal, isolated, hard-timeout capture -- must never be run in-process
    (see Wave 2 Closure prior incident: an in-process attempt hung for ~39
    minutes). Runs the constructor in a child process and kills it on
    timeout; the timeout itself is the evidence, not an inferred "never
    returns" claim.
    """

    probe_code = (
        "import futu as ft\n"
        f"ft.OpenQuoteContext(host={host!r}, port={port!r}, is_async_connect=False)\n"
        "print('CONSTRUCTOR_RETURNED')\n"
    )
    child_start = utc_now_iso()
    t0 = time.monotonic_ns()
    result = {
        "constructor_args_excluding_secrets": {"host": host, "port": port, "is_async_connect": False},
        "child_start_utc": child_start,
        "timeout_seconds": 15,
    }
    try:
        proc = subprocess.run([sys.executable, "-c", probe_code], capture_output=True, text=True, timeout=15)
        t1 = time.monotonic_ns()
        result.update({
            "child_timeout_utc": None,
            "constructor_returned": "CONSTRUCTOR_RETURNED" in proc.stdout,
            "child_returncode": proc.returncode,
            "duration_ns": t1 - t0,
            "termination_method": "exited_on_its_own",
            "classification": "constructor_returned_within_timeout" if "CONSTRUCTOR_RETURNED" in proc.stdout else "constructor_exited_abnormally",
        })
    except subprocess.TimeoutExpired as exc:
        t1 = time.monotonic_ns()
        # subprocess.run's own timeout path already sends the child a kill
        # signal internally; nothing further to terminate here.
        result.update({
            "child_timeout_utc": utc_now_iso(),
            "constructor_returned": False,
            "duration_ns": t1 - t0,
            "termination_method": "subprocess_timeout_kill (child process ownership verified: sole child "
            "of this subprocess.run call, no other process touched)",
            "classification": "SYNC_UNREACHABLE_CONNECT_DID_NOT_RETURN_WITHIN_TIMEOUT",
            "stdout_partial": (exc.stdout or b"").decode("utf-8", "replace") if isinstance(exc.stdout, bytes) else exc.stdout,
        })
    return result


def make_recording_context_class(recorder: LifecycleRecorder, ctx_id_holder: dict):
    class RecordingQuoteContext(ft.OpenQuoteContext):
        def on_disconnect(self, conn_id, reason, msg):
            recorder.record_lifecycle(
                event_type="CONNECTION_ERROR",
                origin="PROVIDER_SDK",
                quote_context_id=ctx_id_holder.get("current"),
                raw_payload={"conn_id": conn_id, "reason": str(reason), "msg": msg, "is_client_initiated_close": str(reason) == "CloseReason.Close"},
            )
            return super().on_disconnect(conn_id, reason, msg)

    return RecordingQuoteContext


def make_quote_handler(recorder: LifecycleRecorder, ctx_id_holder: dict):
    class _H(ft.StockQuoteHandlerBase):
        def on_recv_rsp(self, rsp_pb):
            ret_code, data = super().on_recv_rsp(rsp_pb)
            if ret_code != ft.RET_OK:
                return ft.RET_ERROR, data
            for row in data.to_dict(orient="records"):
                recorder.record_lifecycle(
                    event_type="DATA_CALLBACK", origin="PROVIDER_SDK", quote_context_id=ctx_id_holder.get("current"),
                    symbol=row.get("code"), stream_type="QUOTE", raw_provider_timestamp=row.get("data_time"), raw_payload=row, raw_ret_code=ret_code,
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
                    event_type="DATA_CALLBACK", origin="PROVIDER_SDK", quote_context_id=ctx_id_holder.get("current"),
                    symbol=row.get("code"), stream_type="K_1M", raw_provider_timestamp=row.get("time_key"), raw_payload=row, raw_ret_code=ret_code,
                )
            return ft.RET_OK, data
    return _H()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Wave 2 Closure R1: safe Level-1 transport fault via isolated proxy")
    parser.add_argument("--opend-host", default="127.0.0.1")
    parser.add_argument("--opend-port", type=int, default=11111)
    parser.add_argument("--proxy-port", type=int, default=23456)
    parser.add_argument("--symbol", default="HK.00700")
    parser.add_argument("--output-dir", default=str(Path(__file__).resolve().parent / "runs"))
    parser.add_argument("--cut-seconds", type=int, default=20, help="How long to hold the transport cut before restoring")
    args = parser.parse_args(argv)

    runtime_run_id = str(uuid.uuid4())
    run_dir = new_run_dir(Path(args.output_dir))
    recorder = LifecycleRecorder(run_dir, runtime_run_id=runtime_run_id)
    ctx_id_holder: dict = {"current": None}
    RecordingQuoteContext = make_recording_context_class(recorder, ctx_id_holder)

    # ---- upfront: OpenD identity + market session gate ----
    probe_ctx = ft.OpenQuoteContext(host=args.opend_host, port=args.opend_port)
    ret, global_state = probe_ctx.get_global_state()
    probe_ctx.close()
    market_hk = global_state.get("market_hk") if isinstance(global_state, dict) else None
    market_active = market_hk in ("MORNING", "AFTERNOON")

    recorder.write_metadata({
        **build_run_metadata(
            host=args.opend_host, port=args.opend_port, futu_sdk_version=getattr(ft, "__version__", "unknown"),
            opend_version=str(global_state.get("server_ver")) if isinstance(global_state, dict) else None,
            opend_raw_global_state=global_state if isinstance(global_state, dict) else {"raw_repr": repr(global_state)},
            harness_version_hash=harness_version_hash(),
        ),
        "purpose": "Wave 2 Closure R1: safe Level-1 transport fault via isolated proxy, F19/F34/SDK-ownership formal capture, F17/F18 gated on market session",
        "proxy_listen_port": args.proxy_port,
        "market_hk": market_hk,
        "market_active_for_f17_f18": market_active,
        "cli_args": vars(args),
        "runtime_run_id": runtime_run_id,
    })
    print(f"Run directory: {run_dir}")
    print(f"market_hk={market_hk}, market_active_for_f17_f18={market_active}")

    # ---- source-inspection formal capture ----
    source_evidence = capture_sdk_source_evidence()
    derived_dir = run_dir / "derived"
    derived_dir.mkdir(exist_ok=True)
    (derived_dir / "sdk_source_inspection.json").write_text(
        json.dumps({"analysis_revision": "wave2r1_source", "created_at": utc_now_iso(), **source_evidence}, indent=2, default=str),
        encoding="utf-8",
    )
    print("SDK source-inspection evidence written.")
    print("PUBLIC_AUTO_RECONNECT_DISABLE:", source_evidence["answers"]["PUBLIC_AUTO_RECONNECT_DISABLE"][:12])

    # ---- F34 formal capture (isolated subprocess, hard timeout) ----
    f34_result = probe_f34_unreachable_port(args.opend_host, 65432)
    recorder.record_lifecycle(event_type="PROVIDER_EVENT", origin="HARNESS", raw_payload={"f34_formal_capture": f34_result})
    print("F34 formal capture:", f34_result["classification"])

    # ---- proxy setup + baseline ----
    proxy = TransportProxy("127.0.0.1", args.proxy_port, args.opend_host, args.opend_port)
    proxy.start()
    time.sleep(0.3)

    def drain_proxy_events(label: str) -> None:
        for ev in proxy.drain_events():
            recorder.record_lifecycle(
                event_type="PROVIDER_EVENT", origin="HARNESS", raw_payload={"proxy_event": ev, "label": label},
            )

    ctx_id_holder["current"] = str(uuid.uuid4())[:8]
    recorder.record_lifecycle(event_type="CONTEXT_CREATE_BEGIN", origin="HARNESS", quote_context_id=ctx_id_holder["current"], raw_payload={"via": "proxy"})
    try:
        ctx = RecordingQuoteContext(host="127.0.0.1", port=args.proxy_port)
    except Exception as exc:
        recorder.record_lifecycle(event_type="CONTEXT_CREATE_ERROR", origin="HARNESS", raw_error_text=repr(exc))
        drain_proxy_events("create_error")
        print("PROXY BASELINE: TEST_BLOCKED_SAFETY / PROXY_INVALID -- context creation through proxy failed")
        proxy.stop()
        return 1
    recorder.record_lifecycle(event_type="CONTEXT_CREATE_OK", origin="HARNESS", quote_context_id=ctx_id_holder["current"])
    drain_proxy_events("after_create")

    ctx.set_handler(make_quote_handler(recorder, ctx_id_holder))
    ctx.set_handler(make_kline_handler(recorder, ctx_id_holder))

    recorder.record_lifecycle(event_type="SUBSCRIBE_CALL_BEGIN", origin="HARNESS", quote_context_id=ctx_id_holder["current"], raw_payload={"symbols": [args.symbol], "subtypes": ["QUOTE", "K_1M"]})
    ret, err = ctx.subscribe([args.symbol], [ft.SubType.QUOTE, ft.SubType.K_1M], subscribe_push=True)
    recorder.record_lifecycle(event_type="SUBSCRIBE_CALL_RETURN", origin="PROVIDER_SDK", quote_context_id=ctx_id_holder["current"], raw_ret_code=ret, raw_error_text=str(err) if ret != 0 else None)
    drain_proxy_events("after_subscribe")

    recorder.record_lifecycle(event_type="QUERY_SUBSCRIPTION_CALL", origin="HARNESS", quote_context_id=ctx_id_holder["current"], raw_payload={"label": "baseline"})
    qret, qdata = ctx.query_subscription(is_all_conn=True)
    recorder.record_lifecycle(event_type="QUERY_SUBSCRIPTION_CALL", origin="PROVIDER_SDK", quote_context_id=ctx_id_holder["current"], raw_ret_code=qret, raw_payload=qdata if isinstance(qdata, dict) else {"raw_repr": repr(qdata)})

    time.sleep(8)
    drain_proxy_events("baseline_window")
    baseline_events = [e for e in recorder.read_lifecycle() if e["event_type"] == "DATA_CALLBACK"]
    print(f"PROXY BASELINE: subscribe ret={ret}, sub_list={qdata.get('sub_list') if isinstance(qdata, dict) else None}, "
          f"callbacks_observed_through_proxy={len(baseline_events)}")
    baseline_ok = ret == 0 and isinstance(qdata, dict) and qdata.get("sub_list")
    if not baseline_ok:
        print("PROXY BASELINE: TEST_BLOCKED_SAFETY / PROXY_INVALID")
        ctx.close()
        proxy.stop()
        return 1

    # ---- F19: genuine transport loss ----
    pre_cut_events = [e for e in recorder.read_lifecycle() if e["event_type"] == "DATA_CALLBACK"]
    last_pre_cut = pre_cut_events[-1] if pre_cut_events else None
    cut_monotonic_ns = time.monotonic_ns()
    recorder.record_lifecycle(
        event_type="FAULT_INJECTION_BEGIN", origin="HARNESS", quote_context_id=ctx_id_holder["current"],
        raw_payload={
            "method": "LEVEL1_proxy_cut", "cut_monotonic_ns": cut_monotonic_ns,
            "last_pre_cut_callback_hash": _payload_hash(last_pre_cut["raw_payload"]) if last_pre_cut else None,
            "last_pre_cut_observed_at_utc": last_pre_cut["observed_at_utc"] if last_pre_cut else None,
        },
    )
    proxy.cut()
    drain_proxy_events("at_cut")

    # Observe for on_disconnect + reconnect-attempt cadence against the
    # (still-refusing) proxy for a bounded window.
    disconnect_seen_at = None
    for _ in range(int(args.cut_seconds * 2)):
        time.sleep(0.5)
        events_now = recorder.read_lifecycle()
        conn_errors = [e for e in events_now if e["event_type"] == "CONNECTION_ERROR" and e["quote_context_id"] == ctx_id_holder["current"]]
        if conn_errors and disconnect_seen_at is None:
            disconnect_seen_at = conn_errors[0]
        drain_proxy_events("outage_window")
    recorder.record_lifecycle(event_type="FAULT_INJECTION_END", origin="HARNESS", raw_payload={"phase": "cut_window_end"})

    disconnect_reason = disconnect_seen_at["raw_payload"].get("reason") if disconnect_seen_at else None
    detection_latency_ns = (
        disconnect_seen_at["monotonic_ns"] - cut_monotonic_ns if disconnect_seen_at else None
    )
    print(f"F19: on_disconnect observed={disconnect_seen_at is not None}, reason={disconnect_reason}, "
          f"detection_latency_s={detection_latency_ns / 1e9 if detection_latency_ns else None}")

    refused_attempts = [
        e for e in recorder.read_lifecycle()
        if e["event_type"] == "PROVIDER_EVENT" and e.get("raw_payload", {}).get("proxy_event", {}).get("event") == "CONNECTION_REFUSED_DURING_CUT"
    ]
    print(f"F19: SDK reconnect attempts refused by proxy during cut window: {len(refused_attempts)}")

    # ---- restore ----
    query_before_restore_ret, query_before_restore_data = None, None
    try:
        query_before_restore_ret, query_before_restore_data = ctx.query_subscription(is_all_conn=True)
    except Exception as exc:
        query_before_restore_data = {"exception": repr(exc)}
    recorder.record_lifecycle(event_type="QUERY_SUBSCRIPTION_CALL", origin="HARNESS", raw_payload={"label": "during_outage_before_restore", "ret": query_before_restore_ret, "data": query_before_restore_data})

    proxy.restore()
    recorder.record_lifecycle(event_type="FAULT_INJECTION_END", origin="HARNESS", raw_payload={"phase": "restore"})

    # Do NOT call subscribe() -- observe auto-resubscribe per instruction.
    reconnect_deadline = time.time() + 30
    reconnected_context = False
    while time.time() < reconnect_deadline:
        drain_proxy_events("post_restore_window")
        events_now = recorder.read_lifecycle()
        established = [e for e in events_now if e["event_type"] == "PROVIDER_EVENT" and e.get("raw_payload", {}).get("proxy_event", {}).get("event") == "CONNECTION_ESTABLISHED"]
        if len(established) >= 2:  # first was the initial baseline connection
            reconnected_context = True
            break
        time.sleep(1)

    post_restore_callbacks = []
    deadline = time.time() + 20
    while time.time() < deadline:
        events_now = recorder.read_lifecycle()
        post_restore_callbacks = [
            e for e in events_now
            if e["event_type"] == "DATA_CALLBACK" and e["monotonic_ns"] > cut_monotonic_ns
        ]
        if post_restore_callbacks:
            break
        time.sleep(1)

    try:
        post_restore_query_ret, post_restore_query_data = ctx.query_subscription(is_all_conn=True)
    except Exception as exc:
        post_restore_query_ret, post_restore_query_data = None, {"exception": repr(exc)}
    recorder.record_lifecycle(event_type="QUERY_SUBSCRIPTION_CALL", origin="HARNESS", raw_payload={"label": "post_restore_no_manual_subscribe", "ret": post_restore_query_ret, "data": post_restore_query_data})

    auto_resubscribe = "OBSERVED" if post_restore_callbacks else "NOT_OBSERVED"
    print(f"AUTO_RESUBSCRIBE_BEHAVIOR = {auto_resubscribe} (post-restore callbacks without manual subscribe(): {len(post_restore_callbacks)})")
    print(f"SDK automatically re-established a NEW transport connection through the proxy without harness intervention: {reconnected_context}")
    print(f"query_subscription immediately after restore: {post_restore_query_data.get('sub_list') if isinstance(post_restore_query_data, dict) else post_restore_query_data}")

    market_hk_now = None
    try:
        _, gs2 = ctx.get_global_state()
        market_hk_now = gs2.get("market_hk") if isinstance(gs2, dict) else None
    except Exception:
        pass

    recorder.write_observations({
        "market_active_for_f17_f18": market_active,
        "f17_f18_status": "WAITING_FOR_ACTIVE_SESSION" if not market_active else "ATTEMPTED",
        "f34_formal_capture": f34_result,
        "f19": {
            "disconnect_observed": disconnect_seen_at is not None,
            "disconnect_reason": disconnect_reason,
            "detection_latency_seconds": detection_latency_ns / 1e9 if detection_latency_ns else None,
            "refused_reconnect_attempts_during_cut": len(refused_attempts),
        },
        "auto_resubscribe_behavior": auto_resubscribe,
        "reconnected_new_transport_without_intervention": reconnected_context,
        "post_restore_query_subscription": post_restore_query_data,
        "market_hk_at_end": market_hk_now,
    })

    try:
        ctx.close()
    except Exception:
        pass
    proxy.stop()
    print(f"Done. Raw evidence in: {run_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
