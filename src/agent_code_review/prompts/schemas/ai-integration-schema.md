# Structured Output Schema

AI integration review output should include:

- `executiveSummary`: model integration risk, reliability posture, and cost/privacy concerns.
- `findings`: issues with prompts, context, provider boundaries, retries, fallbacks, evaluation, observability, or data handling.
- `safetyControls`: recommended privacy, prompt, tool, and output validation controls.
- `operationalControls`: cost, rate limit, monitoring, and fallback recommendations.

Do not expose prompt secrets, keys, tokens, or private data.
