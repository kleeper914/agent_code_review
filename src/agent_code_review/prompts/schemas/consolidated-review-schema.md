# Structured Output Schema

Return a consolidated review object with:

- `review.version`: use `"1.0"`.
- `review.executiveSummary`: holistic project assessment.
- `review.overallGrade`: academic grade from `A+` through `F`.
- `review.gradeCategories`: functionality, code quality, documentation, testing, maintainability, security, and performance.
- `review.issues`: grouped `high`, `medium`, and `low` findings.
- `review.strengths`: positive patterns worth preserving.
- `review.architecturalInsights`: optional cross-file design insights.
- `review.recommendations`: immediate, short-term, and long-term actions.

Deduplicate overlapping findings and preserve the strongest evidence.
