# Minimal Core E09 — Representative Minimum Safe Agent Read-Set

**Mode:** Research / Shadow  
**Exact head under test:** `6b1ad363c1c65fc075e3ac7f3df1fd5c77902d23`  
**Representative task:** add one canonical HK symbol input form without
changing market classification or provider wire formatting.

## Minimum safe read-set observed

The task cannot be safely answered from one symbol helper alone. The bounded
read-set is:

1. `docs/research/minimal-core-current-state.md` — governance and owner
   boundaries;
2. `docs/research/minimal-core-e12a-symbol-fixture-corpus.md` — corpus and
   known edge cases;
3. `docs/research/minimal-core-e12b-market-wrapper-delete-audit.md` — current
   wrapper/delete candidate and precedence rules;
4. `src/services/market_symbol_utils.py` — canonical semantic owner;
5. `data_provider/base.py` — routing/classification consumer and provider
   boundary;
6. `tests/test_minimal_core_e12_symbol_corpus.py` and
   `tests/test_minimal_core_e12b_market_wrapper_shadow.py` — executable
   differential contract.

## Safety result

This is the minimum set that exposes canonical identity, HK bare-numeric
precedence, US-before-HK ordering, CN fallback, provider-local wire ownership,
and the current Shadow contract. Omitting `base.py` hides routing consumers;
omitting the tests hides the adversarial corpus; omitting the current-state
pointer hides the no-production/no-merge gate.

The measured result is therefore **6 logical artifacts / 7 file reads** (the
two test files are separate reads), with no production file modified. A
smaller set is **unsafe**, not an E09 win. This is a structural baseline, not
a claim of token savings; tokenizer measurement remains a follow-up.

## E09 decision

`E09 = EXECUTABLE STRUCTURAL BASELINE / SHADOW`. The representative task now
has a repeatable bounded read-set. No production simplification is proposed
until a before/after replay uses the same task, model, and correctness rubric.
