# ADR-009 — Local AI with human review

November 17, 2026. Prepared in Phase 0, with the first inference slice in Phase 6.

## Context

Real financial data must stay out of external LLM services.

## Decision

Keep Ollama on the internal AI network with `OLLAMA_NO_CLOUD=1` and unpublished
ports. The dashboard API joins that network and calls only the fixed local
Ollama endpoint. Present validated categories for human approval.

## Alternatives

Remote APIs conflict with the privacy boundary. Runtime model downloads require egress.

## Consequences

Download model files in a dedicated temporary container with no access to the
Lake, database, or API secrets. Runtime inference uses bounded batches and a
process-local cache. Acceptance uses the same merchant rule as a manual edit.
