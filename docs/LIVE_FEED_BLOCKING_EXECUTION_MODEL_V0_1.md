# Live Feed — Blocking Boundary / Execution Model (Draft R1)

Status: **PLANNING ONLY.** No threads/executors/queues are implemented by
this document. It specifies the conceptual execution lanes a future
implementation must respect, per frozen principle 15: *"Potentially
blocking provider SDK operations must not execute on the authoritative
controller writer thread."*

## Empirical basis

From `tools/provider_semantics/futu/derived/sync_api_risk_inventory.json`
and `FUTU_SEMANTIC_CONTRACT_V0_1.md` §2 BLOCKING:

- `KNOWN_BLOCKING_RISK` (empirically confirmed to hang in this project's
  own testing): `OpenQuoteContext.__init__` against an unreachable
  endpoint (~39-minute real hang before bounded isolation existed);
  `query_subscription()` called during an active transport outage
  (~19-minute real hang, root cause: RPC issued before `restore()`).
- `LIKELY_BLOCKING_RISK`: 123 additional public methods share the exact
  same synchronous dispatch mechanism (`_get_sync_query_processor`) as
  `query_subscription`, per static source scan. **This is a source-pattern
  match, not an empirical claim** — none of the 123 have been individually
  tested for actual blocking behavior. Do not present them as confirmed.
- `UNRESOLVED`: 8 public methods (`close`, `get_security_firm`,
  `get_sub_list`, `on_api_socket_reconnected`, `sub`, `unsub`,
  `unsub_all`, `unsubscribe_all`) did not match the static pattern scan;
  their blocking risk is simply unknown, not cleared.

## Execution lanes (conceptual, not an implementation)

```
LANE 1: Provider callback ingress (Futu adapter)
  - runs on whatever thread the Futu SDK delivers callbacks on
    (confirmed multi-threaded, per-run consistent per stream type)
  - work here: normalize payload → build immutable ProviderEvent → enqueue
  - MUST be nonblocking/minimal: no Futu RPC calls, no I/O beyond the
    enqueue itself, no waiting on locks held by LANE 2

LANE 2: LiveFeedController single writer
  - the ONLY place lifecycle state, registry truth, liveness, health, and
    recovery qualification are mutated (frozen principle 14: serialized
    single-writer controller)
  - consumes ProviderEvents from the ingress queue
  - MUST NOT call any potentially blocking Futu RPC directly — not even
    query_subscription — per frozen principle 15 and the two real hang
    incidents this project already suffered from violating exactly this rule
  - when it needs provider truth (e.g. "is this symbol actually
    subscribed right now"), it issues a command to LANE 3 and continues
    processing other events; the result comes back as its own event

LANE 3: Provider SDK command executor
  - owns: connect, subscribe, unsubscribe, query_subscription,
    diagnostics
  - every operation here needs an explicit timeout/boundary (see below)
  - results are delivered back to LANE 2 as immutable events, tagged with
    the command identity they answer (see §B1) — never as a direct
    return value the controller blocks waiting on

LANE 4: Snapshot/read consumers
  - reads only whatever LANE 2 has published as immutable state
  - unchanged from the existing `RealtimeMarketDataService.snapshot()`
    path (`src/services/realtime_market_data.py:120`)
```

## Which operations need a timeout/boundary

Every LANE 3 operation, without exception — including the 8 `UNRESOLVED`
methods, since "not pattern-matched as risky" is not the same as
"confirmed safe." The two operations with real empirical hang evidence
(`__init__`/construction, `query_subscription`) are the highest-priority
targets for whatever boundary mechanism is chosen; the 123
`LIKELY_BLOCKING_RISK` methods should inherit the same boundary by
default rather than being individually re-litigated.

## How results return to the single writer as immutable events

A LANE 3 command completes (success, provider error, or timeout) and
produces exactly one immutable result event, carrying the full command
identity (§B1) it answers. LANE 2 consumes it like any other event from
the ingress queue — there is no synchronous call/return path from LANE 2
into LANE 3 at all, which is what makes "the controller never blocks on
Futu" actually true rather than aspirational.

## How a stale result from an old generation is rejected

