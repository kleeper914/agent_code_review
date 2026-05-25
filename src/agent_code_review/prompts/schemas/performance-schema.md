# Structured Output Schema

Performance review output should include:

- `executiveSummary`: performance posture, likely bottlenecks, and confidence.
- `findings`: issues with `id`, `severity`, `category`, `location`, `impact`, `measurementSuggestion`, `recommendation`, and `effort`.
- `quickWins`: low-risk optimizations.
- `measurementPlan`: benchmarks, profiling, or runtime metrics needed to validate changes.

State assumptions when performance impact is inferred rather than measured.
