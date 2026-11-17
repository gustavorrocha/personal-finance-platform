# ADR-001 — Python and TypeScript monorepo

November 17, 2026. Accepted in Phase 0.

## Context

The API and future domain code need explicit boundaries and reproducible checks.

## Decision

Use uv workspaces for the API and Lake and npm for React. Ruff, Pytest, and CI use synthetic data.

## Alternatives

Separate repositories would duplicate operations. A workspace does not require a service per package.

## Consequences

Keep uv.lock and package-lock.json current. Implement modules in their planned phases.
