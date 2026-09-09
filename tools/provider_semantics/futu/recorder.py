"""Append-only raw-evidence recorder for the Futu semantics harness.

Design rules this module enforces mechanically (see harness_selftest.py):

- Every run gets its own timestamped directory. Rerunning never overwrites
  a prior run's evidence.
- ``events.jsonl`` and ``sdk_calls.jsonl`` are opened in append mode only,
  for the lifetime of the recorder, and are never rewritten in place.
- Every timestamp recorded is timezone-aware UTC, generated at the moment
  of the call -- never a naive ``datetime.now()``.
- ``event_seq_local`` is a strictly increasing integer per recorder
  instance, assigned under a lock, so concurrent callback threads cannot
  produce duplicate or out-of-order sequence numbers.
- Anything shaped like a secret is redacted before it reaches disk.
"""

from __future__ import annotations

import json
import platform
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from models import raw_event, scrub_secrets


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def _json_default(value: Any) -> Any:
    """Last-resort encoder for objects json.dumps cannot serialize natively
    (e.g. pandas Timestamp, numpy scalars returned inside SDK payloads).
    Never silently drops data -- falls back to repr() rather than raising.
    """

    for attr in ("isoformat",):
        method = getattr(value, attr, None)
        if callable(method):
            try:
                return method()
            except Exception:
                pass
    try:
        import numpy as np  # noqa: PLC0415

        if isinstance(value, np.generic):
            return value.item()
    except Exception:
        pass
    try:
        import pandas as pd  # noqa: PLC0415

        if isinstance(value, pd.DataFrame):
            return {"__pandas_dataframe__": value.to_dict(orient="records")}
        if isinstance(value, pd.Series):
            return {"__pandas_series__": value.to_dict()}
    except Exception:
        pass
    return repr(value)


class EvidenceRecorder:
    """One instance per run. Owns exactly one run directory."""

    def __init__(self, run_dir: Path) -> None:
        self.run_dir = run_dir
        self.run_dir.mkdir(parents=True, exist_ok=False)
        self._events_path = self.run_dir / "events.jsonl"
        self._sdk_calls_path = self.run_dir / "sdk_calls.jsonl"
        # Touch both files now so their existence (and the "append only,
        # never truncated again") invariant is established from t=0.
        self._events_path.touch(exist_ok=False)
        self._sdk_calls_path.touch(exist_ok=False)
        self._lock = threading.Lock()
        self._seq = 0
        self._start_monotonic_ns = time.monotonic_ns()

    # -- sequencing -------------------------------------------------------

    def next_seq(self) -> int:
        with self._lock:
            self._seq += 1
            return self._seq

    # -- low-level append ---------------------------------------------------

    def _append_jsonl(self, path: Path, record: dict) -> None:
        line = json.dumps(record, ensure_ascii=False, default=_json_default)
        with self._lock:
            with path.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")
                handle.flush()

    # -- public API ---------------------------------------------------------

    def record_event(
        self,
        *,
        provider: str,
        market: str | None,
        symbol: str | None,
        stream_type: str,
        event_type: str,
        raw_sdk_ret: Any = None,
        raw_sdk_err_text: str | None = None,
        raw_payload: Any = None,
    ) -> dict:
        record = raw_event(
            observed_at_utc=utc_now_iso(),
            monotonic_ns=time.monotonic_ns(),
            thread_id=threading.get_ident(),
            event_seq_local=self.next_seq(),
            provider=provider,
            market=market,
            symbol=symbol,
            stream_type=stream_type,
            event_type=event_type,
            raw_sdk_ret=raw_sdk_ret,
            raw_sdk_err_text=raw_sdk_err_text,
            raw_payload=raw_payload,
        )
        self._append_jsonl(self._events_path, record)
        return record

    def record_sdk_call(
        self,
        *,
        call: str,
        args_repr: str,
        raw_sdk_ret: Any,
        raw_response: Any,
        duration_ns: int,
    ) -> dict:
        record = {
            "observed_at_utc": utc_now_iso(),
            "monotonic_ns": time.monotonic_ns(),
            "thread_id": threading.get_ident(),
            "event_seq_local": self.next_seq(),
            "call": call,
            "args_repr": scrub_secrets(args_repr),
            "raw_sdk_ret": raw_sdk_ret,
            "raw_response": scrub_secrets(raw_response),
            "duration_ns": duration_ns,
        }
        self._append_jsonl(self._sdk_calls_path, record)
        return record

    def write_metadata(self, metadata: dict) -> Path:
        path = self.run_dir / "metadata.json"
        if path.exists():
            raise FileExistsError(f"metadata.json already written for run {self.run_dir}")
        path.write_text(
            json.dumps(scrub_secrets(metadata), ensure_ascii=False, indent=2, default=_json_default),
            encoding="utf-8",
        )
        return path

    def write_observations(self, observations: dict) -> Path:
        path = self.run_dir / "observations.json"
        if path.exists():
            raise FileExistsError(f"observations.json already written for run {self.run_dir}")
        path.write_text(
            json.dumps(scrub_secrets(observations), ensure_ascii=False, indent=2, default=_json_default),
            encoding="utf-8",
        )
        return path

    def write_results(self, results: list[dict]) -> Path:
        path = self.run_dir / "results.json"
        if path.exists():
            raise FileExistsError(f"results.json already written for run {self.run_dir}")
        path.write_text(
            json.dumps(scrub_secrets(results), ensure_ascii=False, indent=2, default=_json_default),
            encoding="utf-8",
        )
        return path

    def read_events(self) -> list[dict]:
        """Read-back helper for post-hoc analysis. Never used to mutate
        ``events.jsonl`` -- callers get a list of dicts, not a file handle.
        """

        if not self._events_path.exists():
            return []
        records = []
        with self._events_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if line:
                    records.append(json.loads(line))
        return records


def build_run_metadata(
    *,
    host: str,
    port: int,
    futu_sdk_version: str,
    opend_version: str | None,
    opend_raw_global_state: dict | None,
    harness_version_hash: str,
) -> dict:
    """Environment provenance required for every run (spec section 19)."""

    local_tz = datetime.now().astimezone().tzinfo
    return {
        "python_version": sys.version,
        "os": f"{platform.system()} {platform.release()} ({platform.version()})",
        "futu_sdk_version": futu_sdk_version,
        "opend_host": host,
        "opend_port": port,
        "opend_version_field": opend_version,
        "opend_raw_global_state": opend_raw_global_state,
        "local_timezone": str(local_tz),
        "system_utc_time_at_run_start": utc_now_iso(),
        "repo_head": _git_head(),
        "harness_version_hash": harness_version_hash,
    }


def _git_head() -> str | None:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=Path(__file__).resolve().parents[3],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if out.returncode == 0:
            return out.stdout.strip()
    except Exception:
        pass
    return None


def harness_version_hash() -> str:
    """Hash of this harness's own source files, so evidence can be tied back
    to the exact harness code that produced it even without a git commit.
    """

    import hashlib

    here = Path(__file__).resolve().parent
    digest = hashlib.sha256()
    for name in sorted(("models.py", "recorder.py", "wave1_runner.py")):
        path = here / name
        if path.exists():
            digest.update(path.read_bytes())
    return digest.hexdigest()


def new_run_dir(base: Path) -> Path:
    """Deterministic, collision-resistant run directory name."""

    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S-%fZ")
    candidate = base / stamp
    suffix = 0
    while candidate.exists():
        suffix += 1
        candidate = base / f"{stamp}-{suffix}"
    return candidate
