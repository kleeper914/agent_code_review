"""Shared review service used by CLI and MCP integrations."""

from __future__ import annotations

import re
import subprocess
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from ..config import ResolvedConfig
from ..observability import get_observability
from ..runtime import RuntimeContext

from .orchestrator import run_review as run_orchestrated_review
from .types import ReviewOptions, ReviewResult

FileAnalysisType = Literal["syntax", "complexity", "security", "performance", "patterns"]
GitAnalysisType = Literal["commits", "changes", "patterns", "quality"]

ANALYSIS_REVIEW_TYPE_MAP = {
    "syntax": "quick-fixes",
    "security": "security",
    "performance": "performance",
    "patterns": "extract-patterns",
}


class ServiceAnalysisResult(BaseModel):
    """Structured non-LLM analysis result for MCP and future platform surfaces."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    title: str
    content: str
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    metadata: dict[str, Any] = Field(default_factory=dict)


class ReviewService:
    """Single application service reused by CLI and MCP tools."""

    def run_review(
        self,
        options: ReviewOptions,
        config: ResolvedConfig | None = None,
        runtime: RuntimeContext | None = None,
    ) -> ReviewResult:
        with get_observability().start_span(
            "service.run_review",
            {"review_type": options.review_type, "target": options.target},
        ):
            return run_orchestrated_review(options, config, runtime)

    def run_file_analysis(
        self,
        *,
        file_path: str,
        analysis_type: FileAnalysisType = "syntax",
        output_format: str = "markdown",
        model: str | None = None,
        language: str | None = None,
        framework: str | None = None,
        include_project_docs: bool = True,
        options: dict[str, Any] | None = None,
    ) -> ReviewResult | ServiceAnalysisResult:
        with get_observability().start_span(
            "service.run_file_analysis",
            {"analysis_type": analysis_type, "file_path": file_path},
        ):
            return self._run_file_analysis_inner(
                file_path=file_path,
                analysis_type=analysis_type,
                output_format=output_format,
                model=model,
                language=language,
                framework=framework,
                include_project_docs=include_project_docs,
                options=options,
            )

    def _run_file_analysis_inner(
        self,
        *,
        file_path: str,
        analysis_type: FileAnalysisType,
        output_format: str,
        model: str | None,
        language: str | None,
        framework: str | None,
        include_project_docs: bool,
        options: dict[str, Any] | None,
    ) -> ReviewResult | ServiceAnalysisResult:
        resolved_path = Path(file_path).expanduser().resolve()
        if not resolved_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        if not resolved_path.is_file():
            raise ValueError(f"Path is not a file: {file_path}")

        if analysis_type == "complexity":
            return self._analyze_complexity(resolved_path, language)

        try:
            review_type = ANALYSIS_REVIEW_TYPE_MAP[analysis_type]
        except KeyError as exc:
            raise ValueError(f"Unsupported file analysis type: {analysis_type}") from exc

        merged_options = dict(options or {})
        review_options = ReviewOptions(
            target=file_path,
            review_type=review_type,  # type: ignore[arg-type]
            output=output_format,  # type: ignore[arg-type]
            model=model,
            language=language,
            framework=framework,
            include_tests=False,
            include_project_docs=include_project_docs,
            quiet=True,
            **_review_option_overrides(merged_options),
        )
        return self.run_review(review_options)

    def run_git_analysis(
        self,
        *,
        repository: str,
        analysis_type: GitAnalysisType = "commits",
        commit_count: int = 50,
        branch: str | None = None,
        since: str | None = None,
        until: str | None = None,
    ) -> ServiceAnalysisResult:
        with get_observability().start_span(
            "service.run_git_analysis",
            {"analysis_type": analysis_type, "repository": repository},
        ):
            return self._run_git_analysis_inner(
                repository=repository,
                analysis_type=analysis_type,
                commit_count=commit_count,
                branch=branch,
                since=since,
                until=until,
            )

    def _run_git_analysis_inner(
        self,
        *,
        repository: str,
        analysis_type: GitAnalysisType,
        commit_count: int,
        branch: str | None,
        since: str | None,
        until: str | None,
    ) -> ServiceAnalysisResult:
        repo_path = Path(repository).expanduser().resolve()
        if not repo_path.exists() or not repo_path.is_dir():
            raise ValueError(f"Repository not found: {repository}")
        self._git(repo_path, ["rev-parse", "--git-dir"])

        commits = self._load_commits(repo_path, commit_count, branch, since, until)
        if analysis_type == "commits":
            content = self._format_commit_analysis(commits)
        elif analysis_type == "changes":
            content = self._format_change_analysis(repo_path, commit_count, branch, since, until)
        elif analysis_type == "patterns":
            content = self._format_pattern_analysis(commits)
        elif analysis_type == "quality":
            content = self._format_quality_analysis(repo_path, commit_count, branch, since, until)
        else:
            raise ValueError(f"Unsupported git analysis type: {analysis_type}")

        return ServiceAnalysisResult(
            title="Git Repository Analysis",
            content=content,
            metadata={
                "repository": str(repo_path),
                "analysisType": analysis_type,
                "commitCount": len(commits),
                "requestedCommitCount": commit_count,
                "branch": branch,
                "since": since,
                "until": until,
            },
        )

    def _analyze_complexity(
        self, file_path: Path, language: str | None = None
    ) -> ServiceAnalysisResult:
        content = file_path.read_text(encoding="utf-8", errors="replace")
        lines = content.splitlines()
        non_empty = [line for line in lines if line.strip()]
        comment_lines = [line for line in lines if _is_comment_line(line)]
        detected_language = language or _language_for_path(file_path)
        function_count = _count_functions(content, detected_language)
        class_count = _count_classes(content, detected_language)

        report = "\n".join(
            [
                "## Code Complexity Analysis",
                "",
                f"- Total lines: {len(lines)}",
                f"- Non-empty lines: {len(non_empty)}",
                f"- Comment lines: {len(comment_lines)}",
                f"- Code lines: {max(len(non_empty) - len(comment_lines), 0)}",
                f"- Function or method declarations: {function_count}",
                f"- Class declarations: {class_count}",
            ]
        )
        return ServiceAnalysisResult(
            title="File Analysis Results",
            content=report,
            metadata={
                "filePath": str(file_path),
                "analysisType": "complexity",
                "language": detected_language,
                "fileSize": file_path.stat().st_size,
                "lineCount": len(lines),
                "nonEmptyLineCount": len(non_empty),
                "commentLineCount": len(comment_lines),
                "functionCount": function_count,
                "classCount": class_count,
            },
        )

    def _load_commits(
        self,
        repo_path: Path,
        commit_count: int,
        branch: str | None,
        since: str | None,
        until: str | None,
    ) -> list[dict[str, str]]:
        args = [
            "log",
            "--pretty=format:%H%x1f%s%x1f%ai%x1f%an%x1f%ae",
            "-n",
            str(max(commit_count, 0)),
        ]
        if branch:
            args.append(branch)
        if since:
            args.append(f"--since={since}")
        if until:
            args.append(f"--until={until}")
        output = self._git(repo_path, args)
        commits: list[dict[str, str]] = []
        for line in output.splitlines():
            parts = line.split("\x1f")
            if len(parts) < 5:
                continue
            commits.append(
                {
                    "hash": parts[0],
                    "message": parts[1],
                    "date": parts[2],
                    "author": parts[3],
                    "email": parts[4],
                }
            )
        return commits

    def _format_commit_analysis(self, commits: list[dict[str, str]]) -> str:
        lines = ["## Commit History Analysis", "", f"Total commits analyzed: {len(commits)}", ""]
        if not commits:
            lines.append("No commits found in the requested range.")
            return "\n".join(lines)
        authors = Counter(commit["author"] for commit in commits)
        lines.extend(["### Top Contributors", ""])
        for author, count in authors.most_common(5):
            lines.append(f"- **{author}**: {count} commits")
        lines.extend(["", "### Recent Activity", ""])
        for commit in commits[:10]:
            lines.append(
                f"- `{commit['hash'][:8]}` {commit['message']} - "
                f"{commit['author']} ({commit['date'][:10]})"
            )
        return "\n".join(lines)

    def _format_change_analysis(
        self,
        repo_path: Path,
        commit_count: int,
        branch: str | None,
        since: str | None,
        until: str | None,
    ) -> str:
        files = self._changed_files(repo_path, commit_count, branch, since, until)
        lines = ["## File Changes Analysis", "", f"Total files changed: {len(files)}", ""]
        lines.extend(["### Most Frequently Changed Files", ""])
        for file_name, count in files.most_common(10):
            lines.append(f"- `{file_name}`: {count} changes")
        if not files:
            lines.append("No changed files found in the requested range.")
        return "\n".join(lines)

    def _format_pattern_analysis(self, commits: list[dict[str, str]]) -> str:
        prefixes: Counter[str] = Counter()
        for commit in commits:
            match = re.match(r"([a-zA-Z]+)(?:\(.+\))?:", commit["message"])
            prefixes[match.group(1).lower() if match else "unclassified"] += 1
        lines = ["## Development Patterns Analysis", "", "### Commit Message Patterns", ""]
        for prefix, count in prefixes.most_common():
            lines.append(f"- **{prefix}**: {count} commits")
        if not commits:
            lines.append("No commits found in the requested range.")
        return "\n".join(lines)

    def _format_quality_analysis(
        self,
        repo_path: Path,
        commit_count: int,
        branch: str | None,
        since: str | None,
        until: str | None,
    ) -> str:
        files = self._changed_files(repo_path, commit_count, branch, since, until)
        test_files = sum(count for file, count in files.items() if _looks_like_test_file(file))
        docs_files = sum(count for file, count in files.items() if file.lower().endswith(".md"))
        lines = [
            "## Repository Quality Signals",
            "",
            f"- Files touched: {len(files)}",
            f"- Test-file changes: {test_files}",
            f"- Documentation changes: {docs_files}",
            "",
            "These lightweight signals are deterministic MCP-safe summaries; deep quality review "
            "should use the code-review tool.",
        ]
        return "\n".join(lines)

    def _changed_files(
        self,
        repo_path: Path,
        commit_count: int,
        branch: str | None,
        since: str | None,
        until: str | None,
    ) -> Counter[str]:
        args = ["log", "--name-only", "--pretty=format:%H%x1f%s", "-n", str(max(commit_count, 0))]
        if branch:
            args.append(branch)
        if since:
            args.append(f"--since={since}")
        if until:
            args.append(f"--until={until}")
        output = self._git(repo_path, args)
        files: Counter[str] = Counter()
        for line in output.splitlines():
            stripped = line.strip()
            if not stripped or "\x1f" in stripped:
                continue
            files[stripped] += 1
        return files

    def _git(self, repo_path: Path, args: list[str]) -> str:
        # 这里必须使用 argv list 且 shell=False，避免 MCP 入参被拼进 shell 字符串。
        completed = subprocess.run(
            ["git", *args],
            cwd=repo_path,
            check=False,
            capture_output=True,
            text=True,
        )
        if completed.returncode != 0:
            message = completed.stderr.strip() or completed.stdout.strip() or "git command failed"
            raise ValueError(message)
        return completed.stdout.strip()


def _review_option_overrides(options: dict[str, Any]) -> dict[str, Any]:
    allowed = {
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
    return {key: value for key, value in options.items() if key in allowed}


def _language_for_path(path: Path) -> str:
    return {
        ".ts": "typescript",
        ".tsx": "typescript",
        ".js": "javascript",
        ".jsx": "javascript",
        ".py": "python",
        ".rb": "ruby",
        ".go": "go",
        ".rs": "rust",
        ".java": "java",
        ".php": "php",
    }.get(path.suffix.lower(), path.suffix.lower().lstrip(".") or "unknown")


def _is_comment_line(line: str) -> bool:
    stripped = line.strip()
    return stripped.startswith(("#", "//", "/*", "*"))


def _count_functions(content: str, language: str) -> int:
    if language == "python":
        return len(re.findall(r"^\s*def\s+\w+\s*\(", content, flags=re.MULTILINE))
    return len(
        re.findall(
            r"\bfunction\s+\w+\s*\(|\bconst\s+\w+\s*=\s*\(|\bfunc\s+\w+\s*\(",
            content,
        )
    )


def _count_classes(content: str, language: str) -> int:
    if language == "python":
        return len(re.findall(r"^\s*class\s+\w+", content, flags=re.MULTILINE))
    return len(re.findall(r"\bclass\s+\w+", content))


def _looks_like_test_file(path: str) -> bool:
    name = Path(path).name.lower()
    return (
        "test" in name
        or "spec" in name
        or "/tests/" in f"/{path.lower()}/"
        or "/__tests__/" in f"/{path.lower()}/"
    )
