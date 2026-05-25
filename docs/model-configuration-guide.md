# Model Configuration Guide

Models use the same `provider:model`.

```bash
uv run agent-code-review --models
uv run agent-code-review . --model deepseek:deepseek-v4-pro
uv run agent-code-review . --model openai:gpt-5.5 --writer-model openai:gpt-5.5
```

## API Keys

Use provider-specific environment variables or CLI flags:

```bash
export AGENT_CODE_REVIEW_GOOGLE_API_KEY=your_google_api_key_here
export AGENT_CODE_REVIEW_OPENAI_API_KEY=your_openai_api_key_here
export AGENT_CODE_REVIEW_ANTHROPIC_API_KEY=your_anthropic_api_key_here
export AGENT_CODE_REVIEW_OPENROUTER_API_KEY=your_openrouter_api_key_here
export AGENT_CODE_REVIEW_DEEPSEEK_API_KEY=your_deepseek_api_key_here
```

CLI flags are available for local smoke tests:

```bash
uv run agent-code-review test-model --model openai:gpt-5.5 --openai-api-key "$AGENT_CODE_REVIEW_OPENAI_API_KEY"
```

## Metadata And Cost

The enhanced registry stores:

- provider
- display name
- context window
- output limit
- pricing
- status
- capabilities
- tool support

When providers return token usage, the Python client estimates input, output, and total cost and includes the values in review metadata.

## Unknown Models

Unknown provider models fall back to provider defaults. OpenRouter models also use vendor/model pattern inference where possible. Warnings are emitted through runtime metadata rather than leaking prompt or key content.
