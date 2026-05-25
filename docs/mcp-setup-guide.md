# MCP Setup Guide

The Python MCP server exposes the same public tool names targeted by the TypeScript MCP surface:

- `review`
- `code-review`
- `pr-review`
- `file-analysis`
- `git-analysis`

## Local Run

```bash
uv run agent-code-review mcp --name agent-code-review --max-requests 5 --timeout 300000
```

## Project MCP Config

```bash
uv run agent-code-review install
```

This writes `.mcp.json` with:

```json
{
  "mcpServers": {
    "agent-code-review": {
      "command": "agent-code-review",
      "args": ["mcp"]
    }
  }
}
```

## PR Review

The Python `pr-review` tool currently targets local git repositories. It compares `baseBranch...headBranch`, extracts changed files, and routes the review through the shared `ReviewService`.

Expected input:

- `repository`: local repository path
- `baseBranch`: base branch, default `main`
- `headBranch`: feature branch or current branch
- `reviewType`: any public review type, default `consolidated`
- `outputFormat`: `markdown` or `json`

Expected JSON output includes:

- `success`
- `content`
- `metadata.tool = "pr-review"`
- `metadata.changedFiles`
- `metadata.baseBranch`
- `metadata.headBranch`
