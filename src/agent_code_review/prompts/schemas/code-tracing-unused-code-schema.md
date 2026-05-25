# Structured Output Schema

Return a code-tracing unused-code review with:

- `traceSummary`: entry points, imports, exports, dynamic references, tests, and framework hooks considered.
- `traceFindings`: each finding includes `symbol`, `definition`, `referenceTrace`, `confidence`, `falsePositiveRisk`, and `recommendation`.
- `assumptions`: tracing assumptions and unresolved references.
- `validationPlan`: concrete commands or manual checks needed before deletion.

Do not mark code removable without trace evidence.
