# Structured Output Schema

Return a JSON-compatible unused code review with:

- `executiveSummary`: total unused elements, confidence summary, and cleanup risk overview.
- `unusedItems`: each item includes `id`, `symbol`, `kind`, `location`, `evidence`, `confidence`, `removalRisk`, and `recommendation`.
- `manualVerification`: dynamic references, public API surfaces, framework conventions, or tests that should be checked before deletion.
- `safeRemovalPlan`: ordered validation and cleanup steps.

Always separate high-confidence removals from uncertain candidates.
