# Structured Output Schema

Security review output should include:

- `executiveSummary`: overall risk level, key strengths, critical concerns, and confidence.
- `findings`: vulnerabilities with `id`, `severity`, `category`, `location`, `attackScenario`, `impact`, `recommendation`, and `confidence`.
- `standards`: relevant OWASP, CWE, NIST, or language/framework guidance when applicable.
- `remediationPlan`: prioritized fixes ordered by exploitability and impact.

Never include secrets or raw credential values in the response.
