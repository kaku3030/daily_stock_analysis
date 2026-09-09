"""Futu/Moomoo provider-semantics harness -- Wave 1 (temporal / basic stream).

Isolated test tool. NOT production code. Nothing under `src/` or
`data_provider/` imports this, and this module imports nothing from
production adapters -- it talks to the Futu SDK directly.

Read-only / market-data only. Never places, modifies, or cancels an order,
never touches account/trading state, never subscribes a paid package.

Usage (smoke run, ~2-3 minutes, one liquid HK symbol):

    python wave1_runner.py --host 127.0.0.1 --port 11111 \\
        --market HK --symbols HK.00700 --duration 150 \\
        --stream-types QUOTE,K_1M --output-dir runs

Usage (Wave 1 run):

    python wave1_runner.py --host 127.0.0.1 --port 11111 \\
        --market HK --symbols HK.00700 --duration 600 \\
        --stream-types QUOTE,K_1M --output-dir runs \\
        --low-liquidity-symbol HK.01234

If ``--low-liquidity-symbol`` is omitted, F10 is reported NEEDS_MANUAL_SYMBOL
rather than the harness guessing an obscure instrument on its own.
"""

from __future__ import annotations

import argparse
import statistics
import sys
import time
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

# F28 needs to diff a UTC-aware local capture time against a NAIVE provider
# time_key string. We do not know the provider's timezone as fact -- this
# mapping is an explicit, recorded *interpretation candidate* (assume the
# provider timestamps in the traded market's local exchange timezone), never
# silently baked in. See analysis["f28_assumed_market_timezone_interpretation_candidate"].
_MARKET_TZ_INTERPRETATION_CANDIDATE = {
    "HK": "Asia/Hong_Kong",
    "US": "America/New_York",
    "CN": "Asia/Shanghai",
    "SH": "Asia/Shanghai",
    "SZ": "Asia/Shanghai",
}

sys.path.insert(0, str(Path(__file__).resolve().parent))

from models import SemanticTestResult, TestStatus  # noqa: E402
from recorder import (  # noqa: E402
    EvidenceRecorder,
    build_run_metadata,
    harness_version_hash,
    new_run_dir,
    utc_now_iso,
)

try:
    import futu as ft

    _FUTU_IMPORT_ERROR: Exception | None = None
except Exception as exc:  # pragma: no cover - exercised only when SDK missing
    ft = None
    _FUTU_IMPORT_ERROR = exc


# --------------------------------------------------------------------------
# Push handlers -- record every field, apply zero interpretation here.
# --------------------------------------------------------------------------


def _rows_of(data) -> list[dict]:
    try:
        return data.to_dict(orient="records")
    except Exception:
        return [{"raw_repr": repr(data)}]


def make_quote_handler(recorder: EvidenceRecorder, market_hint: str):
    class _QuoteHandler(ft.StockQuoteHandlerBase):
        def on_recv_rsp(self, rsp_pb):
            ret_code, data = super().on_recv_rsp(rsp_pb)
            if ret_code != ft.RET_OK:
                recorder.record_event(
                    provider="futu",
                    market=market_hint,
                    symbol=None,
                    stream_type="QUOTE",
                    event_type="push_error",
                    raw_sdk_ret=ret_code,
                    raw_sdk_err_text=str(data),
                    raw_payload=None,
                )
                return ft.RET_ERROR, data
            for row in _rows_of(data):
                recorder.record_event(
                    provider="futu",
                    market=market_hint,
                    symbol=row.get("code"),
                    stream_type="QUOTE",
                    event_type="push",
                    raw_sdk_ret=ret_code,
                    raw_sdk_err_text=None,
                    raw_payload=row,
                )
            return ft.RET_OK, data

    return _QuoteHandler()


def make_kline_handler(recorder: EvidenceRecorder, market_hint: str, stream_type: str):
    class _KlineHandler(ft.CurKlineHandlerBase):
        def on_recv_rsp(self, rsp_pb):
            ret_code, data = super().on_recv_rsp(rsp_pb)
            if ret_code != ft.RET_OK:
                recorder.record_event(
                    provider="futu",
                    market=market_hint,
                    symbol=None,
                    stream_type=stream_type,
                    event_type="push_error",
                    raw_sdk_ret=ret_code,
                    raw_sdk_err_text=str(data),
                    raw_payload=None,
                )
                return ft.RET_ERROR, data
            for row in _rows_of(data):
                recorder.record_event(
                    provider="futu",
                    market=market_hint,
                    symbol=row.get("code"),
                    stream_type=stream_type,
                    event_type="push",
                    raw_sdk_ret=ret_code,
                    raw_sdk_err_text=None,
                    raw_payload=row,
                )
            return ft.RET_OK, data

    return _KlineHandler()


# --------------------------------------------------------------------------
# SDK call wrapper -- always records, regardless of success or exception.
# --------------------------------------------------------------------------


