# Structured Output Schema

Return a developer or project evaluation with:

- `overallAssessment`: score, readiness, level, and short rationale.
- `criteriaScores`: requirement coverage, correctness, code quality, architecture, testing, performance, security, and documentation.
- `evidence`: code-backed observations for each score.
- `redFlags`: risks that affect acceptance or hiring decisions.
- `strengths`: evidence-backed positive indicators.
- `decision`: pass, fail, hire, no-hire, or needs-follow-up with rationale.

Do not provide broad refactoring advice unless it directly supports the evaluation.
