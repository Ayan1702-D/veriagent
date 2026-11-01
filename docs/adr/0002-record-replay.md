# ADR 0002: Record external work and support offline replay

Status: Accepted

## Context

Live model and search calls are variable, rate-limited, and unavailable when free services fail.
Tests and demonstrations need deterministic behavior without spending provider quota.

## Decision

Store completed run artifacts and support replay that performs no model or network calls. Use
recorded evaluation artifacts for regression checks and seed three evidence-backed demonstration
runs at application startup.

## Consequences

CI and the demo can run offline, and regressions are reproducible. A replay is historical evidence,
not a fresh investigation; stored snapshots can become stale and must be labeled as such.