LANE 2, on receiving a LANE 3 result event, compares the event's embedded
command identity (`connection_generation`, `desired_registry_revision`,
etc.) against LANE 2's own current values before applying it. If they
don't match current truth, the result is recorded as evidence (for
diagnostics/audit) but must not mutate current desired-registry or
liveness state (frozen principle 6 example; also directly matches CASE 6
and CASE 29 in the adversarial set).

## Cancellation / shutdown, conceptually

- LANE 2 sets an internal `stop_requested` flag and stops issuing new
  LANE 3 commands.
- In-flight LANE 3 commands are not force-killed via ambiguous process
  signaling; they are allowed to either complete/time out under their
  existing boundary, or (for diagnostics-only, harness-precedented
  paths) run in an isolated child process that can be terminated
  unambiguously by the boundary mechanism, never by killing a
  same-process thread mid-SDK-call.
- LANE 1 stops delivering new events into the queue once the underlying
  `OpenQuoteContext` is closed by LANE 3's own shutdown command.
- This directly matches CASE 20 in the adversarial set (normal shutdown
  must not let the SDK's own reconnect timer resurrect a "connection"
  after `stop_requested`).

## What happens if a LANE 3 SDK call hangs

It is bounded by its own timeout mechanism (see PRODUCTION_REQUIRED vs
HARNESS_ONLY below) and reports back a timeout result event. LANE 2 never
finds out by blocking — it finds out by eventually receiving (or not
receiving, past its own patience threshold) a result event.

## What happens if the desired registry changes while an RPC is in flight

The in-flight command keeps whatever identity it was issued under. When
its result arrives, LANE 2 applies the staleness check above. If the
registry changed in the meantime, LANE 2 will independently need to issue
a *new* command reflecting the new desired state — the old command's
result, stale or not, never substitutes for that. This is CASE 29
directly.

## PRODUCTION_REQUIRED vs HARNESS_ONLY

The bounded subprocess helper built during the Offline Closure Pack
(`tools/provider_semantics/futu/bounded_probe.py`,
`run_bounded_provider_probe()`) is explicitly **HARNESS_ONLY**. It exists
to run empirical diagnostic probes safely during semantics research. It
is not vetted, sized, or designed as a production timeout mechanism — for
example it pays a full Python-interpreter-startup cost per call, has no
notion of a long-lived connection (it is a `subprocess.run(...)` per
probe, not a persistent worker), and has no result-routing back into a
LANE 2 event stream.

Whether a production LANE 3 executor needs actual OS-level process
isolation (because CPython threads cannot forcibly kill a thread stuck
inside a C-extension blocking call), or whether a sufficiently
conservative application-level timeout plus "never call this method
again on this context, recreate it instead" policy is acceptable, is an
**open design question**, not resolved by this document. What is settled
is only the negative constraint: an unbounded worker thread, by itself,
must not be presented as a timeout mechanism — a stuck synchronous SDK
call inside a plain Python thread cannot be safely cancelled by Python
alone, and pretending otherwise would just relocate the same class of
hang from the controller thread to a lane nobody is watching.

## B1. In-flight command identity (candidate)

| Field | Purpose |
|---|---|
| `runtime_instance_id` | which process instance issued this |
| `provider_id` | `"futu"` |
| `connection_generation` | which controller-issued connection epoch this command belongs to |
| `desired_registry_revision` | which version of desired-subscription truth this command reflects |
| `stream_subscription_epoch` | if applicable — a per-stream incarnation counter, distinct from `connection_generation` (frozen principle 10: these must never be conflated) |
| `command_id` | unique per issued command |
| `command_type` | `SUBSCRIBE` / `UNSUBSCRIBE` / `QUERY_SUBSCRIPTION` / `CONNECT` / `DIAGNOSTIC` |
| `semantic_stream_key` | which stream this command concerns, if applicable |
| `created_at` | issuance timestamp |

Example (directly from the frozen principles' own worked case): a
`SUBSCRIBE` command is issued under `desired_registry_revision=12`. Before
its result returns, the desired registry mutates to revision 13. The late
revision-12 success result arrives. LANE 2 must not let it overwrite
current desired truth — it applies the staleness check above and, at
most, records the result as historical evidence.
