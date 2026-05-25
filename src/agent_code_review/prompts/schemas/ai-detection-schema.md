# Structured Output Schema

Return AI detection context with:

- `isAIGenerated`: boolean or unknown.
- `confidenceScore`: number from 0.0 to 1.0.
- `patternsDetected`: specific signals and locations.
- `humanSignals`: evidence of manual problem-solving or project-specific judgment.
- `riskLevel`: `LOW`, `MEDIUM`, `HIGH`, or `CRITICAL`.
- `limitations`: reasons the assessment may be uncertain.

Avoid claiming authorship certainty without strong evidence.
