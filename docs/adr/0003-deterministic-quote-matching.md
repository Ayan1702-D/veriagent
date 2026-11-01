# ADR 0003: Verify quotations with deterministic text matching

Status: Accepted

## Context

Model-generated quotations can be altered or invented. A citation should not support a finding
unless the quoted text can be located in the stored source snapshot.

## Decision

Normalize text and use deterministic fuzzy quote matching against the stored snapshot. Apply the
same rule to web and curated-corpus sources, and store the verification result on each evidence
item.

## Consequences

Quote provenance can be tested and reproduced without another model call. Matching proves textual
presence only; it does not prove that the source is correct, independent, or that the quotation
logically entails the claim.
