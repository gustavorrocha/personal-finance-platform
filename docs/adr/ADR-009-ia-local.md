# ADR-009 — Local AI with human review

November 17, 2026. Prepared in Phase 0, inference planned for Phase 6.

## Context

Real financial data must stay out of external LLM services.

## Decision

Keep Ollama on the internal AI network with OLLAMA_NO_CLOUD=1 and unpublished ports. Introduce the model and consumer in Phase 6.

## Alternatives

Remote APIs conflict with the privacy boundary. Runtime model downloads require egress.

## Consequences

Bootstrap models separately. Treat output as untrusted, validate it, and route it for review.
