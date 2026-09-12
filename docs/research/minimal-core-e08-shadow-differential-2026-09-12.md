# Minimal Core E08 — Imported-Constant Shadow Differential

**Mode:** Research / Shadow only  
**Head audited:** `0bd06e1c28c564e973698f2e0e2acb614bb11fc0`  
**Production diff:** none

## Preflight

`SIBLING_CHECKED_NO_EQUIVALENT`: the five checked sibling workspaces had no
E08/config-drift implementation equivalent. PR #71 was refreshed before this
experiment; the only change since the prior E07 head was a governance/code-owner
mapping commit, outside the E08 surfaces.

## Shadow model

The existing constants in `src/llm/local_cli_backend.py` are treated as the
hypothetical single owner. The model projects those values into the registry
and `.env.example` in memory; it does not edit production modules or rewrite
the example file.

| Default | Existing runtime owner | Registry/example | Classification |
| --- | --- | --- | --- |
| `GENERATION_BACKEND=litellm` | `LITELLM_BACKEND_ID` | aligned | `SHADOW_CANDIDATE` |
| `GENERATION_BACKEND_TIMEOUT_SECONDS=300` | `DEFAULT_LOCAL_CLI_TIMEOUT_SECONDS` | aligned | `SHADOW_CANDIDATE` |
| `GENERATION_BACKEND_MAX_OUTPUT_BYTES=1048576` | `DEFAULT_LOCAL_CLI_MAX_OUTPUT_BYTES` | aligned | `SHADOW_CANDIDATE` |
| `GENERATION_BACKEND_MAX_CONCURRENCY=1` | `DEFAULT_GENERATION_BACKEND_MAX_CONCURRENCY` | aligned | `SHADOW_CANDIDATE` |
| `LOCAL_CLI_BACKEND_MAX_CONCURRENCY=1` | `DEFAULT_LOCAL_CLI_BACKEND_MAX_CONCURRENCY` | aligned | `SHADOW_CANDIDATE` |
| `STOCK_LIST` | runtime fallback is empty | registry/example seed is `600519,300750,002594` | `KEEP_DUPLICATE_BY_SEMANTICS` |
| `GENERATION_FALLBACK_BACKEND` | missing env falls back; empty env disables fallback | registry/example display default | `KEEP_DUPLICATE_BY_SEMANTICS` |

## Protected differential cases

The Shadow tests preserve the following counterexamples and contracts:

- Missing versus empty versus explicit environment values remain distinct;
- numeric bounds/types and malformed-value handling remain owned by runtime parsing;
- empty and non-empty `STOCK_LIST` retain runtime fallback/validation semantics;
- registry metadata and `.env.example` are not runtime authority and may diverge;
- historical documentation text must not override runtime values;
- secrets, ConfigManager file semantics, startup behavior, and UNKNOWN/currentness
  behavior are untouched.

## Measurements and decision

- Repeated default/contract sites before Shadow: 3 surface representations for
  each bounded aligned default (runtime, registry, example); after the in-memory
  Shadow projection: 1 semantic owner plus 2 derived consumers. No files were
  deleted.
- `semantic_owner_delta`: `UNKNOWN` for production; Shadow model indicates
  `-2` potential copied representations per aligned field, pending an approved
  implementation gate.
- `duplicate_site_delta`: `0` production; `-2` hypothetical per aligned field.
- Agent read-set delta: `NOT_MEASURED` (E06 protocol not reproducibly available
  in this checkout).
- Token delta: `NOT_MEASURED`.
- `net_complexity_result=UNKNOWN`: parity is shown, but deletion, read-set
  reduction, rollback, and production ownership have not been validated.

Terminal decision: `KEEP_CURRENT_CONFIG_SURFACES / SHADOW_EVIDENCE_ONLY`.

Promotion is not authorized. A future implementation would require an explicit
Control Tower gate, fresh exact-head CI/Radar, and rollback evidence. Rollback
would be reverting only the imported-constant production change; no such change
was made here.
