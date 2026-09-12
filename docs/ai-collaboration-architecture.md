# AI Collaboration Architecture V0.1

This document defines the repository's accelerated agent workflow. `AGENTS.md` remains the canonical rule source; this file is a context pointer for execution details.

## Goals

1. Reduce repeated reading, repeated explanation, and context growth.
2. Keep design, implementation, verification, and review as explicit phases.
3. Prefer small, end-to-end slices that fit in one fresh agent context.
4. Persist decisions in repository artifacts instead of relying on chat memory.
5. Preserve repository governance, runtime/data semantics, and rollback discipline while moving faster.

## Context Model

Use **progressive disclosure**:

- `AGENTS.md`: always-loaded global rules and pointers only.
- Domain docs / ADRs / specs: load when the task touches that branch.
- Tickets / issues: self-contained implementation contracts.
- CI, tests, code, config, and schemas: executable truth; prefer them over duplicated prose.
- Handoff notes: temporary context compression; reference durable artifacts instead of copying them.

A rule or decision should have one authoritative home. Prefer a pointer over repeating the same meaning in several agent files.

## Two Execution Paths

### Fast Path

Use when the change is narrow, low-risk, and the expected behavior is already clear.

`analyze-issue -> fix-issue or implement-ticket -> analyze-pr`

Skip a formal spec only when all of the following are true:

- scope is unambiguous;
- no new cross-module contract is introduced;
- no unresolved product/architecture decision exists;
- the change can be validated through an existing seam.

### Deep Path

Use for ambiguous, cross-module, high-risk, or multi-session work.

`to-spec -> to-tickets -> fresh context per ticket -> implement-ticket -> analyze-pr`

For hard bugs, insert `diagnose-bug` before implementation.

## Phase Boundaries

A phase boundary is a deliberate context decision.

- Continue in the same context while the next step depends heavily on reasoning that is not yet captured elsewhere.
- Start a fresh context when a ticket/spec contains enough information to execute independently.
- Use `handoff` when a session must stop before the current unit of work is complete.
- Do not carry large logs, old tool output, or full prior discussions forward when a durable artifact already contains the decision.

## Tracer-Bullet Tickets

Tickets should be narrow, complete vertical slices rather than horizontal layer batches.

A good ticket:

- delivers one verifiable behavior end to end;
- declares blockers explicitly;
- fits in one fresh context window;
- states acceptance criteria in observable terms;
- identifies important risk/compatibility constraints;
- avoids stale implementation detail unless that detail is itself a frozen contract.

Wide mechanical refactors are an exception. Use expand -> migrate -> contract so CI can stay green between steps.

## Test-Seam Rule

Before implementation, identify the highest practical seam that proves the requested behavior. Reuse existing seams where possible.

For bugs, first build a tight feedback loop that can reproduce the exact symptom. For features, define observable acceptance before implementation. Tests should exercise real behavior rather than mirror internal implementation structure.

## Review Axes

Review findings stay separated so one dimension cannot hide another:

1. **Standards**: repository rules, maintainability, compatibility, security, and documented conventions.
2. **Spec**: missing requirements, scope creep, and incorrect implementation of the requested behavior.
3. **Runtime / Data Semantics**: time/currentness, UNKNOWN handling, provider/fallback semantics, schema meaning, persistence/restart behavior, and other execution-truth risks when relevant.

A PR is not considered clean merely because one axis passes.

## Repository Identity

Repository skills must not hard-code a historical owner/repository name. Resolve the active repository when needed, for example:

```bash
REPO="$(gh repo view --json nameWithOwner -q .nameWithOwner)"
```

If repository resolution fails, stop and report the ambiguity instead of silently acting on a fallback repository.

## Handoff Contract

A handoff is a compact continuation packet, not a duplicate project history. It should contain only:

- current objective;
- current state and last verified baseline;
- unresolved decisions/blockers;
- next executable action;
- pointers to issue/spec/ADR/PR/test evidence;
- suggested repository skills for the next session.

Never copy secrets, credentials, or large logs into a handoff.

## Speed Rules

- Read the smallest authoritative surface that can answer the question.
- Prefer CI/diff/test evidence over rerunning broad suites without a reason.
- Fix the highest-level contract once instead of patching repeated symptoms.
- Use fresh contexts for independent tickets; do not drag unrelated history forward.
- Keep implementation minimal; avoid opportunistic refactors.
- Stop early on a broken prerequisite rather than building on UNKNOWN state.

## Validation

Any change to repository AI collaboration assets must pass:

```bash
python scripts/check_ai_assets.py
```

The normal code/build validation matrix in `AGENTS.md` still applies to implementation changes.

## Inspiration / Attribution

The workflow intentionally adapts ideas such as context pointers, tracer-bullet tickets, phase boundaries, tight debugging loops, and separated review axes from Matt Pocock's `mattpocock/skills` project. The local implementation is adapted to Stock Razor's existing governance and repository constraints rather than vendoring the upstream skills unchanged.
