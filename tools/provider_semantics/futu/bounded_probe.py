"""Wave 2 harness hardening: a generic bounded-subprocess helper for
dangerous diagnostic SDK calls.

Generalizes the ad-hoc pattern used for the F34 unreachable-port probe
(Wave 2 Closure R1) into a single, reusable, harness-only helper. For
empirical probes only -- this is not a production timeout wrapper and must
not be presented as one.

Guarantees:
- the probe code runs in a genuinely separate child process (never
  in-thread, so a hang can never block the harness's own event loop or
  main thread)
- a hard wall-clock timeout, after which the child is terminated by
  ``subprocess`` itself (no ambiguous process-tree cleanup is attempted by
  this module -- Python's own ``subprocess.run(..., timeout=...)`` already
  owns and kills exactly the one child it spawned)
- stdout/stderr are always captured, timeout or not
- exact ownership: the only process this helper can ever affect is the
  single child it spawned via ``sys.executable -c <code>``
"""

from __future__ import annotations

import subprocess
import sys
import time
from dataclasses import dataclass


@dataclass(frozen=True)
class BoundedProbeResult:
    completed: bool
    timed_out: bool
    returncode: int | None
    stdout: str
    stderr: str
    duration_seconds: float
    child_command: list[str]


def run_bounded_provider_probe(python_code: str, *, timeout_seconds: float = 15.0) -> BoundedProbeResult:
    """Run `python_code` in an isolated child Python process with a hard
    timeout. Never raises on timeout -- returns a BoundedProbeResult with
    timed_out=True instead, so callers never need their own try/except
    around this to stay safe.
    """

    command = [sys.executable, "-c", python_code]
    start = time.monotonic()
    try:
        proc = subprocess.run(command, capture_output=True, text=True, timeout=timeout_seconds)
        duration = time.monotonic() - start
        return BoundedProbeResult(
            completed=True,
            timed_out=False,
            returncode=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
            duration_seconds=duration,
            child_command=command,
        )
    except subprocess.TimeoutExpired as exc:
        duration = time.monotonic() - start
        stdout = exc.stdout.decode("utf-8", "replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        stderr = exc.stderr.decode("utf-8", "replace") if isinstance(exc.stderr, bytes) else (exc.stderr or "")
        return BoundedProbeResult(
            completed=False,
            timed_out=True,
            returncode=None,
            stdout=stdout,
            stderr=stderr,
            duration_seconds=duration,
            child_command=command,
        )