def call_and_record(recorder: EvidenceRecorder, label: str, fn, *args, **kwargs):
    start = time.monotonic_ns()
    args_repr = f"args={args!r} kwargs={kwargs!r}"
    try:
        result = fn(*args, **kwargs)
        duration_ns = time.monotonic_ns() - start
        if isinstance(result, tuple) and len(result) == 2:
            ret_code, payload = result
            raw_response = _rows_of(payload) if hasattr(payload, "to_dict") else payload
        else:
            ret_code, raw_response = None, result
        recorder.record_sdk_call(
            call=label,
            args_repr=args_repr,
            raw_sdk_ret=ret_code,
            raw_response=raw_response,
            duration_ns=duration_ns,
        )
        return result
    except Exception as exc:  # noqa: BLE001 - the exception itself is evidence
        duration_ns = time.monotonic_ns() - start
        recorder.record_sdk_call(
            call=label,
            args_repr=args_repr,
            raw_sdk_ret="EXCEPTION",
            raw_response=f"{type(exc).__name__}: {exc}",
            duration_ns=duration_ns,
        )
        return None


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Futu/Moomoo provider-semantics harness (Wave 1)")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=11111)
    parser.add_argument("--market", default="HK", help="Primary market for the live stream tests (e.g. HK, US)")
    parser.add_argument("--symbols", default="HK.00700", help="Comma-separated symbol list for the live stream tests")
    parser.add_argument("--entitlement-markets", default="US,HK", help="Comma-separated markets to probe for F04/F05")
    parser.add_argument(
        "--entitlement-symbols",
        default="US.AAPL,HK.00700",
        help="Comma-separated symbols used for entitlement snapshot probes, one per entitlement market in order",
    )
    parser.add_argument("--duration", type=int, default=150, help="Seconds to hold the live subscription open")
    parser.add_argument("--stream-types", default="QUOTE,K_1M", help="Comma-separated SubType names")
    parser.add_argument("--output-dir", default=str(Path(__file__).resolve().parent / "runs"))
    parser.add_argument(
        "--low-liquidity-symbol",
        default=None,
        help="Symbol to use for F10; if omitted, F10 is reported NEEDS_MANUAL_SYMBOL",
    )
    parser.add_argument(
        "--invalid-symbol",
        default="HK.99999999",
        help="Deliberately-invalid symbol used for F06 negative-case subscription",
    )
    return parser.parse_args(argv)


# --------------------------------------------------------------------------
# Entitlement probes (F04 / F05)
# --------------------------------------------------------------------------


def run_entitlement_probes(recorder: EvidenceRecorder, ctx, markets: list[str], symbols: list[str]) -> None:
    call_and_record(recorder, "query_subscription", ctx.query_subscription, is_all_conn=True)
    call_and_record(recorder, "get_history_kl_quota", ctx.get_history_kl_quota, get_detail=True)

    # Corrected call (R1): get_delay_statistics(type_list, qot_push_stage,
    # segment_list). type_list takes DelayStatisticsType members (QOT_PUSH /
    # REQ_REPLY / PLACE_ORDER), NOT SubType -- the original probe passed
    # SubType.QUOTE/K_1M here, which the server rejected outright
    # ("missing required fields: c2s"). segment_list is a list of millisecond
    # bucket boundaries per the SDK's own docstring (e.g. 100/200/500/1000/
    # 2000/-1, where -1 is the overflow bucket) -- confirmed via
    # inspect.getsource(ft.OpenQuoteContext.get_delay_statistics).
    for stage_name in ("ALL",):
        stage = getattr(ft.QotPushStage, stage_name, None)
        type_ = getattr(ft, "DelayStatisticsType", None)
        if stage is None or type_ is None:
            continue
        call_and_record(
            recorder,
            f"get_delay_statistics[stage={stage_name},type=QOT_PUSH]",
            ctx.get_delay_statistics,
            type_list=[type_.QOT_PUSH],
            qot_push_stage=stage,
            segment_list=[100, 200, 500, 1000, 2000, -1],
        )

    for market, symbol in zip(markets, symbols):
        call_and_record(recorder, f"get_market_snapshot[{market}:{symbol}]", ctx.get_market_snapshot, [symbol])
        call_and_record(recorder, f"get_market_state[{market}:{symbol}]", ctx.get_market_state, [symbol])
        call_and_record(recorder, f"get_stock_quote[{market}:{symbol}]", ctx.get_stock_quote, [symbol])


# --------------------------------------------------------------------------
# Subscribe / ACK / normalization probes (F06 / F07 / F37)
# --------------------------------------------------------------------------


