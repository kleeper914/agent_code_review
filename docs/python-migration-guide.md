# Python Migration Guide

当前 `0.1.0` 是 pre-1.0 最终验收版本，用于证明 Python CLI、Prompt、模型注册、MCP、插件、memory、测试、构建和发布路径已经形成闭环。

## Install And Run

From this directory:

```bash
uv sync
uv run agent-code-review --models
uv run agent-code-review . --type security --model openai:gpt-5.5 --openai-api-key "$AGENT_CODE_REVIEW_OPENAI_API_KEY"
```

The package exposes both console scripts:

- `agent-code-review`

## Quality Gates

Phase 12 fixes the single-path Python delivery workflow:

```bash
uv run pytest
uv run ruff check
uv run ruff format --check
uv run mypy src tests
uv build
```

These commands replace the TypeScript package's `pnpm run test`, `pnpm run lint`, `pnpm run format:check`, `pnpm run build:types`, and `pnpm run build` for the Python project.

## Migration Position

- Python `0.1.0` is the future-mainline migration target.
- Python keeps compatibility aliases and explicit deferred messages for commands that are recognized but not yet remote-service complete.
- Python-only extensions, such as DeepSeek support and OpenTelemetry facade wiring, are documented in `known-differences.md`.

## Completion Installation

Generated shell completions live in `completions/`.

```bash
# bash
source completions/ai-code-review.bash

# zsh
fpath=("$PWD/completions" $fpath)
autoload -Uz compinit && compinit

# fish
cp completions/ai-code-review.fish ~/.config/fish/completions/
```

Regenerate after CLI type or option changes:

```bash
uv run python scripts/generate_completions.py
```
