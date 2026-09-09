"""Per-RPC bounded snapshot/history probe for Futu US K_15M / K_60M.

EVIDENCE TOOL ONLY.  This complements ``kline_timestamp_probe.py``.

Every synchronous SDK observation runs in its own child process with its own
hard timeout.  A hung ``OpenQuoteContext``, subscribe, ``get_cur_kline`` or
``request_history_kline`` therefore invalidates only that one observation,
not the entire evidence pack.

The parent writes one immutable JSON file containing raw child outcomes. Child
SDK logs may appear on stdout, so the structured result is emitted on a unique
sentinel-prefixed line and parsed independently from incidental logging.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

HERE = Path(__file__).resolve().parent
STREAM_TYPES = ("K_15M", "K_60M")
SESSION_NAMES = ("RTH", "ETH", "ALL")
ET = ZoneInfo("America/New_York")
RESULT_SENTINEL = "__STOCK_RAZOR_FUTU_EVIDENCE_JSON__="


def _rows_of(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, dict):
        return [dict(value)]
    try:
        return list(value.to_dict(orient="records"))
    except Exception:
        return [{"raw_repr": repr(value)}]


def _emit_result(payload: dict[str, Any]) -> None:
    print(RESULT_SENTINEL + json.dumps(payload, ensure_ascii=False, default=str), flush=True)


def _parse_child_stdout(raw_stdout: str) -> tuple[dict[str, Any] | None, str]:
    """Extract the last sentinel result while preserving unrelated SDK logs."""

    result = None
    noise: list[str] = []
    for line in raw_stdout.splitlines():
        if line.startswith(RESULT_SENTINEL):
            encoded = line[len(RESULT_SENTINEL):]
            try:
                result = json.loads(encoded)
            except json.JSONDecodeError:
                result = {"status": "MALFORMED_CHILD_RESULT", "raw_result_line": encoded}
        elif line.strip():
            noise.append(line)
    return result, "\n".join(noise)


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


def _child_operation(args: argparse.Namespace) -> int:
    try:
        import futu as ft
    except Exception as exc:
        _emit_result({
            "status": "IMPORT_ERROR",
            "error": f"{type(exc).__name__}: {exc}",
        })
        return 3

    observed_at = datetime.now(timezone.utc).isoformat(timespec="microseconds")
    local_trade_date = datetime.now(ET).strftime("%Y-%m-%d")
    ctx = None
    started = time.monotonic()
    try:
        ctx = ft.OpenQuoteContext(host=args.host, port=args.port)
        opend_version = None
        raw_global_state = None
        try:
            ret_state, state = ctx.get_global_state()
            raw_global_state = _rows_of(state) if ret_state == ft.RET_OK else str(state)
            if isinstance(raw_global_state, list) and raw_global_state:
                first = raw_global_state[0]
                if isinstance(first, dict):
                    opend_version = first.get("server_ver")
        except Exception as exc:
            raw_global_state = f"{type(exc).__name__}: {exc}"

        ktype = _ktype_value(ft, args.ktype)
        session = _session_value(ft, args.session)

        if args.operation == "history":
            result = ctx.request_history_kline(
                args.symbol,
                start=local_trade_date,
                end=local_trade_date,
                ktype=ktype,
                autype=ft.AuType.NONE,
                max_count=1000,
                session=session,
            )
            ret_code = result[0] if isinstance(result, tuple) and result else None
            payload = result[1] if isinstance(result, tuple) and len(result) > 1 else result
        elif args.operation == "current":
            sub_ret, sub_payload = ctx.subscribe(
                [args.symbol],
                [ktype],
                session=session,
            )
            if sub_ret != ft.RET_OK:
                _emit_result({
                    "status": "SUBSCRIBE_ERROR",
                    "observed_at_utc": observed_at,
                    "operation": args.operation,
                    "ktype": args.ktype,
                    "session": args.session,
                    "symbol": args.symbol,
                    "raw_subscribe_response": _rows_of(sub_payload) if hasattr(sub_payload, "to_dict") else str(sub_payload),
                    "duration_seconds": time.monotonic() - started,
                })
                return 4
            ret_code, payload = ctx.get_cur_kline(
                args.symbol,
                args.num,
                ktype=ktype,
                autype=ft.AuType.NONE,
            )
        else:
            raise RuntimeError(f"unsupported operation {args.operation}")

        _emit_result({
            "status": "OK" if ret_code == ft.RET_OK else "SDK_ERROR",
            "observed_at_utc": observed_at,
            "operation": args.operation,
            "ktype": args.ktype,
            "session": args.session,
            "symbol": args.symbol,
            "us_eastern_trade_date": local_trade_date,
            "futu_sdk_version": str(getattr(ft, "__version__", "unknown")),
            "opend_version": opend_version,
            "raw_global_state": raw_global_state,
            "raw_sdk_ret": ret_code,
            "raw_rows": _rows_of(payload) if hasattr(payload, "to_dict") or isinstance(payload, dict) else payload,
            "duration_seconds": time.monotonic() - started,
            "semantic_adjudication": "NOT_PERFORMED_BY_CAPTURE_TOOL",
        })
        return 0 if ret_code == ft.RET_OK else 5
    except Exception as exc:
        _emit_result({
            "status": "EXCEPTION",
            "observed_at_utc": observed_at,
            "operation": args.operation,
            "ktype": args.ktype,
            "session": args.session,
            "symbol": args.symbol,
            "error": f"{type(exc).__name__}: {exc}",
            "duration_seconds": time.monotonic() - started,
        })
        return 6
    finally:
        if ctx is not None:
            try:
                ctx.close()
            except Exception:
                pass


def _run_one_child(args: argparse.Namespace, operation: str, ktype: str) -> dict[str, Any]:
    command = [
        sys.executable,
        str(Path(__file__).resolve()),
        "--_child",
        "--operation",
        operation,
        "--ktype",
        ktype,
        "--host",
        args.host,
        "--port",
        str(args.port),
        "--symbol",
        args.symbol,
        "--session",
        args.session,
        "--num",
        str(args.num),
    ]
    started = time.monotonic()
    try:
        proc = subprocess.run(command, capture_output=True, text=True, timeout=args.rpc_timeout)
        child_result, stdout_noise = _parse_child_stdout(proc.stdout)
        return {
            "completed": True,
            "timed_out": False,
            "returncode": proc.returncode,
            "parent_duration_seconds": time.monotonic() - started,
            "child_result": child_result,
            "stdout_noise": stdout_noise,
            "stderr": proc.stderr,
        }
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout.decode("utf-8", "replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        child_result, stdout_noise = _parse_child_stdout(stdout)
        stderr = exc.stderr.decode("utf-8", "replace") if isinstance(exc.stderr, bytes) else (exc.stderr or "")
        return {
            "completed": False,
            "timed_out": True,
            "returncode": None,
            "parent_duration_seconds": time.monotonic() - started,
            "partial_child_result": child_result,
            "stdout_noise": stdout_noise,
            "stderr": stderr,
            "governance": "THIS_OBSERVATION_IS_INCOMPLETE_DO_NOT_ADJUDICATE",
        }


def _parent_run(args: argparse.Namespace) -> int:
    Path(args.output_dir).mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S-%fZ")
    output_path = Path(args.output_dir) / f"kline_snapshot_{stamp}.json"
    if output_path.exists():
        raise FileExistsError(output_path)

    observations: list[dict[str, Any]] = []
    for repetition in range(args.repeat):
        for operation in ("history", "current"):
            for ktype in STREAM_TYPES:
                observations.append({
                    "repetition": repetition + 1,
                    "requested_operation": operation,
                    "requested_ktype": ktype,
                    "result": _run_one_child(args, operation, ktype),
                })
        if repetition + 1 < args.repeat and args.repeat_delay > 0:
            time.sleep(args.repeat_delay)

    document = {
        "probe": "futu_us_k15_k60_snapshot_history_semantics",
        "created_at_utc": datetime.now(timezone.utc).isoformat(timespec="microseconds"),
        "symbol": args.symbol,
        "session": args.session,
        "repeat": args.repeat,
        "repeat_delay_seconds": args.repeat_delay,
        "rpc_timeout_seconds": args.rpc_timeout,
        "timezone_rule": "same-day history uses America/New_York trade date",
        "semantic_adjudication": "NOT_PERFORMED_BY_CAPTURE_TOOL",
        "observations": observations,
    }
    output_path.write_text(json.dumps(document, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(str(output_path))
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Per-RPC bounded Futu K15/K60 snapshot/history probe")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=11111)
    parser.add_argument("--symbol", default="US.AAPL")
    parser.add_argument("--session", choices=SESSION_NAMES, default="RTH")
    parser.add_argument("--repeat", type=int, default=3)
    parser.add_argument("--repeat-delay", type=int, default=120)
    parser.add_argument("--rpc-timeout", type=float, default=30.0)
    parser.add_argument("--num", type=int, default=20)
    parser.add_argument("--output-dir", default=str(HERE / "runs"))
    parser.add_argument("--operation", choices=("history", "current"), default="history", help=argparse.SUPPRESS)
    parser.add_argument("--ktype", choices=STREAM_TYPES, default="K_15M", help=argparse.SUPPRESS)
    parser.add_argument("--_child", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.repeat <= 0:
        parser.error("--repeat must be positive")
    if args.repeat_delay < 0:
        parser.error("--repeat-delay must be >= 0")
    if args.rpc_timeout <= 0:
        parser.error("--rpc-timeout must be positive")
    if args.num <= 0:
        parser.error("--num must be positive")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    return _child_operation(args) if args._child else _parent_run(args)


if __name__ == "__main__":
    raise SystemExit(main())
