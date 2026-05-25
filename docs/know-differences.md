# Known Differences

Python `0.1.0` is the future-mainline path, but it is still a pre-1.0 validation release. TypeScript npm 4.x remains available while migration finishes.

## Python-only Extensions

- DeepSeek is first-class in Python through `deepseek:` model keys.
- OpenTelemetry facade support is available from the Python runtime.
- The memory and pattern database are JSON/JSONL-backed in this phase.

## Deferred Or Different Behavior

- `sync-github-projects` is recognized but returns a deferred compatibility message.
- `--interactive` is accepted and recorded, but structured interactive post-processing remains a later milestone.
- MCP `pr-review` supports local git branch diffs. Remote GitHub PR fetching is intentionally not part of Phase 12.
- Completion files are static generated artifacts, not Typer dynamic completion.

## Security Boundaries

- API keys are read from environment variables, project config, or explicit CLI flags.
- Example docs use placeholders only.
- Debug raw output strips prompt metadata before writing raw JSON.
- Plugin load failures sanitize local paths and secret-looking values before warnings are surfaced.
