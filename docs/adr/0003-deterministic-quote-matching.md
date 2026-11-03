# ADR 0003: Verify quotations with deterministic text matching

Status: Accepted

## Context

Model-generated quotations can be altered or invented. A citation should not support a finding
unless the quoted text can be located in the stored source snapshot.

## Decision

Normalize text and use deterministic fuzzy quote matching against the stored snapshot. Apply the
same rule to web and curated-corpus sources, and store the verification result on each evidence
item. The default fuzzy threshold comes from `QUOTE_MATCH_THRESHOLD`; callers may explicitly
supply a threshold. Numeric tokens (including signs, decimal points, and digit grouping) must
match exactly within the candidate span even when surrounding prose passes the fuzzy threshold.

Evidence IDs remain stable across research loops. Identical quotes from different sources retain
separate identities. Verdict eligibility uses only verified evidence IDs linked to each finding:
`SUPPORTED` requires supporting evidence, `REFUTED` contradicting evidence, `MIXED` both, and
`CONDITIONAL` at least one linked verified quote. Entailment decisions stay local to the finding.
The report derives its verdict from these calibrated findings and cites only their linked,
verified sources. Any insufficient finding prevents an overall `SUPPORTED` verdict.

## Consequences

Quote provenance can be tested and reproduced without another model call. Matching proves textual
presence only; it does not prove that the source is correct, independent, or that the quotation
logically entails the claim.
