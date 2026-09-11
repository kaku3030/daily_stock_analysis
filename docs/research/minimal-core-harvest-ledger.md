# Minimal Core External Harvest Ledger — Superseded

This document has been superseded by:

- `docs/research/minimal-core-harvest-ledger-v0.2.md`

Use V0.2 as the canonical external-reference ledger for the Minimal Core Initiative.

## Why this file was superseded

The earlier ledger contained a factual drift: it stated that `cachetools` was already a Stock Razor dependency. The root `requirements.txt` does not declare `cachetools`; `tenacity` and `schedule` are the relevant existing dependencies.

Rather than keep a long research document with a known stale fact and force every agent to remember an exception, the canonical ledger was compacted and corrected in V0.2.

Git history preserves the previous detailed Harvest cards if historical comparison is needed.

**Rule:** repository/runtime evidence overrides research notes and chat memory.
