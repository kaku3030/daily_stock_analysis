# Shared

Cross-product contracts belong here only after both Radar and Realtime Monitor consume them. The first migration deliberately keeps the existing implementations in place so their behavior does not change.

Likely future candidates are normalized market data, data-health states, evidence schemas, and common logging. Moving them requires contract tests at both callers first.
