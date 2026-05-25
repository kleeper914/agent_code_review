# Structured Output Schema

Return a focused unused-code review with:

- `summary`: concise cleanup assessment and total candidate count.
- `highConfidenceRemovals`: candidates with direct evidence, `confidence`, `risk`, and validation commands.
- `needsManualReview`: uncertain candidates with false-positive risk notes.
- `defer`: items that look unused but should not be removed yet.

Prefer fewer, better-supported findings over broad speculative cleanup.
