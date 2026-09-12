# MCI-E07 Shadow Evidence — 2026-09-12

**experiment_id:** `MCI-E07-20260912-projection-v0`
**source_lane:** `AI_MONITOR/HARVEST`
**scope:** research-only deterministic Layer-B projection; production outputs and owners unchanged
**required reuse:** `SIBLING_ASSET_REUSED: PR #71 E06 benchmark protocol + E07 spec`

## Exact-head and validation status

- PR #71 exact head: `78e98ea2120d45c2602ba1b7c93640bea767a112` (unchanged after local fetch).
- Previously recorded at this exact head: Repository CI `#254 PASS`, Research Radar `#274 PASS`.
- A fresh GitHub API refresh was attempted but anonymous requests were rate-limited; no new remote status is asserted here.
- Targeted E07 tests: `8 passed` on Windows/Python 3.12.
- No validation PR was created and #71 remains intentionally unmerged.

## Corpus and layers

The bounded offline corpus has five cases: provider `UNKNOWN` plus entitlement `INDETERMINATE`; Gate/Candidate plus reason/risk; reason/risk-heavy stale data; portfolio truth; and distinct event/available/provider timestamps. The adversarial set also covers nested protected fields and unsupported schemas.

- Layer A: original payload, retained unchanged and addressed by `raw_ref`.
- Layer B: deterministic protected-field projection; repeated narrative lines may be deduplicated. Portfolio/runtime truth is passthrough.
- Layer C: not measured; no task-facing model/tool execution was performed.

## Gate results

| Gate | Result |
| --- | --- |
| critical_field_recall | 100% on tested protected fields |
| currentness_equivalence | 100% for represented status/reason/timestamps |
| gate_candidate_equivalence | 100% for represented records |
| reason_risk_retention | 100% set/value retention |
| raw_evidence_retrievability | 100% by preserved `raw_ref` in prototype |
| UNKNOWN/currentness/entitlement | retained explicitly |
| semantic_owner_delta | 0 |
| private_reach_through_delta | 0 |
| agent_read_set_delta | NOT MEASURED |
| token_delta_if_measured | NOT MEASURED; no fixed tokenizer/tool run |
| net_complexity_result | UNKNOWN |

Malformed nested protected fields fail loudly; arbitrary unsupported schemas are ineligible. No free-form summarization, production routing, cache-of-truth, health score, fallback, or portfolio authority was added.

## Governance closure

**Control Tower terminal decision: KEEP CURRENT OUTPUTS / SHADOW EVIDENCE ONLY.**

This bounded experiment is not a Promotion Candidate because Layer-C/task equivalence and reproducible token/read-set reduction were not measured. Recommendation: retain the prototype/tests as research guardrails; do not integrate or merge. Rollback is removal of the research-only prototype and test. Next validation condition: rerun the same corpus with fixed tokenizer/tooling and E06 Layer-B/C task protocol, then obtain fresh exact-head CI and Radar evidence before any durable remote closure.

**data_confidence:** medium for local gates; low for fresh remote CI/Radar due to API rate limit.
**unknown_fields:** Layer-C task correctness, reopen count, latency, fixed-tokenizer delta, fresh remote comments/checks.
