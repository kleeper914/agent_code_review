# Structured Output Schema

Return a JSON-compatible quick fixes review with:

- `executiveSummary`: include `totalIssuesFound`, `highPriorityFixes`, `estimatedFixTime`, `impactLevel`, and `confidenceScore`.
- `quickFixes`: list each issue with `id`, `title`, `category`, `priority`, `effort`, `confidence`, `location`, `issue`, `impact`, `fix`, and `validation`.
- `prioritizedSummary`: include `immediate`, `shortTerm`, and `whenTimePermits`.
- `patterns`: include repeated issues and code smells.
- `metrics`: include expected code quality, maintainability, performance, and bug-risk impact.

Use `quickFixes` as the issue array key.
