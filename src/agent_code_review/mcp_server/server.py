"""FastMCP server exposing AI Code Review tools."""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from ..orchestration.reports import format_review_result
from ..orchestration.service import ReviewService, ServiceAnalysisResult
from ..orchestration.types import ReviewOptions, ReviewResult

TOOL_NAMES = ("review", "code-review", "pr-review", "file-analysis", "git-analysis")


@dataclass(frozen=True)
class MCPServerConfig:
    """Runtime MCP settings accepted by the Python CLI entrypoint."""

    name: str = "ai-code-review"
    debug: bool = False
    max_requests: int = 5
    timeout: int = 300000


def create_mcp_server(
    *,
    name: str = "ai-code-review",
    debug: bool = False,
    max_requests: int = 5,
    timeout: int = 300000,
) -> FastMCP:
    config = MCPServerConfig(
        name=name,
        debug=debug,
        max_requests=max_requests,
        timeout=timeout,
    )
    server = FastMCP(config.name)
    # FastMCP owns request handling internally; attaching sanitized config keeps CLI
    # parameters observable and testable without changing the transport contract.
    server.aicode_review_config = config  # type: ignore[attr-defined]
    server.tool(name="review")(review)
    server.tool(name="code-review")(code_review)
    server.tool(name="pr-review")(pr_review)
    server.tool(name="file-analysis")(file_analysis)
    server.tool(name="git-analysis")(git_analysis)
    return server


def run_mcp_server(
    *,
    name: str = "ai-code-review",
    debug: bool = False,
    max_requests: int = 5,
    timeout: int = 300000,
) -> int:
    server = create_mcp_server(
        name=name,
        debug=debug,
        max_requests=max_requests,
        timeout=timeout,
    )
    server.run("stdio")
    return 0


def review(
    target: str,
    context: str | None = None,
    reviewType: str = "quick-fixes",
    outputFormat: str = "json",
    model: str | None = None,
    options: dict[str, Any] | None = None,
) -> str:
    del context
    if _is_pr_target(target):
        return _format_error(
            "PR review is not implemented in the Python MCP phase 5 MVP.", outputFormat
        )
    return code_review(
        target=target,
        reviewType=reviewType,
        outputFormat=outputFormat,
        model=model,
        options=options,
    )


def code_review(
    target: str,
    reviewType: str = "quick-fixes",
    outputFormat: str = "markdown",
    model: str | None = None,
    includeTests: bool = False,
    includeProjectDocs: bool = True,
    language: str | None = None,
    framework: str | None = None,
    options: dict[str, Any] | None = None,
) -> str:
    try:
        review_options = _build_review_options(
            target=target,
            review_type=reviewType,
            output_format=outputFormat,
            model=model,
            include_tests=includeTests,
            include_project_docs=includeProjectDocs,
            language=language,
            framework=framework,
            options=options,
        )
        result = ReviewService().run_review(review_options)
        return _format_review(result, outputFormat)
    except Exception as exc:
        return _format_error(str(exc), outputFormat)