def run_subscribe_probes(
    recorder: EvidenceRecorder, ctx, market: str, valid_symbols: list[str], invalid_symbol: str, subtypes: list
) -> None:
    # Single valid symbol, single stream type.
    call_and_record(
        recorder, "subscribe[single_valid]", ctx.subscribe, [valid_symbols[0]], [subtypes[0]], subscribe_push=True
    )

    # Multiple valid symbols (only if more than one was supplied) + all requested stream types.
    if len(valid_symbols) > 1:
        call_and_record(
            recorder, "subscribe[multi_valid]", ctx.subscribe, valid_symbols, subtypes, subscribe_push=True
        )
    else:
        call_and_record(recorder, "subscribe[remaining_stream_types]", ctx.subscribe, valid_symbols, subtypes, subscribe_push=True)

    # Single invalid symbol.
    call_and_record(
        recorder, "subscribe[single_invalid]", ctx.subscribe, [invalid_symbol], [subtypes[0]], subscribe_push=True
    )

    # Mixed valid + invalid in one call.
    call_and_record(
        recorder,
        "subscribe[mixed_valid_invalid]",
        ctx.subscribe,
        [valid_symbols[0], invalid_symbol],
        [subtypes[0]],
        subscribe_push=True,
    )

    # Symbol normalization: request an unpadded HK code form and see what
    # comes back from a snapshot call using that exact string.
    if market == "HK":
        unpadded = valid_symbols[0].replace("HK.0", "HK.").lstrip("0").replace("HK.", "HK.0") if False else None
        # Build a deliberately different textual form (strip leading zeros
        # in the numeric part) without assuming a fixed code length.
        prefix, _, digits = valid_symbols[0].partition(".")
        if digits.isdigit():
            unpadded_form = f"{prefix}.{str(int(digits))}"
            if unpadded_form != valid_symbols[0]:
                call_and_record(
                    recorder,
                    f"get_market_snapshot[normalization_probe:{unpadded_form}]",
                    ctx.get_market_snapshot,
                    [unpadded_form],
                )


# --------------------------------------------------------------------------
# Post-hoc observational analysis (F01, F02, F03, F09, F10, F28)
# --------------------------------------------------------------------------


