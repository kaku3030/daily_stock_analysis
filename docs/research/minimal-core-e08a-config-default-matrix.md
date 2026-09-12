# Minimal Core E08-A — Config Default / Metadata Matrix

**Mode:** Research / Shadow  
**Production behavior change:** none

## Result

Configuration duplication is real, but not every repeated-looking value has the same semantic role.

The most important finding is that a future single-source schema must distinguish at least:

```text
runtime_default
ui_seed_or_default
operator_example
validation rule
```

Collapsing these into one `default_value` can change runtime behavior.

## Bounded matrix

| Field | Runtime source | Registry | `.env.example` | Assessment |
| --- | --- | --- | --- | --- |
| `STOCK_LIST` | runtime resolution defaults to empty string; validation requires non-empty | `600519,300750,002594` | `600519,300750,002594` | **different roles**: runtime default vs UI/example seed |
| `GENERATION_BACKEND` | `LITELLM_BACKEND_ID` | `litellm` | `litellm` | aligned, duplicated representation |
| `GENERATION_FALLBACK_BACKEND` | missing env -> `litellm`; explicit empty has distinct disable/no-op semantics | `litellm` | `litellm` | aligned default, but empty semantics must stay explicit |
| `GENERATION_BACKEND_TIMEOUT_SECONDS` | `DEFAULT_LOCAL_CLI_TIMEOUT_SECONDS` + bounds | literal `300`, bounds `1..3600` | `300` | true duplicate fact candidate |
| `GENERATION_BACKEND_MAX_OUTPUT_BYTES` | `DEFAULT_LOCAL_CLI_MAX_OUTPUT_BYTES` + bounds | literal `1048576`, bounds | `1048576` | true duplicate fact candidate |
| `GENERATION_BACKEND_MAX_CONCURRENCY` | runtime constant + bounds | literal `1`, bounds | `1` | true duplicate fact candidate |
| `LOCAL_CLI_BACKEND_MAX_CONCURRENCY` | runtime constant + bounds | literal `1`, bounds | `1` | true duplicate fact candidate |

## Concrete drift signal

`src/core/config_registry.py` still contains documentation links pointing to the historical upstream `ZhuLinsen/daily_stock_analysis` repository.

This is exactly the failure mode E08 is intended to reduce: metadata that is correct when copied but slowly drifts because it is maintained independently.

Do not fix this by creating a giant configuration framework. A narrow link/base-repository helper or repo-local docs path may be enough in a later FIX.

## Smallest useful evidence

`tests/test_minimal_core_e08_config_default_drift.py` compares a bounded set of **truly shared numeric/backend defaults** across:

```text
runtime constants
config registry default_value
.env.example concrete value
```

This test deliberately excludes `STOCK_LIST` from equality because the current roles are different.

## Delete-first opportunities

### Candidate A — numeric default duplication

For fields whose default is truly one runtime fact, prefer one runtime constant and derive registry assertions/metadata from it rather than copying literals.

A production implementation could be as small as importing the already-existing constants into registry metadata. No schema generator is required unless repeated evidence justifies it.

### Candidate B — drift detection instead of code generation

A consistency test may deliver most of the value of a “single schema” with far less architecture.

If five assertions prevent practical drift, do not build a config compiler.

## KEEP

- `ConfigManager` file I/O, optimistic versioning, atomic replacement and mount-aware behavior;
- explicit empty-value semantics where empty is meaningful;
- runtime validation that is contextual or cross-field;
- UI-only descriptions/help metadata where no runtime semantic owner exists.

## REJECT by default

- replacing all config loading with a new framework merely to reduce file count;
- one `default` property that conflates runtime fallback with UI seed/example;
- generating `.env.example` if generation adds more machinery than the duplication it removes.

## Promotion condition

A future E08 simplification must show:

```text
same runtime parse behavior
same explicit-empty behavior
same bounds/validation
same UI defaults/examples where intended
fewer duplicated semantic facts
smaller Agent read-set
net_complexity_result = SMALLER
```

E08-A conclusion: start with **tests + imported constants**, not a framework.

Current result: `net_complexity_result = UNKNOWN`. The Shadow test reduces drift
risk and quantifies five aligned facts, but it does not itself remove a runtime
owner or reduce the production read-set. An imported-constant change remains a
candidate only after compatibility and rollback evidence.