def pr_review(
    repository: str,
    prNumber: int | None = None,
    baseBranch: str = "main",
    headBranch: str | None = None,
    reviewType: str = "consolidated",
    focusAreas: list[str] | None = None,
    generateComments: bool = True,
    outputFormat: str = "markdown",
    model: str | None = None,
    options: dict[str, Any] | None = None,
) -> str:
    try:
        if _is_github_repository(repository):
            if prNumber is None:
                raise ValueError("PR number is required for GitHub repositories")
            raise ValueError(
                "GitHub PR analysis is not implemented yet. Use a local git repository path."
            )

        repo_path = Path(repository).expanduser().resolve()
        _git(repo_path, ["rev-parse", "--git-dir"])
        head = headBranch or _git(repo_path, ["rev-parse", "--abbrev-ref", "HEAD"]).strip()
        diff_content = _git(repo_path, ["diff", f"{baseBranch}...{head}"])
        changed_files = _extract_changed_files(diff_content)

        if not changed_files:
            return _format_analysis(
                ServiceAnalysisResult(
                    title="Pull Request Review",
                    content="No changes detected in the specified branch comparison.",
                    metadata={
                        "tool": "pr-review",
                        "repository": str(repo_path),
                        "baseBranch": baseBranch,
                        "headBranch": head,
                        "changedFiles": [],
                    },
                ),
                outputFormat,
            )

        review_options = ReviewOptions(
            target=str(repo_path),
            review_type=reviewType,  # type: ignore[arg-type]
            output=outputFormat,  # type: ignore[arg-type]
            model=model,
            include_tests=True,
            include_project_docs=True,
            return_only=True,
            quiet=True,
            **_allowed_review_overrides(dict(options or {})),
        )
        result = ReviewService().run_review(review_options)
        summary = _format_pr_summary(
            repository=str(repo_path),
            pr_number=prNumber,
            base_branch=baseBranch,
            head_branch=head,
            review_type=reviewType,
            focus_areas=focusAreas or [],
            generate_comments=generateComments,
            changed_files=changed_files,
            review_content=result.content,
        )
        return _format_analysis(
            ServiceAnalysisResult(
                title="Pull Request Review",
                content=summary,
                metadata={
                    "tool": "pr-review",
                    "repository": str(repo_path),
                    "prNumber": prNumber,
                    "baseBranch": baseBranch,
                    "headBranch": head,
                    "reviewType": reviewType,
                    "focusAreas": focusAreas or [],
                    "generateComments": generateComments,
                    "changedFiles": changed_files,
                    "reviewMetadata": result.metadata,
                },
            ),
            outputFormat,
        )
    except Exception as exc:
        return _format_error(str(exc), outputFormat)


def file_analysis(
    filePath: str,
    analysisType: str = "syntax",
    outputFormat: str = "markdown",
    model: str | None = None,
    language: str | None = None,
    framework: str | None = None,
    includeProjectDocs: bool = True,
    options: dict[str, Any] | None = None,
) -> str:
    try:
        result = ReviewService().run_file_analysis(
            file_path=filePath,
            analysis_type=analysisType,  # type: ignore[arg-type]
            output_format=outputFormat,
            model=model,
            language=language,
            framework=framework,
            include_project_docs=includeProjectDocs,
            options=options,
        )
        if isinstance(result, ReviewResult):
            return _format_review(result, outputFormat)
        return _format_analysis(result, outputFormat)
    except Exception as exc:
        return _format_error(str(exc), outputFormat)


def git_analysis(
    repository: str,
    commitCount: int = 50,
    branch: str | None = None,
    analysisType: str = "commits",
    since: str | None = None,
    until: str | None = None,
    outputFormat: str = "markdown",
) -> str:
    try:
        result = ReviewService().run_git_analysis(
            repository=repository,
            analysis_type=analysisType,  # type: ignore[arg-type]
            commit_count=commitCount,
            branch=branch,
            since=since,
            until=until,
        )
        return _format_analysis(result, outputFormat)
    except Exception as exc:
        return _format_error(str(exc), outputFormat)


def _build_review_options(
    *,
    target: str,
    review_type: str,
    output_format: str,
    model: str | None,
    include_tests: bool,
    include_project_docs: bool,
    language: str | None,
    framework: str | None,
    options: dict[str, Any] | None,
) -> ReviewOptions:
    merged = dict(options or {})
    # MCP 保持 TypeScript 兼容的 camelCase 入参；进入 orchestration 前统一转换。
    return ReviewOptions(
        target=target,
        review_type=review_type,  # type: ignore[arg-type]
        output=output_format,  # type: ignore[arg-type]
        model=model,
        include_tests=include_tests,
        include_project_docs=include_project_docs,
        language=language,
        framework=framework,
        quiet=True,
        **_allowed_review_overrides(merged),
    )


def _allowed_review_overrides(options: dict[str, Any]) -> dict[str, Any]:
    mapping = {
        "outputDir": "output_dir",
        "includeDependencyAnalysis": "include_dependency_analysis",
        "multiPass": "multi_pass",
        "forceSinglePass": "force_single_pass",
        "batchTokenLimit": "batch_token_limit",
        "enableSemanticChunking": "enable_semantic_chunking",
        "useMemory": "use_memory",
        "skipKeyCheck": "skip_key_check",
        "apiKeys": "api_keys",
    }
    normalized = {mapping.get(key, key): value for key, value in options.items()}
    allowed = {
        "output_dir",
        "include_dependency_analysis",
        "estimate",
        "multi_pass",
        "force_single_pass",
        "context_maintenance_factor",
        "batch_token_limit",
        "enable_semantic_chunking",
        "diagram",
        "use_memory",
        "debug",
        "verbose",
        "quiet",
        "log_level",
        "skip_key_check",
        "api_keys",
    }
    return {key: value for key, value in normalized.items() if key in allowed}