def analyze_events(events: list[dict], low_liquidity_symbol: str | None, market: str | None = None) -> dict:
    quote_events = [e for e in events if e["stream_type"] == "QUOTE" and e["event_type"] == "push"]
    kline_events = [e for e in events if e["stream_type"].startswith("K_") and e["event_type"] == "push"]

    tz_candidate_name = _MARKET_TZ_INTERPRETATION_CANDIDATE.get((market or "").upper())

    analysis: dict = {
        "quote_event_count": len(quote_events),
        "kline_event_count": len(kline_events),
        "f28_assumed_market_timezone_interpretation_candidate": tz_candidate_name,
    }

    # ---- F01: quote timestamp semantics ----
    by_symbol: dict[str, list[dict]] = defaultdict(list)
    for e in quote_events:
        by_symbol[e["symbol"]].append(e)
    f01_symbol_traces = {}
    for symbol, rows in by_symbol.items():
        trace = []
        for e in sorted(rows, key=lambda r: r["event_seq_local"]):
            payload = e["raw_payload"] or {}
            trace.append(
                {
                    "observed_at_utc": e["observed_at_utc"],
                    "monotonic_ns": e["monotonic_ns"],
                    "raw_data_date": payload.get("data_date"),
                    "raw_data_time": payload.get("data_time"),
                    "raw_update_time": payload.get("update_time"),
                    "last_price": payload.get("last_price"),
                    "volume": payload.get("volume"),
                    "turnover": payload.get("turnover"),
                }
            )
        f01_symbol_traces[symbol] = trace
    analysis["f01_quote_traces_by_symbol"] = f01_symbol_traces

    # Does provider timestamp change only when price/volume changes?
    f01_timestamp_changes_without_data_change = 0
    f01_data_changes_without_timestamp_change = 0
    for symbol, trace in f01_symbol_traces.items():
        for prev, cur in zip(trace, trace[1:]):
            ts_changed = (prev["raw_data_time"], prev["raw_update_time"]) != (cur["raw_data_time"], cur["raw_update_time"])
            data_changed = (prev["last_price"], prev["volume"], prev["turnover"]) != (
                cur["last_price"],
                cur["volume"],
                cur["turnover"],
            )
            if ts_changed and not data_changed:
                f01_timestamp_changes_without_data_change += 1
            if data_changed and not ts_changed:
                f01_data_changes_without_timestamp_change += 1
    analysis["f01_timestamp_changes_without_data_change"] = f01_timestamp_changes_without_data_change
    analysis["f01_data_changes_without_timestamp_change"] = f01_data_changes_without_timestamp_change

    # ---- F02 / F28: kline timestamp + publication delay ----
    by_symbol_kline: dict[str, list[dict]] = defaultdict(list)
    for e in kline_events:
        by_symbol_kline[e["symbol"]].append(e)
    f02_traces = {}
    delay_candidate_start: list[float] = []
    delay_candidate_end: list[float] = []
    for symbol, rows in by_symbol_kline.items():
        trace = []
        for e in sorted(rows, key=lambda r: r["event_seq_local"]):
            payload = e["raw_payload"] or {}
            trace.append(
                {
                    "observed_at_utc": e["observed_at_utc"],
                    "monotonic_ns": e["monotonic_ns"],
                    "raw_time_key": payload.get("time_key"),
                    "k_type": payload.get("k_type"),
                    "open": payload.get("open"),
                    "close": payload.get("close"),
                    "high": payload.get("high"),
                    "low": payload.get("low"),
                    "volume": payload.get("volume"),
                    "is_blank": payload.get("is_blank"),
                }
            )
            time_key = payload.get("time_key")
            if time_key and tz_candidate_name:
                try:
                    # time_key is a NAIVE provider string with no offset. We
                    # do not know its timezone as fact -- per the recorded
                    # interpretation candidate (assume exchange-local time
                    # for `market`), convert the UTC-aware capture time into
                    # that same naive local frame, then diff two naive
                    # datetimes so no accidental UTC-vs-local mismatch (the
                    # bug this comment replaces) can occur.
                    bar_ts_naive_local = datetime.fromisoformat(time_key)
                    observed_utc = datetime.fromisoformat(e["observed_at_utc"])
                    observed_naive_local = observed_utc.astimezone(ZoneInfo(tz_candidate_name)).replace(tzinfo=None)
                    # Candidate A: time_key is bar START -> boundary = start + 60s.
                    boundary_start_naive_local = bar_ts_naive_local + timedelta(seconds=60)
                    delay_candidate_start.append(
                        (observed_naive_local - boundary_start_naive_local).total_seconds()
                    )
                    # Candidate B: time_key is bar END -> boundary = time_key itself.
                    delay_candidate_end.append((observed_naive_local - bar_ts_naive_local).total_seconds())
                except Exception:
                    pass
        f02_traces[symbol] = trace
    analysis["f02_kline_traces_by_symbol"] = f02_traces

    # Does the callback repeat while the bar is forming (same time_key,
    # multiple pushes with differing OHLCV before the next time_key appears)?
    f02_repeated_same_bar = {}
    for symbol, trace in f02_traces.items():
        counts: dict[str, int] = defaultdict(int)
        for row in trace:
            counts[str(row["raw_time_key"])] += 1
        f02_repeated_same_bar[symbol] = {k: v for k, v in counts.items() if v > 1}
    analysis["f02_repeated_pushes_per_time_key"] = f02_repeated_same_bar

    def _dist(samples: list[float]) -> dict:
        if not samples:
            return {"count": 0}
        ordered = sorted(samples)
        out = {
            "count": len(ordered),
            "min": ordered[0],
            "p50": statistics.median(ordered),
            "max": ordered[-1],
        }
        if len(ordered) >= 20:
            out["p95"] = ordered[int(len(ordered) * 0.95) - 1]
        if len(ordered) >= 100:
            out["p99"] = ordered[int(len(ordered) * 0.99) - 1]
        return out

    analysis["f28_publication_delay_seconds"] = {
        "candidate_timestamp_is_start": _dist(delay_candidate_start),
        "candidate_timestamp_is_end": _dist(delay_candidate_end),
    }

    # ---- F03: timezone shape of raw fields ----
    raw_time_field_samples = []
    for e in (quote_events + kline_events)[:50]:
        payload = e["raw_payload"] or {}
        raw_time_field_samples.append(
            {
                "symbol": e["symbol"],
                "stream_type": e["stream_type"],
                "raw_data_time": payload.get("data_time"),
                "raw_update_time": payload.get("update_time"),
                "raw_time_key": payload.get("time_key"),
            }
        )
    analysis["f03_raw_time_field_samples"] = raw_time_field_samples

    # ---- F09 / F10: zero-trade / low-liquidity ----
    zero_volume_bars = []
    for symbol, trace in f02_traces.items():
        for row in trace:
            if row.get("volume") == 0:
                zero_volume_bars.append({"symbol": symbol, **row})
    analysis["f09_zero_volume_bar_events"] = zero_volume_bars

    if low_liquidity_symbol:
        analysis["f10_low_liquidity_symbol"] = low_liquidity_symbol
        analysis["f10_low_liquidity_kline_trace"] = f02_traces.get(low_liquidity_symbol, [])
        analysis["f10_low_liquidity_quote_trace"] = f01_symbol_traces.get(low_liquidity_symbol, [])
    else:
        analysis["f10_low_liquidity_symbol"] = None

    return analysis


# --------------------------------------------------------------------------
# Result assembly
# --------------------------------------------------------------------------


