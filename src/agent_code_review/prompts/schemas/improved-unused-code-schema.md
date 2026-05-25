# Structured Output Schema

Return an improved unused-code report with:

- `summary`: counts by unused kind, risk, and confidence.
- `findings`: candidates with `id`, `kind`, `name`, `location`, `evidence`, `referencesChecked`, `confidence`, `risk`, and `recommendation`.
- `dependencySignals`: tool or dependency evidence considered.
- `safeCleanupScript`: optional ordered cleanup actions, not destructive by default.
- `validation`: tests, builds, or search commands to run before removal.

Prefer conservative recommendations when references may be dynamic.
