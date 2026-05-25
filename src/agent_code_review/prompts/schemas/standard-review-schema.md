# Structured Output Schema

Return a structured review with these top-level sections:

- `executiveSummary`: concise assessment, strengths, critical concerns, overall score, and confidence.
- `findings`: ordered list of actionable findings with `id`, `title`, `severity`, `category`, `description`, `location`, `impact`, `recommendation`, `effort`, and `confidence`.
- `recommendations`: prioritized next steps grouped by urgency.

Use severity values `CRITICAL`, `HIGH`, `MEDIUM`, `LOW`, or `INFO`. Include file paths and line numbers when evidence is available.
