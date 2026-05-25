# CLI Compatibility Matrix

Python `0.1.0` accepts the TypeScript public review type surface and the main migration subcommands. Commands that are not fully remote-service equivalent return an explicit compatibility message instead of being parser errors.

## Review Types

| Review type | Python status | Notes |
| --- | --- | --- |
| `quick-fixes` | Supported | Dedicated strategy. |
| `architectural` | Supported | Includes diagram and dependency output paths. |
| `security` | Supported | Dedicated strategy plus dependency analysis support. |
| `performance` | Supported | Dedicated strategy. |
| `unused-code` | Supported | Supports `--focused` and `--trace-code`. |
| `focused-unused-code` | Supported | Public type and focused variant route. |
| `code-tracing-unused-code` | Supported | Public type and trace variant route. |
| `consolidated` | Supported | Used by multi-pass and PR review consolidation. |
| `best-practices` | Supported | Compatibility strategy and resource templates. |
| `evaluation` | Supported | Coding assessment options are accepted. |
| `extract-patterns` | Supported | Dedicated validator and pattern metadata. |
| `coding-test` | Supported | Coding-test config and AI detection options. |
| `ai-integration` | Supported | Compatibility strategy and schema resources. |
| `cloud-native` | Supported | Compatibility strategy and schema resources. |
| `developer-experience` | Supported | Compatibility strategy and schema resources. |
| `comprehensive` | Supported | Compatibility strategy and common template. |

## Subcommands

| Subcommand | Python status | Expected behavior |
| --- | --- | --- |
| `generate-config` | Supported | Writes YAML or JSON sample config; refuses overwrite unless `--force`. |
| `validate-config` | Supported | Validates selected model API key without leaking configured values. |
| `init` | Supported | Creates `.ai-code-review/config.yaml`. |
| `install` | Supported | Creates project-level `.mcp.json`. |
| `test-build` | Supported | Prints local model/review-type registry smoke data. |
| `sync-github-projects` | Recognized | Returns a clear deferred message. |
| `mcp` | Supported | Starts FastMCP server with runtime config. |
| `plugins list` | Supported | Lists built-in and loaded plugins. |
| `prompt-feedback` | Supported | Adds, lists, selects, and optimizes prompt feedback. |
| `test-model` | Supported | Runs selected model smoke prompt. |

## Common Root Options

| Option | Python status |
| --- | --- |
| `--type`, `-t` | Supported |
| `--output`, `-o` | Supported for `markdown` and `json` |
| `--model`, `-m` | Supported |
| `--writer-model` | Supported for consolidation |
| `--language` | Supported |
| `--framework` | Supported |
| `--interactive` | Accepted with compatibility warning |
| `--test-api` | Supported |
| `--stdout` | Supported; skips report file output |
| `--models`, `--listmodels` | Supported |