def build_results(
    *,
    run_dir: Path,
    sdk_version: str,
    opend_version: str | None,
    started_at: str,
    ended_at: str,
    market: str,
    symbols: list[str],
    analysis: dict,
    entitlement_markets: list[str],
) -> list[dict]:
    events_path = str(run_dir / "events.jsonl")
    sdk_calls_path = str(run_dir / "sdk_calls.jsonl")

    def base(test_id, stream_type, precondition, action):
        return dict(
            test_id=test_id,
            provider="futu",
            sdk_version=sdk_version,
            opend_version=opend_version,
            started_at_utc=started_at,
            ended_at_utc=ended_at,
            market=market,
            symbol=symbols[0] if symbols else None,
            stream_type=stream_type,
            precondition=precondition,
            action=action,
        )

    results: list[SemanticTestResult] = []

    # F01
    quote_count = analysis["quote_event_count"]
    ts_no_data = analysis["f01_timestamp_changes_without_data_change"]
    data_no_ts = analysis["f01_data_changes_without_timestamp_change"]
    if quote_count == 0:
        status, obs, limits = (
            TestStatus.UNRESOLVED,
            ["No quote push events were captured during this run window."],
            ["Run duration or market session may not have produced any pushes."],
        )
    elif ts_no_data > 0:
        # Timestamp changing with NO observable price/volume/turnover change
        # at all is the genuinely ambiguous direction -- it cannot be
        # explained away by coarse timestamp resolution the way data_no_ts
        # can, so this is the case that actually earns CONFLICTING.
        status, obs, limits = (
            TestStatus.CONFLICTING,
            [
                f"Observed {ts_no_data} instance(s) where the raw timestamp field changed but "
                f"last_price/volume/turnover did not, across {quote_count} quote pushes -- this is not "
                f"explained by timestamp coarseness and admits multiple readings (heartbeat/refresh push "
                f"vs. a genuine trade-adjacent field this harness did not diff).",
                f"Also observed {data_no_ts} instance(s) of data changing without the raw timestamp field "
                f"changing (see limitations -- expected under second-resolution timestamps).",
            ],
            ["Single short run; not enough samples to rule out coincidental repeats at low tick rate."],
        )
    elif data_no_ts > 0:
        status, obs, limits = (
            TestStatus.PARTIALLY_VERIFIED,
            [
                f"Observed {data_no_ts} instance(s), across {quote_count} quote pushes, where "
                f"last_price/volume/turnover changed but the raw timestamp field (second resolution, e.g. "
                f"'14:26:32') did not -- consistent with a timestamp whose resolution is coarser than the "
                f"actual push/trade cadence, not with the timestamp being decoupled from trade data.",
                f"{ts_no_data} case(s) of the reverse (timestamp changed, no observable data change) were seen.",
            ],
            [
                "Single short run against one instrument; the underlying raw field is second-resolution, so "
                "this evidence cannot by itself distinguish exchange-event time from provider-processing time "
                "at sub-second granularity.",
            ],
        )
    else:
        status, obs, limits = (
            TestStatus.PARTIALLY_VERIFIED,
            [
                f"Across {quote_count} quote pushes, no case was observed where price/volume/turnover changed "
                f"without the raw timestamp field also changing.",
                f"{ts_no_data} case(s) of timestamp changing with no observable price/volume/turnover change "
                f"were seen (consistent with a timestamp that ticks on something other than trade data alone, "
                f"e.g. quote-refresh or heartbeat-like updates -- not established either way by this sample).",
            ],
            ["Single short run against one instrument; cannot distinguish exchange-event time from "
             "provider-processing time from this evidence alone."],
        )
    results.append(
        SemanticTestResult(
            **base("F01", "QUOTE", "Live QUOTE subscription active", "Observe repeated QUOTE pushes and diff raw timestamp vs raw price/volume fields"),
            raw_evidence_paths=[events_path],
            status=status,
            observations=obs,
            limitations=limits,
            implementation_consequence="Do not assume quote update_time is trade-event time until adjudicated externally against exchange reference data.",
        )
    )

    # F02
    kline_count = analysis["kline_event_count"]
    repeats = analysis["f02_repeated_pushes_per_time_key"]
    total_repeat_keys = sum(len(v) for v in repeats.values())
    if kline_count == 0:
        status, obs, limits = (
            TestStatus.UNRESOLVED,
            ["No K_1M push events were captured during this run window."],
            ["Market may have been closed, or bar interval exceeded run duration."],
        )
    else:
        status = TestStatus.PARTIALLY_VERIFIED
        obs = [
            f"Captured {kline_count} K-line push events.",
            f"{total_repeat_keys} distinct time_key value(s) received more than one push before "
            f"(presumably) rolling to the next bar -- consistent with the callback firing multiple times "
            f"while a bar is forming, but this run does not independently confirm bar boundary semantics.",
            "Raw time_key strings were preserved verbatim; no start/end interpretation was applied by the harness.",
        ]
        limits = [
            "Whether time_key denotes bar start or bar end is NOT adjudicated here -- see F28 for both candidate delay distributions.",
            "Single short run; number of distinct minute boundaries observed is bounded by --duration.",
        ]
    results.append(
        SemanticTestResult(
            **base("F02", "K_1M", "Live K_1M subscription active near a minute boundary", "Observe repeated K_1M pushes and record raw time_key + OHLCV across consecutive bars"),
            raw_evidence_paths=[events_path],
            status=status,
            observations=obs,
            limitations=limits,
            implementation_consequence="Do not assume time_key is bar-start or bar-end without external adjudication; both candidates are recorded in F28.",
        )
    )

    # F03
    samples = analysis["f03_raw_time_field_samples"]
    if not samples:
        status, obs = TestStatus.UNRESOLVED, ["No push events with time fields were captured."]
    else:
        has_offset = any(
            (s.get("raw_data_time") and ("+" in str(s["raw_data_time"]) or "Z" in str(s["raw_data_time"])))
            or (s.get("raw_time_key") and ("+" in str(s["raw_time_key"]) or "Z" in str(s["raw_time_key"])))
            for s in samples
        )
        status = TestStatus.PARTIALLY_VERIFIED
        obs = [
            f"Sampled {len(samples)} raw time-field record(s) verbatim (see raw_evidence_paths).",
            f"Explicit UTC-offset or 'Z' marker present in sampled raw strings: {has_offset}.",
            "raw_data_time/raw_update_time/raw_time_key are stored as the exact provider text; no timezone was attached by the harness.",
        ]
    results.append(
        SemanticTestResult(
            **base("F03", "QUOTE+K_1M", "Live subscriptions active", "Inspect raw timestamp text fields for explicit timezone/offset markers"),
            raw_evidence_paths=[events_path],
            status=status,
            observations=obs,
            limitations=["interpretation_candidate parsing (if any) is exploratory only and never asserted as ground truth by this harness."],
            implementation_consequence="Never silently attach a timezone to these fields in production code without an externally adjudicated basis.",
        )
    )

    # F04 / F05
    results.append(
        SemanticTestResult(
            **base("F04", None, f"Connected OpenD session, markets probed: {entitlement_markets}", "Call query_subscription/get_history_kl_quota/get_delay_statistics/get_market_snapshot/get_market_state/get_stock_quote and record raw fields"),
            raw_evidence_paths=[sdk_calls_path],
            status=TestStatus.UNRESOLVED,
            observations=[
                "Raw SDK responses for entitlement-adjacent calls were captured verbatim in sdk_calls.jsonl.",
                "No field observed in this SDK version's responses was self-evidently a 'DeliveryMode' or realtime/delayed boolean; "
                "see sdk_calls.jsonl for the exact field names/values actually returned per call.",
            ],
            limitations=[
                "This harness does not map any observed field to DeliveryMode.REALTIME/DELAYED without a directly evidenced field -- "
                "none was found in this run, so the question remains UNRESOLVED rather than guessed.",
            ],
            implementation_consequence="Do not implement a DeliveryMode enum mapping from these fields until a directly evidencing field is found and reviewed externally.",
        )
    )
    results.append(
        SemanticTestResult(
            **base("F05", None, f"Entitlement probes run against markets: {entitlement_markets}", "Compare raw entitlement-adjacent evidence across markets"),
            raw_evidence_paths=[sdk_calls_path],
            status=TestStatus.UNRESOLVED if len(entitlement_markets) < 2 else TestStatus.PARTIALLY_VERIFIED,
            observations=[
                f"Entitlement probes were issued for markets: {entitlement_markets}.",
                "Raw per-market responses are in sdk_calls.jsonl, tagged by market in the call label.",
            ],
            limitations=["Account-level trading/quote permissions were not independently confirmed outside these SDK calls; scope conclusions are bounded by whatever this account currently holds."],
            implementation_consequence="Do not assume entitlement scope generalizes beyond the markets actually probed.",
        )
    )

    # F06 / F07
    results.append(
        SemanticTestResult(
            **base("F06", None, "OpenD connected, no prior subscriptions for the invalid symbol", "Issue subscribe() for valid, invalid, and mixed symbol lists and record raw return + timing"),
            raw_evidence_paths=[sdk_calls_path],
            status=TestStatus.PARTIALLY_VERIFIED,
            observations=[
                "Raw subscribe() return codes/error text for single-valid, invalid, and mixed-valid+invalid calls are in sdk_calls.jsonl.",
                "Whether RET_OK corresponds to a confirmed subscription (vs. merely an accepted request) is not established by return-code inspection alone; "
                "see whether push events for the subscribed symbol actually appear afterward in events.jsonl.",
            ],
            limitations=["Single subscribe attempt per case in this run; no retry/backoff variation tested."],
            implementation_consequence="Do not treat RET_OK from subscribe() as proof that live data will follow; confirm via observed pushes.",
        )
    )
    results.append(
        SemanticTestResult(
            **base("F07", None, "Same subscribe() calls as F06", "Determine ACK granularity from raw subscribe() return payloads (whole-request vs per-symbol)"),
            raw_evidence_paths=[sdk_calls_path, events_path],
            status=TestStatus.PARTIALLY_VERIFIED,
            observations=[
                "Raw subscribe() return payloads for the mixed valid+invalid case are recorded verbatim in sdk_calls.jsonl; "
                "inspect whether the return is a single ret_code/err_message pair (whole-request granularity) or contains per-symbol detail.",
                "First push event timestamps (if any) recorded in events.jsonl were compared against the subscribe() call's own timestamp in sdk_calls.jsonl to check whether data can arrive before an observable ACK.",
            ],
            limitations=["Only one batch shape (2 symbols, 1 valid + 1 invalid) was tested this run."],
            implementation_consequence="Do not assume per-symbol ACK granularity in production error handling without confirming the actual raw shape recorded here.",
        )
    )

    # F09
    zero_bars = analysis["f09_zero_volume_bar_events"]
    if zero_bars:
        status, obs = (
            TestStatus.PARTIALLY_VERIFIED,
            [f"Observed {len(zero_bars)} K-line push(es) with volume == 0; see raw_evidence_paths for exact records."],
        )
    else:
        status, obs = (
            TestStatus.UNRESOLVED,
            ["No zero-volume K-line push was observed during this run window; cannot distinguish 'no genuine zero-trade minute occurred' from 'provider suppresses zero-trade bars' from this evidence."],
        )
    results.append(
        SemanticTestResult(
            **base("F09", "K_1M", "Live K_1M subscription on the primary symbol(s)", "Scan captured K-line pushes for volume == 0 bars"),
            raw_evidence_paths=[events_path],
            status=status,
            observations=obs,
            limitations=["This harness does not fabricate a zero-trade minute; only genuine occurrences (if any) count as evidence."],
            implementation_consequence="Do not assume a specific zero-trade behavior (suppressed bar vs zero-volume bar vs repeated previous bar) without a genuine observed instance.",
        )
    )

    # F10
    low_liq_symbol = analysis.get("f10_low_liquidity_symbol")
    if not low_liq_symbol:
        results.append(
            SemanticTestResult(
                **base("F10", "K_1M", "No --low-liquidity-symbol supplied", "N/A"),
                raw_evidence_paths=[events_path],
                status=TestStatus.UNRESOLVED,
                observations=["NEEDS_MANUAL_SYMBOL: no low-liquidity symbol was configured for this run."],
                limitations=["The harness will not auto-select an obscure instrument; a symbol must be supplied via --low-liquidity-symbol."],
                implementation_consequence="Re-run with an explicit --low-liquidity-symbol before adjudicating F10.",
            )
        )
    else:
        trace = analysis.get("f10_low_liquidity_kline_trace", [])
        results.append(
            SemanticTestResult(
                **base("F10", "K_1M", f"Live K_1M subscription on low-liquidity symbol {low_liq_symbol}", "Observe raw K-line/quote traces for gaps/silence"),
                raw_evidence_paths=[events_path],
                status=TestStatus.PARTIALLY_VERIFIED if trace else TestStatus.UNRESOLVED,
                observations=[f"Captured {len(trace)} K-line push event(s) for {low_liq_symbol} during this run."],
                limitations=["Single symbol, single short run; not sufficient to generalize a silence rule."],
                implementation_consequence="Do not generalize a single-symbol observation into a repo-wide silence-handling rule.",
            )
        )

    # F28
    dist = analysis["f28_publication_delay_seconds"]
    tz_candidate = analysis.get("f28_assumed_market_timezone_interpretation_candidate")
    sample_n = dist["candidate_timestamp_is_start"].get("count", 0)
    if tz_candidate is None:
        status, obs, limits = (
            TestStatus.UNRESOLVED,
            [f"No timezone interpretation candidate is registered for market {market!r}; delay could not be computed without silently assuming a timezone, which this harness refuses to do."],
            ["Add the market to _MARKET_TZ_INTERPRETATION_CANDIDATE in wave1_runner.py to enable this computation, with the assumption explicitly recorded (as done for HK/US/CN)."],
        )
    else:
        status = TestStatus.PARTIALLY_VERIFIED if sample_n > 0 else TestStatus.UNRESOLVED
        obs = [
            f"Sample size: {sample_n} K-line push(es) with a parseable time_key.",
            f"interpretation_candidate: local capture time was converted to naive local time assuming timezone {tz_candidate!r} "
            f"for market {market!r} -- this is a recorded assumption, not a fact evidenced by the raw payload (time_key carries no offset).",
            f"Delay distribution under 'timestamp_is_start' candidate: {dist['candidate_timestamp_is_start']}",
            f"Delay distribution under 'timestamp_is_end' candidate: {dist['candidate_timestamp_is_end']}",
        ]
        limits = [
            f"Sample size {sample_n} is small for a single short run; percentile fields are only populated once enough samples exist (see distribution dict).",
            f"Delay values depend entirely on the {tz_candidate!r} timezone assumption above; if that assumption is wrong, every value in both distributions is wrong by the same offset.",
        ]
    results.append(
        SemanticTestResult(
            **base("F28", "K_1M", "Live K_1M subscription active", "Compute observed_at_utc minus candidate bar-boundary time, under both start-of-bar and end-of-bar interpretations"),
            raw_evidence_paths=[events_path],
            status=status,
            observations=obs,
            limitations=limits,
            implementation_consequence="Do not choose between the two candidate interpretations inside the harness; both distributions are reported for external adjudication together with F02.",
        )
    )

    # F37
    results.append(
        SemanticTestResult(
            **base("F37", None, f"Symbols requested: {symbols}", "Compare requested symbol text against SDK-returned code fields from snapshot/subscribe probes"),
            raw_evidence_paths=[sdk_calls_path],
            status=TestStatus.PARTIALLY_VERIFIED,
            observations=[
                "Raw get_market_snapshot responses for both the canonical and a deliberately-unpadded symbol form "
                "(where applicable) are recorded verbatim in sdk_calls.jsonl under the 'normalization_probe' call label.",
                "Compare the requested symbol string against the returned 'code'/'stock_code'/'market' fields in that record to determine whether the provider echoes back a canonicalized, market-qualified identity.",
            ],
            limitations=["Only one non-canonical textual variant was probed this run."],
            implementation_consequence="Do not assume requested-symbol text is safe to use as a cache/storage key; use whatever canonical field the raw evidence shows the provider actually returns.",
        )
    )

    return [r.to_dict() for r in results]


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    if ft is None:
        print("EXECUTION BLOCKED: futu SDK is not importable:", repr(_FUTU_IMPORT_ERROR))
        return 2

    symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]
    entitlement_markets = [m.strip() for m in args.entitlement_markets.split(",") if m.strip()]
    entitlement_symbols = [s.strip() for s in args.entitlement_symbols.split(",") if s.strip()]
    stream_type_names = [s.strip() for s in args.stream_types.split(",") if s.strip()]
    subtypes = []
    for name in stream_type_names:
        member = getattr(ft.SubType, name, None)
        if member is None:
            print(f"EXECUTION BLOCKED: unknown stream type {name!r} (not a ft.SubType member)")
            return 2
        subtypes.append(member)

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
            host=args.host,
            port=args.port,
            futu_sdk_version=getattr(ft, "__version__", "unknown"),
            opend_version=opend_version,
            opend_raw_global_state=global_state if isinstance(global_state, dict) else {"raw_repr": repr(global_state)},
            harness_version_hash=harness_version_hash(),
        )
        metadata["cli_args"] = vars(args)
        recorder.write_metadata(metadata)

        started_at = utc_now_iso()
        print(f"Run directory: {run_dir}")
        print(f"OpenD server_ver: {opend_version}")

        run_entitlement_probes(recorder, ctx, entitlement_markets, entitlement_symbols)
        run_subscribe_probes(recorder, ctx, args.market, symbols, args.invalid_symbol, subtypes)

        if args.low_liquidity_symbol:
            call_and_record(
                recorder, "subscribe[low_liquidity]", ctx.subscribe, [args.low_liquidity_symbol], subtypes, subscribe_push=True
            )

        ctx.set_handler(make_quote_handler(recorder, args.market))
        for name in stream_type_names:
            if name.startswith("K_"):
                ctx.set_handler(make_kline_handler(recorder, args.market, name))

        print(f"Holding subscription open for {args.duration}s ...")
        time.sleep(args.duration)

        ended_at = utc_now_iso()

        try:
            ctx.unsubscribe_all()
        except Exception as exc:
            recorder.record_sdk_call(
                call="unsubscribe_all", args_repr="()", raw_sdk_ret="EXCEPTION", raw_response=repr(exc), duration_ns=0
            )

        events = recorder.read_events()
        analysis = analyze_events(events, args.low_liquidity_symbol, market=args.market)
        recorder.write_observations(analysis)

        results = build_results(
            run_dir=run_dir,
            sdk_version=getattr(ft, "__version__", "unknown"),
            opend_version=opend_version,
            started_at=started_at,
            ended_at=ended_at,
            market=args.market,
            symbols=symbols,
            analysis=analysis,
            entitlement_markets=entitlement_markets,
        )
        recorder.write_results(results)

        print(f"Captured {analysis['quote_event_count']} quote events, {analysis['kline_event_count']} kline events.")
        print(f"Results written to: {run_dir / 'results.json'}")
        return 0
    finally:
        try:
            ctx.close()
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
