"""Bounded empirical probe for Futu US K_15M / K_60M timestamp semantics.

EVIDENCE TOOL ONLY -- never imported by production code.

Purpose
-------
Close the P0 provider-semantics gaps documented in
``FUTU_KLINE_TIMESTAMP_SEMANTICS_REPORT_2026_09_09.md`` using controlled,
read-only observation against a locally running OpenD gateway.

The parent process owns a hard wall-clock deadline.  All Futu SDK work lives
inside one child Python process.  If SDK construction or any synchronous quote
call hangs, the parent kills that one child rather than allowing the evidence
run to hang indefinitely.

The probe deliberately records raw provider rows and capture timing.  It does
NOT decide that a timestamp is start/end, that a bar is complete, or that a
particular currentness threshold is correct.  Those are post-hoc adjudication
questions.

Example -- US regular session, enough time to cross several 15m boundaries::

    python kline_timestamp_probe.py \
        --symbol US.AAPL --session RTH --duration 4200 \
        --host 127.0.0.1 --port 11111

For extended-hours comparison use a separate run::

    python kline_timestamp_probe.py \
        --symbol US.AAPL --session ALL --duration 1800

No orders, account calls, trading-state mutation, entitlement purchase, or
production adapter calls are made.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from recorder import (  # noqa: E402
    EvidenceRecorder,
    build_run_metadata,
    new_run_dir,
)


STREAM_TYPES = ("K_15M", "K_60M")
SESSION_NAMES = ("RTH", "ETH", "ALL")


def _rows_of(data: Any) -> list[dict[str, Any]]:
    try:
        return list(data.to_dict(orient="records"))
    except Exception:
        return [{"raw_repr": repr(data)}]


def _probe_hash() -> str:
    digest = hashlib.sha256()
    for path in (HERE / "kline_timestamp_probe.py", HERE / "recorder.py", HERE / "models.py"):
        if path.exists():
            digest.update(path.read_bytes())
    return digest.hexdigest()


def _session_value(ft, name: str):
    value = getattr(ft.Session, name, None)
    if value is None:
        raise RuntimeError(f"installed futu SDK does not expose Session.{name}")
    return value


def _ktype_value(ft, name: str):
    value = getattr(ft.KLType, name, None)
    if value is None:
        # Some SDK surfaces historically exposed these on SubType as well.
        value = getattr(ft.SubType, name, None)
    if value is None:
        raise RuntimeError(f"installed futu SDK does not expose {name}")
    return value


def _call_and_record(recorder: EvidenceRecorder, label: str, fn, *args, **kwargs):
    started = time.monotonic_ns()
    try:
        result = fn(*args, **kwargs)
        duration_ns = time.monotonic_ns() - started
        if isinstance(result, tuple):
            response = []
            for value in result:
                response.append(_rows_of(value) if hasattr(value, "to_dict") else value)
            ret = result[0] if result else None
        else:
            response = result
            ret = None
        recorder.record_sdk_call(
            call=label,
            args_repr=f"args={args!r} kwargs={kwargs!r}",
            raw_sdk_ret=ret,
            raw_response=response,
            duration_ns=duration_ns,
        )
        return result
    except Exception as exc:  # exception is evidence; child remains bounded by parent.
        recorder.record_sdk_call(
            call=label,
            args_repr=f"args={args!r} kwargs={kwargs!r}",
            raw_sdk_ret="EXCEPTION",
            raw_response=f"{type(exc).__name__}: {exc}",
            duration_ns=time.monotonic_ns() - started,
        )
        return None


def _make_kline_handler(ft, recorder: EvidenceRecorder):
    class _Handler(ft.CurKlineHandlerBase):
        def on_recv_rsp(self, rsp_pb):
            ret_code, data = super().on_recv_rsp(rsp_pb)
            if ret_code != ft.RET_OK:
                recorder.record_event(
                    provider="futu",
                    market="US",
                    symbol=None,
                    stream_type="KLINE",
                    event_type="push_error",
                    raw_sdk_ret=ret_code,
                    raw_sdk_err_text=str(data),
                    raw_payload=None,
                )
                return ft.RET_ERROR, data

            for row in _rows_of(data):
                raw_ktype = row.get("k_type")
                stream_type = str(raw_ktype or "KLINE")
                recorder.record_event(
                    provider="futu",
                    market="US",
                    symbol=row.get("code"),
                    stream_type=stream_type,
                    event_type="push",
                    raw_sdk_ret=ret_code,
                    raw_sdk_err_text=None,
                    raw_payload=row,
                )
            return ft.RET_OK, data

    return _Handler()


def _snapshot_current(recorder: EvidenceRecorder, ctx, ft, symbol: str, label: str) -> None:
    for stream in STREAM_TYPES:
        _call_and_record(
            recorder,
            f"get_cur_kline[{label}:{stream}]",
            ctx.get_cur_kline,
            symbol,
            20,
            ktype=_ktype_value(ft, stream),
            autype=ft.AuType.NONE,
        )


def _snapshot_history(
    recorder: EvidenceRecorder,
    ctx,
    ft,
    symbol: str,
    session_name: str,
    label: str,
) -> None:
    # Historical API accepts dates, not intraday endpoints.  Same-day snapshots
    # are repeated at probe start/end so a forming-row mutation can be observed
    # without interpreting it in the recorder.
    today_et = datetime.now().astimezone().strftime("%Y-%m-%d")
    session = _session_value(ft, session_name)
    for stream in STREAM_TYPES:
        _call_and_record(
            recorder,
            f"request_history_kline[{label}:{session_name}:{stream}]",
            ctx.request_history_kline,
            symbol,
            start=today_et,
            end=today_et,
            ktype=_ktype_value(ft, stream),
            autype=ft.AuType.NONE,
            max_count=1000,
            session=session,
        )


def _child_run(args: argparse.Namespace) -> int:
    try:
        import futu as ft
    except Exception as exc:
        print(f"FUTU_IMPORT_ERROR {type(exc).__name__}: {exc}", file=sys.stderr)
        return 3

    run_dir = Path(args.run_dir)
    recorder = EvidenceRecorder(run_dir)
    ctx = None
    exit_code = 0
    try:
        ctx = ft.OpenQuoteContext(host=args.host, port=args.port)
        global_state = _call_and_record(recorder, "get_global_state", ctx.get_global_state)
        raw_global = None
        opend_version = None
        if isinstance(global_state, tuple) and len(global_state) >= 2:
            raw = global_state[1]
            rows = _rows_of(raw)
            raw_global = rows[0] if rows else None
            if isinstance(raw_global, dict):
                opend_version = str(raw_global.get("server_ver") or "") or None

        recorder.write_metadata(
            {
                **build_run_metadata(
                    host=args.host,
                    port=args.port,
                    futu_sdk_version=str(getattr(ft, "__version__", "unknown")),
                    opend_version=opend_version,
                    opend_raw_global_state=raw_global,
                    harness_version_hash=_probe_hash(),
                ),
                "probe": "futu_us_k15_k60_timestamp_semantics",
                "symbol": args.symbol,
                "session": args.session,
                "duration_seconds": args.duration,
                "requested_stream_types": list(STREAM_TYPES),
                "interpretation_policy": (
                    "raw evidence only; no start/end/completion/currentness inference in recorder"
                ),
            }
        )

        ctx.set_handler(_make_kline_handler(ft, recorder))
        session = _session_value(ft, args.session)
        subtypes = [_ktype_value(ft, name) for name in STREAM_TYPES]

        # Pre-subscription historical snapshot is intentionally taken before
        # live push begins.  A later snapshot can show whether the same
        # time_key row mutated while the market was active.
        _snapshot_history(recorder, ctx, ft, args.symbol, args.session, "before_subscribe")

        subscribe_result = _call_and_record(
            recorder,
            f"subscribe[{args.session}:K_15M+K_60M]",
            ctx.subscribe,
            [args.symbol],
            subtypes,
            session=session,
        )
        if not (isinstance(subscribe_result, tuple) and subscribe_result and subscribe_result[0] == ft.RET_OK):
            exit_code = 4
        else:
            _snapshot_current(recorder, ctx, ft, args.symbol, "after_subscribe")
            deadline = time.monotonic() + args.duration
            next_snapshot = time.monotonic() + args.snapshot_interval
            while time.monotonic() < deadline:
                remaining = max(0.0, deadline - time.monotonic())
                time.sleep(min(1.0, remaining))
                if args.snapshot_interval > 0 and time.monotonic() >= next_snapshot:
                    _snapshot_current(recorder, ctx, ft, args.symbol, "periodic")
                    next_snapshot += args.snapshot_interval

            _snapshot_current(recorder, ctx, ft, args.symbol, "before_close")
            _snapshot_history(recorder, ctx, ft, args.symbol, args.session, "after_capture")

        # Persist only mechanical counts; semantic classification happens in
        # the offline analyzer / review report.
        events = recorder.read_events()
        recorder.write_observations(
            {
                "event_count": len(events),
                "push_counts_by_stream_type": {
                    stream: sum(1 for event in events if event.get("stream_type") == stream)
                    for stream in STREAM_TYPES
                },
                "semantic_adjudication": "NOT_PERFORMED_BY_CAPTURE_TOOL",
            }
        )
    except Exception as exc:
        print(f"PROBE_CHILD_ERROR {type(exc).__name__}: {exc}", file=sys.stderr)
        exit_code = 5
    finally:
        if ctx is not None:
            try:
                ctx.close()
            except Exception:
                pass
    return exit_code


def _parent_run(args: argparse.Namespace) -> int:
    base = Path(args.output_dir)
    run_dir = new_run_dir(base)
    # new_run_dir returns a unique *path*; EvidenceRecorder in the child owns
    # creation of the directory so the append-only invariant remains intact.
    child_argv = [
        sys.executable,
        str(Path(__file__).resolve()),
        "--_child",
        "--run-dir",
        str(run_dir),
        "--host",
        args.host,
        "--port",
        str(args.port),
        "--symbol",
        args.symbol,
        "--session",
        args.session,
        "--duration",
        str(args.duration),
        "--snapshot-interval",
        str(args.snapshot_interval),
        "--output-dir",
        str(base),
    ]
    timeout = args.duration + args.hard_timeout_grace
    started = time.monotonic()
    try:
        completed = subprocess.run(child_argv, capture_output=True, text=True, timeout=timeout)
        print(
            json.dumps(
                {
                    "run_dir": str(run_dir),
                    "completed": True,
                    "timed_out": False,
                    "returncode": completed.returncode,
                    "duration_seconds": round(time.monotonic() - started, 3),
                    "stdout": completed.stdout,
                    "stderr": completed.stderr,
                },
                ensure_ascii=False,
            )
        )
        return completed.returncode
    except subprocess.TimeoutExpired as exc:
        print(
            json.dumps(
                {
                    "run_dir": str(run_dir),
                    "completed": False,
                    "timed_out": True,
                    "returncode": None,
                    "duration_seconds": round(time.monotonic() - started, 3),
                    "stdout": exc.stdout or "",
                    "stderr": exc.stderr or "",
                    "governance": "run is incomplete evidence; do not adjudicate semantic facts from it",
                },
                ensure_ascii=False,
            )
        )
        return 124


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Bounded Futu US K15/K60 timestamp-semantics probe")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=11111)
    parser.add_argument("--symbol", default="US.AAPL")
    parser.add_argument("--session", choices=SESSION_NAMES, default="RTH")
    parser.add_argument("--duration", type=int, default=4200)
    parser.add_argument("--snapshot-interval", type=int, default=300)
    parser.add_argument("--hard-timeout-grace", type=int, default=180)
    parser.add_argument("--output-dir", default=str(HERE / "runs"))
    parser.add_argument("--run-dir", default=None, help=argparse.SUPPRESS)
    parser.add_argument("--_child", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.duration <= 0:
        parser.error("--duration must be positive")
    if args.snapshot_interval < 0:
        parser.error("--snapshot-interval must be >= 0")
    if args.hard_timeout_grace <= 0:
        parser.error("--hard-timeout-grace must be positive")
    if args._child and not args.run_dir:
        parser.error("internal child mode requires --run-dir")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args._child:
        return _child_run(args)
    return _parent_run(args)


if __name__ == "__main__":
    raise SystemExit(main())
