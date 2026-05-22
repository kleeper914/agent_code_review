"""FastMCP server exposing AI Code Review tools."""

from __future__ import annotations

import json
import re
from typing import Any

from mcp.server.fastmcp import FastMCP

from ..orchestration.reports import format_review_result
from ..orchestration.service import ReviewService, ServiceAnalysisResult
from ..orchestration.types import ReviewOptions, ReviewResult

TOOL_NAMES = ("review", "code-review", "file-analysis", "git-analysis")


def create_mcp_server() -> FastMCP:
    server = FastMCP("ai-code-review")
    server.tool(name="review")(review)
    server.tool(name="code-review")(code_review)
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
    del debug, max_requests, timeout
    server = FastMCP(name)
    server.tool(name="review")(review)
    server.tool(name="code-review")(code_review)
    server.tool(name="file-analysis")(file_analysis)
    server.tool(name="git-analysis")(git_analysis)
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
        return _format_error("PR review is not implemented in the Python MCP phase 5 MVP.", outputFormat)
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
