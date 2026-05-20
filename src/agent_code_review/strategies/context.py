from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

from ..discovery import ProjectContext
from ..orchestration.types import ReviewOptions

from .base import ContextSection


DEPENDENCY_FILES = (
    "package.json",
    "pnpm-lock.yaml",
    "package-lock.json",
    "yarn.lock",
    "requirements.txt",
    "pyproject.toml",
    "poetry.lock",
    "Pipfile",
    "Gemfile",
    "go.mod",
    "Cargo.toml",
    "pubspec.yaml"
)


def dependency_sections(context: ProjectContext, include_details: bool | None) -> list[ContextSection]:
    if include_details is False:
        return []
    
    sections: list[ContextSection] = []
    found: list[str] = []
    for name in DEPENDENCY_FILES:
        path = context.project_root / name
        if not path.exists() or not path.is_file():
            continue
        found.append(name)
        content = path.read_text(encoding="utf-8", errors="replace")
        if len(content) > 8_000:
            content = f"{content[:8_000]}\n\n[Dependency file truncated]"
        sections.append(
            ContextSection(
                title=f"Dependency context: {name}",
                content=content,
                source="dependency-analysis",
                metadata={"path": name},
            )
        )
    
    if not sections:
        sections.append(
            ContextSection(
                title="Dependency context",
                content="No common dependency manifest was found in the project root.",
                source="dependency-analysis",
                metadata={"found": found},
            )
        )
    return sections


def directory_summary_section(context: ProjectContext) -> ContextSection:
    paths = sorted(file.relative_path for file in context.files)
    lines = paths[:80]
    if len(paths) > 80:
        lines.append(f"... {len(paths) - 80} more files")
    return ContextSection(
        title="Directory summary",
        content="\n".join(f"- {path}" for path in lines) or "- No files",
        source="common",
        metadata={"file_count": len(paths)},
    )


def command_context(
    *,
    context: ProjectContext,
    command: list[str],
    title: str,
    timeout_seconds: int = 12,
) -> tuple[ContextSection, dict[str, Any]]:
    executable = shutil.which(command[0])
    if executable is None:
        metadata = {
            "command": command,
            "status": "skipped",
            "reason": f"{command[0]} is not available on PATH.",
        }
        return (
            ContextSection(
                title=title,
                content=f"Skipped: {metadata['reason']}.",
                source="local-tool",
                metadata=metadata
            ),
            metadata
        )
    
    try:
        completed = subprocess.run(
            [executable, *command[1:]],
            cwd=context.project_root,
            text=True,
            capture_output=True,
            timeout=timeout_seconds,
            check=False,
        )
    except Exception as exc:    # pragma: no cover - defensive around local tools
        metadata = {
            "command": command,
            "status": "error",
            "reason": str(exc)
        }
        return (
            ContextSection(
                title=title,
                content=f"Tool failed before completion: {exc}",
                source="local-tool",
                metadata=metadata,
            ),
            metadata,
        )
    
    output = "\n".join(part for part in (completed.stdout, completed.stderr) if part).strip()
    if len(output) > 12_000:
        output = f"{output[:12_000]}\n\n[Tool output truncated]"
    metadata = {
        "command": command,
        "status": "completed",
        "exit_code": completed.returncode,
    }
    return (
        ContextSection(
            title=title,
            content=output or "Tool completed without output.",
            source="local-tool",
            metadata=metadata,
        ),
        metadata,
    )


def unused_code_tooling_sections(
    context: ProjectContext,
    options: ReviewOptions,
) -> tuple[list[ContextSection], dict[str, Any]]:
    sections: list[ContextSection] = []
    tooling: dict[str, Any] = {}

    if options.use_ts_prune:
        section, metadata = command_context(
            context=context,
            command=["ts-prune"],
            title="Unused code analyzer context: ts-prune",
        )
        sections.append(section)
        tooling["ts_prune"] = metadata

    if options.use_eslint:
        section, metadata = command_context(
            context=context,
            command=["eslint", ".", "--format", "stylish"],
            title="Unused code analyzer context: ESLint",
        )
        sections.append(section)
        tooling["eslint"] = metadata
    
    if not sections:
        sections.append(
            ContextSection(
                title="Unused code analyzer context",
                content=(
                    "No external unused-code analyzer was requested or run. "
                    "Base the review on imports, exports, references, tests, and public API risk."
                ),
                source="unused-code",
                metadata={"status": "not_requested"},
            )
        )
    return sections, tooling


def read_optional_file(path_text: str | None, root: Path) -> tuple[str | None, dict[str, Any]]:
    if not path_text:
        return None, {}
    path = Path(path_text).expanduser()
    if not path.is_absolute():
        path = root / path
    try:
        content = path.read_text(encoding="utf-8", errors="replace")
    except Exception as exc:
        return None, {"path": str(path), "status": "error", "reason": str(exc)}
    return content, {"path": str(path), "status": "loaded"}


def json_section(title: str, payload: dict[str, Any], source: str) -> ContextSection:
    return ContextSection(
        title=title,
        content=json.dumps(payload, ensure_ascii=False, indent=2),
        source=source,
        metadata={"format": "json"}
    )