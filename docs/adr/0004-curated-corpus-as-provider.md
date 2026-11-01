# ADR 0004: Treat the curated corpus as a search provider

Status: Accepted

## Context

Users may have reviewed PDF, text, or Markdown material that should participate in research without
creating a separate evidence path.

## Decision

Chunk and embed curated documents with FastEmbed, store them in ChromaDB with provenance metadata,
and expose retrieval through the same `SearchProvider` shape as web search with
`source_type="curated"`.

## Consequences

Ranking, extraction, audit, and quote verification remain shared across source types. The local
index is single-node and non-durable on an ephemeral free host unless external storage is added.
