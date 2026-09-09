"""Wave 1 Closure R1 -- targeted live probes for F04 (corrected) and F06
(clean mixed-batch, no pre-existing subscription contamination).

This is a fresh empirical capture, not a re-analysis of prior raw evidence:
it opens its own new, timestamped run directory via the same
EvidenceRecorder used by wave1_runner.py, so this run's raw files are
independent of -- and do not modify -- any earlier run's raw evidence.

Read-only / market-data only. No trading/account-state APIs are called.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from recorder import EvidenceRecorder, build_run_metadata, harness_version_hash, new_run_dir, utc_now_iso  # noqa: E402
from wave1_runner import call_and_record, make_quote_handler  # noqa: E402

import futu as ft  # noqa: E402


def probe_f04(recorder: EvidenceRecorder, ctx, live_symbol: str) -> None:
    """Corrected get_delay_statistics invocation, plus a second capture after
    a brief live subscription so the call has real push traffic to report on
    (if it ever populates anything at all).
    """

    # Exact SDK method/signature (captured for the record, not guessed):
    #   OpenQuoteContext.get_delay_statistics(self, type_list, qot_push_stage, segment_list)
    #   type_list: list[DelayStatisticsType]  (QOT_PUSH / REQ_REPLY / PLACE_ORDER)
    #   qot_push_stage: QotPushStage
    #   segment_list: list[int]  -- millisecond bucket boundaries, -1 = overflow bucket
    recorder.record_event(
        provider="futu", market=None, symbol=None, stream_type="SDK_INTROSPECTION",
        event_type="signature_capture", raw_payload={
            "method": "OpenQuoteContext.get_delay_statistics",
            "signature": "(self, type_list, qot_push_stage, segment_list)",
            "type_list_enum": "DelayStatisticsType",
            "type_list_enum_members": [m for m in dir(ft.DelayStatisticsType) if not m.startswith("_") and m.isupper()],
            "qot_push_stage_enum": "QotPushStage",
            "qot_push_stage_enum_members": [m for m in dir(ft.QotPushStage) if not m.startswith("_") and m.isupper()],
        },
    )

    call_and_record(
        recorder,
        "get_delay_statistics[cold, type=QOT_PUSH, stage=ALL]",
        ctx.get_delay_statistics,
        type_list=[ft.DelayStatisticsType.QOT_PUSH],
        qot_push_stage=ft.QotPushStage.ALL,
        segment_list=[100, 200, 500, 1000, 2000, -1],
    )
    call_and_record(
        recorder,
        "get_delay_statistics[cold, type=REQ_REPLY, stage=ALL]",
        ctx.get_delay_statistics,
        type_list=[ft.DelayStatisticsType.REQ_REPLY],
        qot_push_stage=ft.QotPushStage.ALL,
        segment_list=[100, 200, 500, 1000, 2000, -1],
    )
    call_and_record(
        recorder,
        "get_delay_statistics[cold, type=ALL_TYPES, stage=ALL]",
        ctx.get_delay_statistics,
        type_list=[ft.DelayStatisticsType.QOT_PUSH, ft.DelayStatisticsType.REQ_REPLY, ft.DelayStatisticsType.PLACE_ORDER],
        qot_push_stage=ft.QotPushStage.ALL,
        segment_list=[100, 200, 500, 1000, 2000, -1],
    )

    ctx.set_handler(make_quote_handler(recorder, "HK"))
    ret, err = ctx.subscribe([live_symbol], [ft.SubType.QUOTE], subscribe_push=True)
    recorder.record_sdk_call(
        call="subscribe[f04_warm_up_for_delay_stats]", args_repr=f"([{live_symbol!r}], [QUOTE])",
        raw_sdk_ret=ret, raw_response=err, duration_ns=0,
    )
    time.sleep(15)

    call_and_record(
        recorder,
        "get_delay_statistics[warm, type=QOT_PUSH, stage=ALL]",
        ctx.get_delay_statistics,
        type_list=[ft.DelayStatisticsType.QOT_PUSH],
        qot_push_stage=ft.QotPushStage.ALL,
        segment_list=[100, 200, 500, 1000, 2000, -1],
    )

    try:
        ctx.unsubscribe([live_symbol], [ft.SubType.QUOTE])
    except Exception as exc:
        recorder.record_sdk_call(call="unsubscribe[f04_cleanup]", args_repr="()", raw_sdk_ret="EXCEPTION", raw_response=repr(exc), duration_ns=0)


def probe_f06_clean_mixed_batch(recorder: EvidenceRecorder, ctx, new_valid_symbol: str, invalid_symbol: str) -> int:
    """Returns the count of QUOTE push events observed for new_valid_symbol
    during the post-call observation window (0 means none observed).
    """

    # PRE-STATE: prove new_valid_symbol is not already subscribed.
    ret, pre_state = ctx.query_subscription(is_all_conn=True)
    recorder.record_sdk_call(
        call="query_subscription[pre_state]", args_repr="(is_all_conn=True)",
        raw_sdk_ret=ret, raw_response=pre_state, duration_ns=0,
    )
    pre_sub_list = pre_state.get("sub_list", {}) if isinstance(pre_state, dict) else {}
    already_subscribed = any(new_valid_symbol in str(k) or new_valid_symbol in str(v) for k, v in pre_sub_list.items())
    recorder.record_event(
        provider="futu", market="HK", symbol=new_valid_symbol, stream_type="F06_CLEAN_TEST",
        event_type="pre_state_check", raw_payload={
            "new_valid_symbol": new_valid_symbol,
            "pre_sub_list": pre_sub_list,
            "already_subscribed_before_mixed_call": already_subscribed,
        },
    )

    # Handler must be set BEFORE the subscribe call so any callback that
    # does arrive (even if the call itself reports failure) is captured.
    ctx.set_handler(make_quote_handler(recorder, "HK"))

    # THE CALL: mixed valid (demonstrably not-yet-subscribed) + invalid.
    call_start_seq_marker = recorder.next_seq()
    ret, err = ctx.subscribe([new_valid_symbol, invalid_symbol], [ft.SubType.QUOTE], subscribe_push=True)
    recorder.record_sdk_call(
        call="subscribe[clean_mixed_valid_invalid]",
        args_repr=f"([{new_valid_symbol!r}, {invalid_symbol!r}], [QUOTE])",
        raw_sdk_ret=ret, raw_response=err, duration_ns=0,
    )

    # POST-STATE: immediately after the call.
    post_ret, post_state = ctx.query_subscription(is_all_conn=True)
    recorder.record_sdk_call(
        call="query_subscription[post_state_immediate]", args_repr="(is_all_conn=True)",
        raw_sdk_ret=post_ret, raw_response=post_state, duration_ns=0,
    )
    post_sub_list = post_state.get("sub_list", {}) if isinstance(post_state, dict) else {}
    now_subscribed = any(new_valid_symbol in str(k) or new_valid_symbol in str(v) for k, v in post_sub_list.items())
    recorder.record_event(
        provider="futu", market="HK", symbol=new_valid_symbol, stream_type="F06_CLEAN_TEST",
        event_type="post_state_check", raw_payload={
            "post_sub_list": post_sub_list,
            "new_valid_symbol_now_subscribed": now_subscribed,
        },
    )

    # CALLBACK EVIDENCE: wait and see whether any push for new_valid_symbol
    # arrives despite the call's own reported result.
    time.sleep(15)
    events = recorder.read_events()
    callback_count = sum(
        1 for e in events
        if e["event_seq_local"] > call_start_seq_marker
        and e["stream_type"] == "QUOTE" and e["event_type"] == "push"
        and e["symbol"] == new_valid_symbol
    )
    recorder.record_event(
        provider="futu", market="HK", symbol=new_valid_symbol, stream_type="F06_CLEAN_TEST",
        event_type="callback_observation_window_result",
        raw_payload={"callback_count_for_new_valid_symbol_after_call": callback_count, "observation_window_seconds": 15},
    )
    return callback_count


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Wave 1 Closure R1 -- F04 corrected probe + F06 clean mixed-batch test")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=11111)
    parser.add_argument("--f04-live-symbol", default="HK.00700")
    parser.add_argument("--f06-new-valid-symbol", default="HK.09988", help="A liquid HK symbol not otherwise used this session")
    parser.add_argument("--f06-invalid-symbol", default="HK.99999999")
    parser.add_argument("--output-dir", default=str(Path(__file__).resolve().parent / "runs"))
    args = parser.parse_args(argv)

    try:
        ctx = ft.OpenQuoteContext(host=args.host, port=args.port)
    except Exception as exc:
        print(f"EXECUTION BLOCKED: could not connect to OpenD at {args.host}:{args.port}: {exc!r}")
        return 2

    try:
        ret, global_state = ctx.get_global_state()
        if ret != ft.RET_OK:
            print(f"EXECUTION BLOCKED: get_global_state failed: {global_state!r}")
            return 2
        opend_version = str(global_state.get("server_ver")) if isinstance(global_state, dict) else None

        run_dir = new_run_dir(Path(args.output_dir))
        recorder = EvidenceRecorder(run_dir)
        metadata = build_run_metadata(
            host=args.host, port=args.port,
            futu_sdk_version=getattr(ft, "__version__", "unknown"),
            opend_version=opend_version,
            opend_raw_global_state=global_state if isinstance(global_state, dict) else {"raw_repr": repr(global_state)},
            harness_version_hash=harness_version_hash(),
        )
        metadata["cli_args"] = vars(args)
        metadata["purpose"] = "Wave 1 Closure R1: F04 corrected get_delay_statistics probe + F06 clean mixed-batch subscribe test"
        recorder.write_metadata(metadata)

        print(f"Run directory: {run_dir}")

        print("--- F04: corrected get_delay_statistics probe ---")
        probe_f04(recorder, ctx, args.f04_live_symbol)

        print("--- F06: clean mixed-batch subscribe test ---")
        callback_count = probe_f06_clean_mixed_batch(recorder, ctx, args.f06_new_valid_symbol, args.f06_invalid_symbol)
        print(f"F06 callback_count for new valid symbol after mixed call: {callback_count}")

        recorder.write_observations({
            "note": "This run's derived observations are minimal; full narrative is in the Closure R1 report. "
                    "See sdk_calls.jsonl and events.jsonl for raw evidence.",
            "f06_callback_count_for_new_valid_symbol": callback_count,
        })

        print(f"Done. Raw evidence in: {run_dir}")
        return 0
    finally:
        try:
            ctx.close()
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