def _format_review(result: ReviewResult, output_format: str) -> str:
    return format_review_result(result, _normalize_output_format(output_format))


def _format_analysis(result: ServiceAnalysisResult, output_format: str) -> str:
    output_format = _normalize_output_format(output_format)
    if output_format == "json":
        return json.dumps(
            {
                "success": True,
                "title": result.title,
                "content": result.content,
                "timestamp": result.timestamp,
                "metadata": result.metadata,
            },
            indent=2,
            ensure_ascii=False,
        )

    metadata = "\n".join(
        f"**{key}:** `{value}`  " for key, value in result.metadata.items() if value is not None
    )
    return f"# {result.title}\n\n{metadata}\n\n---\n\n{result.content}\n"


def _format_error(message: str, output_format: str) -> str:
    safe_message = _redact_error(message)
    if _normalize_output_format(output_format) == "json":
        return json.dumps({"success": False, "error": safe_message}, indent=2, ensure_ascii=False)
    return f"Error: {safe_message}"


def _normalize_output_format(output_format: str) -> str:
    return "json" if output_format == "json" else "markdown"


def _is_pr_target(target: str) -> bool:
    return bool(re.search(r"^(PR[#\s]*\d+)$|github\.com|/pull/\d+|pull/\d+", target, re.I))


def _is_github_repository(repository: str) -> bool:
    return repository.startswith(("http://", "https://")) and "github.com" in repository


def _git(repo_path: Path, args: list[str]) -> str:
    if not repo_path.exists() or not repo_path.is_dir():
        raise ValueError(f"Repository not found: {repo_path}")
    completed = subprocess.run(
        ["git", *args],
        cwd=repo_path,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise ValueError(completed.stderr.strip() or completed.stdout.strip() or "git failed")
    return completed.stdout.strip()


def _extract_changed_files(diff_content: str) -> list[str]:
    files: list[str] = []
    for line in diff_content.splitlines():
        if not line.startswith("diff --git"):
            continue
        match = re.match(r"diff --git a/(.+) b/(.+)", line)
        if match:
            files.append(match.group(2))
    return files


def _format_pr_summary(
    *,
    repository: str,
    pr_number: int | None,
    base_branch: str,
    head_branch: str,
    review_type: str,
    focus_areas: list[str],
    generate_comments: bool,
    changed_files: list[str],
    review_content: str,
) -> str:
    lines = [
        "# Pull Request Review",
        "",
        f"**Repository:** {repository}",
        f"**Base Branch:** {base_branch}",
        f"**Head Branch:** {head_branch}",
        f"**Review Type:** {review_type}",
        f"**Timestamp:** {datetime.now(timezone.utc).isoformat()}",
        "",
    ]
    if pr_number is not None:
        lines.insert(3, f"**PR Number:** #{pr_number}")
    if focus_areas:
        lines.extend(["**Focus Areas:** " + ", ".join(focus_areas), ""])
    lines.extend([f"## Changed Files ({len(changed_files)})", ""])
    lines.extend(f"- `{file}`" for file in changed_files)
    lines.extend(["", "## Review Results", "", review_content])
    if generate_comments:
        lines.extend(
            [
                "",
                "## Review Comments",
                "",
                "Line-specific comments are represented by the review findings above.",
            ]
        )
    return "\n".join(lines)


def _redact_error(message: str) -> str:
    safe = re.sub(
        r"(?i)((?:api[_-]?key|token|secret|password|credential|raw_prompt|prompt)\s*=\s*)\S+",
        r"\1[REDACTED]",
        message,
    )
    safe = re.sub(r"(?i)(sk-[A-Za-z0-9_-]+)", "[REDACTED]", safe)
    return safe


mcp = create_mcp_server()


if __name__ == "__main__":
    mcp.run("stdio")
