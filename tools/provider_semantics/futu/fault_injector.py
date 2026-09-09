"""Wave 2 fault-injection primitives, tiered by safety level.

LEVEL 0 (context-only): always available. Never touches OpenD itself or
machine network configuration -- only the client-side OpenQuoteContext
object, subscriptions, and handlers.

LEVEL 1 (transport interruption): NOT implemented in this harness. A safe,
reversible, non-machine-wide method to interrupt only this process's
transport to OpenD was not identified without touching system-wide network
configuration (firewall rules, routing) or process-level socket
manipulation that risks affecting unrelated workflows -- both are exactly
what the Wave 2 brief says not to do "blindly". Calling into this tier
returns TEST_BLOCKED_SAFETY unconditionally.

LEVEL 2 (OpenD restart): implemented but requires the caller to pass
``allow_opend_restart=True`` AND a ``verified_pid`` that this module
independently re-checks is still listening on the target port and is named
identifiably as OpenD before doing anything. Even then, this module only
*terminates* the verified process -- it does not attempt to relaunch it
(this harness has no reliable, safe way to know the correct relaunch
command/working directory for the user's OpenD installation), so a restart
is only as safe as the operator's ability to relaunch OpenD by hand
afterward. If the caller does not explicitly opt in, this tier returns
TEST_BLOCKED_SAFETY and touches nothing.
"""

from __future__ import annotations

import subprocess
import sys


class SafetyBlocked(Exception):
    """Raised when a requested fault-injection tier was not authorized or
    could not be safely verified. Callers should catch this and record
    TEST_BLOCKED_SAFETY, never retry with reduced verification.
    """


def level0_close_context(ctx) -> None:
    ctx.close()


def level0_create_context(host: str, port: int):
    import futu as ft

    return ft.OpenQuoteContext(host=host, port=port)


def level1_interrupt_transport(*_args, **_kwargs) -> None:
    raise SafetyBlocked(
        "LEVEL 1 transport interruption is not implemented: no safe, reversible, "
        "non-machine-wide method was identified. Refusing rather than touching "
        "firewall/network configuration blindly."
    )


def find_listening_pid(port: int) -> tuple[int | None, str | None]:
    """Read-only identification: PID listening on `port` and its image name,
    via `netstat`/`tasklist`. Never modifies anything.
    """

    try:
        netstat = subprocess.run(["netstat", "-ano"], capture_output=True, text=True, timeout=10)
    except Exception:
        return None, None
    pid = None
    for line in netstat.stdout.splitlines():
        if f":{port} " in line and "LISTENING" in line:
            parts = line.split()
            if parts:
                try:
                    pid = int(parts[-1])
                except ValueError:
                    pid = None
            break
    if pid is None:
        return None, None
    try:
        tasklist = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
            capture_output=True, text=True, timeout=10,
        )
        image_name = None
        for line in tasklist.stdout.splitlines():
            fields = [f.strip('"') for f in line.split(",")]
            if fields and fields[0]:
                image_name = fields[0]
                break
        return pid, image_name
    except Exception:
        return pid, None


def level2_restart_opend(*, host: str, port: int, allow_opend_restart: bool, expected_pid: int | None) -> dict:
    """Terminate the verified OpenD process. Returns a raw evidence dict.
    Never called unless allow_opend_restart=True AND identity re-verification
    passes. Does not relaunch OpenD -- see module docstring.
    """

    if not allow_opend_restart:
        raise SafetyBlocked("LEVEL 2 OpenD restart requires allow_opend_restart=True; not granted.")

    pid, image_name = find_listening_pid(port)
    if pid is None:
        raise SafetyBlocked(f"Could not identify a process listening on port {port}; refusing to restart blindly.")
    if expected_pid is not None and pid != expected_pid:
        raise SafetyBlocked(
            f"PID listening on port {port} changed since baseline identification "
            f"({expected_pid} -> {pid}); refusing -- identity is no longer verified."
        )
    if not image_name or "opend" not in image_name.lower():
        raise SafetyBlocked(
            f"Process on port {port} (PID {pid}) has image name {image_name!r}, which does not "
            f"identifiably look like OpenD; refusing to terminate."
        )

    result = {"pid": pid, "image_name": image_name, "action": "taskkill", "platform": sys.platform}
    proc = subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True, text=True, timeout=15)
    result["taskkill_returncode"] = proc.returncode
    result["taskkill_stdout"] = proc.stdout
    result["taskkill_stderr"] = proc.stderr
    return result
