"""Isolated, user-space, localhost-only TCP forwarding proxy for Wave 2
Closure R1 safe transport-fault injection.

Topology (and nothing else):

    Futu OpenQuoteContext --> 127.0.0.1:<listen_port> --[this proxy]--> 127.0.0.1:<upstream_port> (OpenD)

Properties, all load-bearing for the safety model this task requires:

- Pure Python stdlib sockets/threads. No firewall rule, no routing table
  change, no OS-level network configuration is ever touched.
- Binds only to 127.0.0.1 (loopback), on a port the harness itself chose
  and owns exclusively for the duration of the run.
- Forwards bytes transparently in both directions for exactly the one
  experimental client<->OpenD flow the harness establishes -- it does not
  proxy, inspect, or touch any other socket, port, or process on the
  machine.
- CUT: stops accepting new inbound connections (any reconnect attempt from
  the SDK is refused immediately, simulating genuine transport
  unavailability) AND forcibly closes the currently-active
  client<->upstream socket pair, if any.
- RESTORE: resumes accepting new inbound connections; a subsequent SDK
  reconnect attempt will be forwarded to OpenD normally.
- ``stop()`` is a hard, idempotent cleanup path (closes the listen socket
  and any live pairs) safe to call from a ``finally`` block or twice.
- Every accept, cut, and restore is timestamped for the lifecycle record;
  the caller (wave2r1_runner.py) is responsible for actually writing those
  into the run's lifecycle.jsonl -- this module only exposes hooks/state,
  it does not import the recorder itself, to keep it independently testable.
"""

from __future__ import annotations

import socket
import threading
import time


class TransportProxy:
    def __init__(self, listen_host: str, listen_port: int, upstream_host: str, upstream_port: int):
        self.listen_host = listen_host
        self.listen_port = listen_port
        self.upstream_host = upstream_host
        self.upstream_port = upstream_port

        self._listen_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._listen_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._listen_sock.bind((listen_host, listen_port))
        self._listen_sock.listen(4)
        self._listen_sock.settimeout(0.5)

        self._accepting = threading.Event()
        self._accepting.set()
        self._stopped = False
        self._lock = threading.Lock()
        self._active_pairs: list[tuple[socket.socket, socket.socket]] = []

        # Observable, timestamped events the caller can poll and record.
        # Each entry: {"event": str, "monotonic_ns": int, "detail": dict}
        self.events: list[dict] = []
        self._events_lock = threading.Lock()

        self._accept_thread = threading.Thread(target=self._accept_loop, daemon=True)

    def _log(self, event: str, **detail) -> None:
        with self._events_lock:
            self.events.append({"event": event, "monotonic_ns": time.monotonic_ns(), "detail": detail})

    def start(self) -> None:
        self._accept_thread.start()
        self._log("PROXY_START", listen=(self.listen_host, self.listen_port), upstream=(self.upstream_host, self.upstream_port))

    def _accept_loop(self) -> None:
        while not self._stopped:
            try:
                client_sock, addr = self._listen_sock.accept()
            except socket.timeout:
                continue
            except OSError:
                break

            if not self._accepting.is_set():
                self._log("CONNECTION_REFUSED_DURING_CUT", client_addr=addr)
                try:
                    client_sock.close()
                except Exception:
                    pass
                continue

            try:
                upstream_sock = socket.create_connection((self.upstream_host, self.upstream_port), timeout=5)
            except Exception as exc:
                self._log("UPSTREAM_CONNECT_FAILED", error=repr(exc))
                try:
                    client_sock.close()
                except Exception:
                    pass
                continue

            with self._lock:
                self._active_pairs.append((client_sock, upstream_sock))
            self._log("CONNECTION_ESTABLISHED", client_addr=addr)

            threading.Thread(target=self._pump, args=(client_sock, upstream_sock, "client->upstream"), daemon=True).start()
            threading.Thread(target=self._pump, args=(upstream_sock, client_sock, "upstream->client"), daemon=True).start()

    def _pump(self, src: socket.socket, dst: socket.socket, direction: str) -> None:
        try:
            while True:
                data = src.recv(65536)
                if not data:
                    break
                dst.sendall(data)
        except Exception:
            pass
        finally:
            self._log("PUMP_ENDED", direction=direction)
            for sock in (src, dst):
                try:
                    sock.close()
                except Exception:
                    pass

    def cut(self) -> None:
        """Stop accepting new connections AND forcibly close the current
        active pair(s). Reversible via restore().
        """

        self._accepting.clear()
        with self._lock:
            pairs = list(self._active_pairs)
            self._active_pairs.clear()
        self._log("CUT", active_pairs_closed=len(pairs))
        for client_sock, upstream_sock in pairs:
            try:
                client_sock.close()
            except Exception:
                pass
            try:
                upstream_sock.close()
            except Exception:
                pass

    def restore(self) -> None:
        self._accepting.set()
        self._log("RESTORE")

    def stop(self) -> None:
        """Hard, idempotent cleanup. Safe to call more than once."""

        if self._stopped:
            return
        self._stopped = True
        self._log("PROXY_STOP")
        self.cut()
        try:
            self._listen_sock.close()
        except Exception:
            pass

    def drain_events(self) -> list[dict]:
        with self._events_lock:
            events, self.events = self.events, []
            return events
