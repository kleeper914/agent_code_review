"""Project discovery and context assembly."""

from __future__ import annotations

from pathlib import Path

import pathspec
from pydantic import BaseModel, ConfigDict


SUPPORTED_EXTENSIONS = {
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".py",
    ".pyi",
    ".pyx",
    ".php",
    ".java",
    ".rb",
    ".rake",
    ".gemspec",
    ".ru",
    ".erb",
    ".go",
    ".rs",
    ".c",
    ".cpp",
    ".h",
    ".hpp",
    ".cs",
    ".swift",
    ".kt",
    ".dart",
}

SKIPPED_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "venv",
    "env",
    "node_modules",
    "dist",
    "build",
    "out",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "ai-code-review-docs",
}

DOC_NAMES = ("README.md", "PROJECT.md", "PROGRESS.md", "CONTRIBUTING.md", "ARCHITECTURE.md")
MAX_DOC_CHARS = 50_000


class DiscoveredFile(BaseModel):
    """File content prepared for review."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    path: Path
    relative_path: str
    language: str
    content: str


class ProjectContext(BaseModel):
    """Code and documentation context sent to orchestration."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    project_name: str
    project_root: Path
    target: str
    files: list[DiscoveredFile]
    docs: dict[str, str]


def discover_project_context(
    *,
    target: str,
    project_root: Path,
    include_tests: bool = False,
    include_project_docs: bool = True,
) -> ProjectContext:
    return ProjectContext(
        project_name=project_root.name,
        project_root=project_root,
        target=target,
        files=discover_files(target=target, project_root=project_root, include_tests=include_tests),
        docs=read_project_docs(project_root) if include_project_docs else {},
    )


def discover_files(*, target: str, project_root: Path, include_tests: bool = False) -> list[DiscoveredFile]:
    root = project_root.resolve()
    target_path = (root / target).resolve()
    _validate_target(target, target_path, root)

    gitignore = _load_gitignore(root)
    paths = [target_path] if target_path.is_file() else _walk_supported_files(target_path, root, gitignore)

    discovered: list[DiscoveredFile] = []
    for path in sorted(paths, key=lambda item: item.relative_to(root).as_posix()):
        relative_path = path.relative_to(root).as_posix()
        if gitignore.match_file(relative_path):
            continue
        if not include_tests and _is_test_file(relative_path):
            continue
        if not _is_supported_file(path):
            continue
        discovered.append(
            DiscoveredFile(
                path=path,
                relative_path=relative_path,
                language=_language_for_path(path),
                content=path.read_text(encoding="utf-8", errors="replace"),
            )
        )

    return discovered


def read_project_docs(project_root: Path) -> dict[str, str]:
    docs: dict[str, str] = {}

    for name in DOC_NAMES:
        path = project_root / name
        if path.exists() and path.is_file():
            docs[name] = _read_doc(path)

    docs_dir = project_root / "docs"
    if docs_dir.exists() and docs_dir.is_dir():
        for path in sorted(docs_dir.glob("*.md")):
            docs[f"docs/{path.name}"] = _read_doc(path)

    return docs


def _validate_target(target: str, target_path: Path, project_root: Path) -> None:
    if "=" in target and not any(part in target for part in ("/", "\\", ".")):
        raise ValueError(
            f"Invalid parameter format: '{target}'. Options should use '--', for example --type security."
        )

    try:
        target_path.relative_to(project_root)
    except ValueError as exc:
        raise ValueError(f"Target must be within the project directory: {project_root}") from exc

    if not target_path.exists():
        raise FileNotFoundError(f"Target not found: {target}")


def _load_gitignore(project_root: Path) -> pathspec.PathSpec:
    gitignore_path = project_root / ".gitignore"
    if not gitignore_path.exists():
        return pathspec.PathSpec.from_lines("gitignore", [])
    lines = gitignore_path.read_text(encoding="utf-8", errors="replace").splitlines()
    return pathspec.PathSpec.from_lines("gitignore", lines)


def _walk_supported_files(target_path: Path, project_root: Path, gitignore: pathspec.PathSpec) -> list[Path]:
    files: list[Path] = []
    for child in target_path.iterdir():
        relative = child.relative_to(project_root).as_posix()
        if gitignore.match_file(relative):
            continue
        if child.is_dir():
            if child.name.startswith(".") or child.name in SKIPPED_DIRS:
                continue
            files.extend(_walk_supported_files(child, project_root, gitignore))
        elif child.is_file() and _is_supported_file(child):
            files.append(child)
    return files


def _is_supported_file(path: Path) -> bool:
    return not path.name.startswith(".") and path.suffix.lower() in SUPPORTED_EXTENSIONS


def _is_test_file(relative_path: str) -> bool:
    file_name = Path(relative_path).name
    return (
        ".test." in file_name
        or ".spec." in file_name
        or file_name.startswith("test_")
        or file_name.startswith("test-")
        or "/__tests__/" in f"/{relative_path}"
        or "/test/" in f"/{relative_path}"
        or "/tests/" in f"/{relative_path}"
    )


def _language_for_path(path: Path) -> str:
    extension = path.suffix.lower()
    return {
        ".ts": "typescript",
        ".tsx": "typescript",
        ".js": "javascript",
        ".jsx": "javascript",
        ".py": "python",
        ".pyi": "python",
        ".pyx": "python",
        ".php": "php",
        ".java": "java",
        ".rb": "ruby",
        ".go": "go",
        ".rs": "rust",
        ".dart": "dart",
    }.get(extension, extension.lstrip(".") or "unknown")


def _read_doc(path: Path) -> str:
    content = path.read_text(encoding="utf-8", errors="replace")
    if len(content) <= MAX_DOC_CHARS:
        return content
    return f"{content[:MAX_DOC_CHARS]}\n\n[Content truncated due to size]"
