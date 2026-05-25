# Structured Output Schema

Cloud-native review output should include:

- `executiveSummary`: deployment readiness, operational strengths, and production risks.
- `findings`: issues with configuration, secrets, scaling, resilience, observability, security, or portability.
- `runtimeAssumptions`: environment, dependency, and infrastructure assumptions that should be documented.
- `mitigations`: concrete platform, deployment, or code changes.

Tie every recommendation to an operational risk.
