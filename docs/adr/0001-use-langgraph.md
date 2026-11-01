# ADR 0001: Use LangGraph for verification orchestration

Status: Accepted

## Context

Verification has ordered stages, bounded correction loops, shared state, and audit requirements.
A single prompt would make stage boundaries and budget enforcement difficult to inspect.

## Decision

Represent the planner, researcher, extractor, contradiction checker, verifier, and reporter as a
LangGraph workflow. Keep domain state in typed models and inject model, retrieval, budget, and audit
dependencies.

## Consequences

The execution path is explicit and testable with `FakeLLM`. LangGraph adds a dependency and its
version changes can affect graph APIs, so upgrades require the full replay and graph test suite.
