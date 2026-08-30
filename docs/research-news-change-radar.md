# Research news and catalyst change radar

The US research scan stores point-in-time snapshots of the existing `dsa_news`, `llm_catalysts`, and `llm_risks` evidence. Adjacent snapshots are compared deterministically. This radar changes research-review urgency only; it does not issue trade instructions or infer that a catalyst is bullish or a risk is a sell signal.

## Persistence and deduplication

Each selected symbol receives one idempotent row per `market`, `code`, and `run_id` in `research_candidate_event_snapshots`. The row preserves catalyst text, risk text, news evidence, and stable fingerprints.

Text is normalized with Unicode NFKC, case folding, punctuation removal, common connective-word removal, token deduplication, and token ordering before hashing. This makes superficial rewrites such as “AI demand remains strong” and “Strong AI demand continues” share a fingerprint. It is intentionally conservative and does not use an LLM for semantic classification.

## Change states

- `new_catalyst`: a catalyst fingerprint is present now but not in the prior snapshot.
- `new_risk`: a risk fingerprint is present now but not in the prior snapshot. Severity is assigned by a small deterministic keyword policy.
- `resolved_or_missing`: a prior catalyst or risk is absent now. This means “recheck the evidence,” not “confirmed resolved.”
- `unchanged`: no fingerprint set changed. The first observation is a non-alerting baseline.

Repeated news or LLM wording with the same fingerprint does not increase research priority again. New change attention contributes a bounded bonus to the existing research-priority score and still passes through the existing transition and notification gates.

## Outputs

The daily scan writes:

- `reports/screening/us_research_news_change_radar.json`
- `reports/screening/us_research_news_change_radar.md`

The candidate-pool JSON also includes the latest `news_change` sidecar. Missing or degraded event evidence remains explicit; no facts are invented.

