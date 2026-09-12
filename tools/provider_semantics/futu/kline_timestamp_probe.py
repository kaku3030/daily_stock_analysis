"""Bounded live-callback probe for Futu US K_15M / K_60M semantics.

EVIDENCE TOOL ONLY -- never imported by production code.

This probe intentionally does only one thing: subscribe to US K_15M/K_60M
and record raw callbacks across interval transitions.  Synchronous
``get_cur_kline`` / ``request_history_kline`` calls live in a separate probe
so an SDK RPC hang cannot destroy a long live-callback capture.

The parent process owns a hard wall-clock deadline and the child owns the
Futu ``OpenQuoteContext``.  If context construction or subscription hangs,
the parent terminates the child through ``subprocess.run(..., timeout=...)``.

No semantic interpretation is performed while recording: ``time_key`` is
stored exactly as supplied by Futu; the tool never labels it bar-start,
bar-end, completed, current, stale, replay, or live-qualified.

Example -- regular session, long enough to cross several 15m boundaries::

    python kline_timestamp_probe.py \
        --symbol US.AAPL --session RTH --duration 4200

Extended-hours comparison must be a separate run::

    python kline_timestamp_probe.py \
        --symbol US.AAPL --session ALL --duration 1800
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from recorder import EvidenceRecorder, build_run_metadata, new_run_dir  # noqa: E402

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
            response = [
                _rows_of(value) if hasattr(value, "to_dict") else value
                for value in result
            ]
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
    except Exception as exc:
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
                stream_type = str(row.get("k_type") or "KLINE")
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


def _child_run(args: argparse.Namespace) -> int:
    try:
        import futu as ft
    except Exception as exc:
        print(f"FUTU_IMPORT_ERROR {type(exc).__name__}: {exc}", file=sys.stderr)
        return 3

    recorder = EvidenceRecorder(Path(args.run_dir))
    ctx = None
    try:
        ctx = ft.OpenQuoteContext(host=args.host, port=args.port)
        global_state = _call_and_record(recorder, "get_global_state", ctx.get_global_state)
        raw_global = None
        opend_version = None
        if isinstance(global_state, tuple) and len(global_state) >= 2:
            rows = _rows_of(global_state[1])
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
                "probe": "futu_us_k15_k60_live_timestamp_semantics",
                "symbol": args.symbol,
                "session": args.session,
                "duration_seconds": args.duration,
                "requested_stream_types": list(STREAM_TYPES),
                "interpretation_policy": "RAW_CALLBACK_EVIDENCE_ONLY",
            }
        )

        ctx.set_handler(_make_kline_handler(ft, recorder))
        subtypes = [_ktype_value(ft, name) for name in STREAM_TYPES]
        result = _call_and_record(
            recorder,
            f"subscribe[{args.session}:K_15M+K_60M]",
            ctx.subscribe,
            [args.symbol],
            subtypes,
            session=_session_value(ft, args.session),
        )
        if not (isinstance(result, tuple) and result and result[0] == ft.RET_OK):
            return 4

        deadline = time.monotonic() + args.duration
        while time.monotonic() < deadline:
            time.sleep(min(1.0, max(0.0, deadline - time.monotonic())))

        events = recorder.read_events()
        recorder.write_observations(
            {
                "event_count": len(events),
                "push_counts_by_stream_type": {
                    stream: sum(1 for event in events if event.get("stream_type") == stream)
                    for stream in STREAM_TYPES
                },
                "distinct_time_keys_by_stream_type": {
                    stream: sorted(
                        {
                            str((event.get("raw_payload") or {}).get("time_key"))
                            for event in events
                            if event.get("stream_type") == stream
                            and (event.get("raw_payload") or {}).get("time_key") is not None
                        }
                    )
                    for stream in STREAM_TYPES
                },
                "semantic_adjudication": "NOT_PERFORMED_BY_CAPTURE_TOOL",
            }
        )
        return 0
    except Exception as exc:
        print(f"PROBE_CHILD_ERROR {type(exc).__name__}: {exc}", file=sys.stderr)
        return 5
    finally:
        if ctx is not None:
            try:
                ctx.close()
            except Exception:
                pass


def _parent_run(args: argparse.Namespace) -> int:
    base = Path(args.output_dir)
    run_dir = new_run_dir(base)
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
        "--output-dir",
        str(base),
    ]
    timeout = args.duration + args.hard_timeout_grace
    started = time.monotonic()
    try:
        completed = subprocess.run(child_argv, capture_output=True, text=True, timeout=timeout)
        print(json.dumps({
            "run_dir": str(run_dir),
            "completed": True,
            "timed_out": False,
            "returncode": completed.returncode,
            "duration_seconds": round(time.monotonic() - started, 3),
            "stdout": completed.stdout,
            "stderr": completed.stderr,
        }, ensure_ascii=False))
        return completed.returncode
    except subprocess.TimeoutExpired as exc:
        print(json.dumps({
            "run_dir": str(run_dir),
            "completed": False,
            "timed_out": True,
            "returncode": None,
            "duration_seconds": round(time.monotonic() - started, 3),
            "stdout": exc.stdout or "",
            "stderr": exc.stderr or "",
            "governance": "INCOMPLETE_EVIDENCE_DO_NOT_ADJUDICATE",
        }, ensure_ascii=False))
        return 124


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Bounded Futu US K15/K60 live timestamp-semantics probe")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=11111)
    parser.add_argument("--symbol", default="US.AAPL")
    parser.add_argument("--session", choices=SESSION_NAMES, default="RTH")
    parser.add_argument("--duration", type=int, default=4200)
    parser.add_argument("--hard-timeout-grace", type=int, default=180)
    parser.add_argument("--output-dir", default=str(HERE / "runs"))
    parser.add_argument("--run-dir", default=None, help=argparse.SUPPRESS)
    parser.add_argument("--_child", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.duration <= 0:
        parser.error("--duration must be positive")
    if args.hard_timeout_grace <= 0:
        parser.error("--hard-timeout-grace must be positive")
    if args._child and not args.run_dir:
        parser.error("internal child mode requires --run-dir")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    return _child_run(args) if args._child else _parent_run(args)


if __name__ == "__main__":
    raise SystemExit(main())
