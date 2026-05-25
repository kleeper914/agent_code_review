"""Project discovery, framework detection, and context assembly."""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

import pathspec
import yaml
from pydantic import BaseModel, ConfigDict, Field


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
    ".vue",
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
    priority: int = 50
    selection_reason: str = "supported source file"


class CssFrameworkDetection(BaseModel):
    """CSS framework detected from config files or dependencies."""

    name: str
    version: str | None = None
    confidence: float = 0.0


class ProjectDetection(BaseModel):
    """Language and framework facts inferred from project files."""

    language: str = "unknown"
    framework: str = "none"
    confidence: float = 0.0
    detection_method: str = "unknown"
    additional_frameworks: list[str] = Field(default_factory=list)
    css_frameworks: list[CssFrameworkDetection] = Field(default_factory=list)
    framework_version: str | None = None
    framework_type: str | None = None
    project_type: str | None = None
    languages: dict[str, int] = Field(default_factory=dict)


class ProjectContext(BaseModel):
    """Code and documentation context sent to orchestration."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    project_name: str
    project_root: Path
    target: str
    files: list[DiscoveredFile]
    docs: dict[str, str]
    detection: ProjectDetection = Field(default_factory=ProjectDetection)
    file_tree: str = ""
    discovery_metadata: dict[str, Any] = Field(default_factory=dict)


def discover_project_context(
    *,
    target: str,
    project_root: Path,
    include_tests: bool = False,
    include_project_docs: bool = True,
) -> ProjectContext:
    detection = detect_project(project_root)
    discovery = discover_files_with_metadata(
        target=target,
        project_root=project_root,
        include_tests=include_tests,
    )
    return ProjectContext(
        project_name=project_root.name,
        project_root=project_root,
        target=target,
        files=discovery.files,
        docs=read_project_docs(project_root) if include_project_docs else {},
        detection=detection,
        file_tree=generate_file_tree([file.relative_path for file in discovery.files]),
        discovery_metadata=discovery.metadata,
    )


def discover_files(
    *, target: str, project_root: Path, include_tests: bool = False
) -> list[DiscoveredFile]:
    return discover_files_with_metadata(
        target=target,
        project_root=project_root,
        include_tests=include_tests,
    ).files


class DiscoveryResult(BaseModel):
    """Files plus details about smart selection decisions."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    files: list[DiscoveredFile]
    metadata: dict[str, Any] = Field(default_factory=dict)


def discover_files_with_metadata(
    *,
    target: str,
    project_root: Path,
    include_tests: bool = False,
) -> DiscoveryResult:
    root = project_root.resolve()
    target_path = (root / target).resolve()
    _validate_target(target, target_path, root)

    gitignore = _load_gitignore(root)
    eslintignore = _load_ignore_file(root / ".eslintignore")
    tsconfig = _load_tsconfig(root)
    paths = (
        [target_path]
        if target_path.is_file()
        else _walk_supported_files(target_path, root, gitignore)
    )

    discovered: list[DiscoveredFile] = []
    excluded_files: list[str] = []
    for path in sorted(paths, key=lambda item: item.relative_to(root).as_posix()):
        relative_path = path.relative_to(root).as_posix()
        excluded_by = _excluded_by_smart_filters(
            path=path,
            relative_path=relative_path,
            root=root,
            gitignore=gitignore,
            eslintignore=eslintignore,
            tsconfig=tsconfig,
        )
        if excluded_by:
            excluded_files.append(relative_path)
            continue
        if not include_tests and _is_test_file(relative_path):
            excluded_files.append(relative_path)
            continue
        if not _is_supported_file(path):
            continue
        priority, reason = _file_priority(relative_path)
        discovered.append(
            DiscoveredFile(
                path=path,
                relative_path=relative_path,
                language=_language_for_path(path),
                content=path.read_text(encoding="utf-8", errors="replace"),
                priority=priority,
                selection_reason=reason,
            )
        )

    discovered.sort(key=lambda file: (-file.priority, file.relative_path))
    return DiscoveryResult(
        files=discovered,
        metadata={
            "excludedFiles": sorted(excluded_files),
            "smartFiltering": {
                "eslintignore": bool(eslintignore.patterns),
                "tsconfig": tsconfig is not None,
            },
        },
    )


def detect_project(project_root: Path) -> ProjectDetection:
    """Detect primary language, application framework, and CSS framework stack."""

    root = project_root.resolve()
    language_counts = _count_languages(root)
    dependencies = _dependency_map(root)
    language = _detect_primary_language(root, language_counts, dependencies)
    framework_scores, framework_methods, framework_types = _score_frameworks(
        root, language, dependencies
    )
    css_frameworks = _detect_css_frameworks(root, dependencies)

    framework = "none"
    confidence = 0.5 if language != "unknown" else 0.0
    detection_method = "language-only" if language != "unknown" else "unknown"
    framework_version: str | None = None
    framework_type: str | None = None
    additional: list[str] = []
    if framework_scores:
        framework, score = max(framework_scores.items(), key=lambda item: item[1])
        if score > 0:
            confidence = min(score, 1.0)
            detection_method = (
                ", ".join(framework_methods.get(framework, [])) or "framework-signature"
            )
            framework_version = dependencies.get(_primary_dependency_for_framework(framework))
            framework_type = framework_types.get(framework)
            additional = sorted(
                name
                for name, value in framework_scores.items()
                if name != framework and value > 0.5
            )
        else:
            framework = "none"

    project_type = framework if framework != "none" else language
    return ProjectDetection(
        language=language,
        framework=framework,
        confidence=confidence,
        detection_method=detection_method,
        additional_frameworks=additional,
        css_frameworks=css_frameworks,
        framework_version=framework_version,
        framework_type=framework_type,
        project_type=project_type,
        languages=language_counts,
    )


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


def _load_ignore_file(path: Path) -> pathspec.PathSpec:
    if not path.exists():
        return pathspec.PathSpec.from_lines("gitignore", [])
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    return pathspec.PathSpec.from_lines("gitignore", lines)


def _load_tsconfig(project_root: Path) -> dict[str, Any] | None:
    path = project_root / "tsconfig.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _excluded_by_smart_filters(
    *,
    path: Path,
    relative_path: str,
    root: Path,
    gitignore: pathspec.PathSpec,
    eslintignore: pathspec.PathSpec,
    tsconfig: dict[str, Any] | None,
) -> str | None:
    if gitignore.match_file(relative_path):
        return ".gitignore"
    if eslintignore.match_file(relative_path):
        return ".eslintignore"
    if tsconfig and path.suffix.lower() in {".ts", ".tsx", ".js", ".jsx"}:
        if not _matches_tsconfig(relative_path, tsconfig):
            return "tsconfig.json"
    try:
        path.relative_to(root)
    except ValueError:
        return "outside-project"
    return None


def _matches_tsconfig(relative_path: str, tsconfig: dict[str, Any]) -> bool:
    files = tsconfig.get("files") or []
    if files:
        return relative_path in {str(item).replace("\\", "/") for item in files}

    excludes = [str(item).replace("\\", "/") for item in tsconfig.get("exclude") or []]
    if any(_glob_matches(relative_path, pattern) for pattern in excludes):
        return False

    includes = [str(item).replace("\\", "/") for item in tsconfig.get("include") or []]
    if includes:
        return any(_glob_matches(relative_path, pattern) for pattern in includes)
    return True


def _glob_matches(relative_path: str, pattern: str) -> bool:
    normalized = relative_path.replace("\\", "/")
    regex = re.escape(pattern)
    regex = regex.replace(r"\*\*/", r"(?:.*/)?")
    regex = regex.replace(r"/\*\*", r"(?:/.*)?")
    regex = regex.replace(r"\*\*", r".*")
    regex = regex.replace(r"\*", r"[^/]*")
    regex = regex.replace(r"\?", r"[^/]")
    return re.match(f"^{regex}$", normalized) is not None


def _walk_supported_files(
    target_path: Path, project_root: Path, gitignore: pathspec.PathSpec
) -> list[Path]:
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
        ".vue": "javascript",
    }.get(extension, extension.lstrip(".") or "unknown")


def _read_doc(path: Path) -> str:
    content = path.read_text(encoding="utf-8", errors="replace")
    if len(content) <= MAX_DOC_CHARS:
        return content
    return f"{content[:MAX_DOC_CHARS]}\n\n[Content truncated due to size]"


def generate_file_tree(file_paths: list[str]) -> str:
    """Return a deterministic markdown tree for reviewed files."""

    tree: dict[str, Any] = {}
    for file_path in sorted(file_paths):
        current = tree
        for part in [part for part in file_path.split("/") if part]:
            current = current.setdefault(part, {})

    def render(node: dict[str, Any], prefix: str = "") -> list[str]:
        lines: list[str] = []
        items = sorted(node.items(), key=lambda item: (bool(item[1] == {}), item[0]))
        for index, (name, children) in enumerate(items):
            last = index == len(items) - 1
            branch = "└── " if last else "├── "
            lines.append(f"{prefix}{branch}{name}")
            child_prefix = "    " if last else "│   "
            if children:
                lines.extend(render(children, prefix + child_prefix))
        return lines

    return "```\n" + "\n".join(render(tree)) + ("\n" if tree else "") + "```"


def _file_priority(relative_path: str) -> tuple[int, str]:
    lower = relative_path.lower()
    name = Path(relative_path).name.lower()
    if name in {"main.py", "app.py", "server.js", "server.ts", "index.ts", "index.js"}:
        return 100, "entry point"
    if "entry" in name or "main" in name:
        return 90, "entry point naming"
    if any(part in lower for part in ("/src/", "src/")):
        return 80, "source directory"
    if any(part in lower for part in ("/config/", "config/")):
        return 70, "configuration file"
    if _is_test_file(relative_path):
        return 40, "test file"
    return 50, "supported source file"


def _count_languages(project_root: Path) -> dict[str, int]:
    counts: Counter[str] = Counter()
    gitignore = _load_gitignore(project_root)
    for path in _walk_all_files(project_root, project_root, gitignore):
        language = _language_for_path(path)
        if language != "unknown":
            counts[language] += 1
    return dict(counts)


def _walk_all_files(
    target_path: Path, project_root: Path, gitignore: pathspec.PathSpec
) -> list[Path]:
    files: list[Path] = []
    if not target_path.exists():
        return files
    for child in target_path.iterdir():
        relative = child.relative_to(project_root).as_posix()
        if gitignore.match_file(relative):
            continue
        if child.is_dir():
            if child.name.startswith(".") or child.name in SKIPPED_DIRS:
                continue
            files.extend(_walk_all_files(child, project_root, gitignore))
        elif child.is_file():
            files.append(child)
    return files


def _dependency_map(project_root: Path) -> dict[str, str]:
    dependencies: dict[str, str] = {}
    dependencies.update(_package_json_dependencies(project_root / "package.json"))
    dependencies.update(_requirements_dependencies(project_root / "requirements.txt"))
    dependencies.update(_pyproject_dependencies(project_root / "pyproject.toml"))
    dependencies.update(_gemfile_dependencies(project_root / "Gemfile"))
    dependencies.update(_composer_dependencies(project_root / "composer.json"))
    dependencies.update(_pubspec_dependencies(project_root / "pubspec.yaml"))
    return {name.lower(): version for name, version in dependencies.items()}


def _package_json_dependencies(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    merged = {}
    for section in ("dependencies", "devDependencies", "peerDependencies"):
        merged.update({str(key): str(value) for key, value in (data.get(section) or {}).items()})
    return merged


def _requirements_dependencies(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    dependencies: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        clean = line.split("#", 1)[0].strip()
        if not clean or clean.startswith(("-", "git+", "http")):
            continue
        match = re.match(r"([A-Za-z0-9_.-]+)\s*([<>=!~].+)?", clean)
        if match:
            dependencies[match.group(1).lower()] = (match.group(2) or "*").strip()
    return dependencies


def _pyproject_dependencies(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}
    values = data.get("project", {}).get("dependencies", []) if isinstance(data, dict) else []
    dependencies: dict[str, str] = {}
    for value in values:
        match = re.match(r"([A-Za-z0-9_.-]+)(.*)", str(value))
        if match:
            dependencies[match.group(1).lower()] = match.group(2).strip() or "*"
    return dependencies


def _gemfile_dependencies(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    dependencies: dict[str, str] = {}
    pattern = re.compile(r"^\s*gem\s+['\"]([^'\"]+)['\"](?:,\s*['\"]([^'\"]+)['\"])?")
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if match := pattern.search(line):
            dependencies[match.group(1).lower()] = match.group(2) or "*"
    return dependencies


def _composer_dependencies(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    merged = {}
    for section in ("require", "require-dev"):
        merged.update({str(key): str(value) for key, value in (data.get(section) or {}).items()})
    return merged


def _pubspec_dependencies(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}
    dependencies: dict[str, str] = {}
    for section in ("dependencies", "dev_dependencies"):
        for name, value in (data.get(section) or {}).items():
            if isinstance(value, dict) and "sdk" in value:
                dependencies[str(name).lower()] = f"sdk:{value['sdk']}"
            else:
                dependencies[str(name).lower()] = str(value)
    return dependencies


def _detect_primary_language(
    project_root: Path,
    language_counts: dict[str, int],
    dependencies: dict[str, str],
) -> str:
    if language_counts.get("dart") or (project_root / "pubspec.yaml").exists():
        return "dart"
    if language_counts.get("python", 0) > 0 and any(
        dep in dependencies for dep in ("django", "flask", "fastapi")
    ):
        return "python"
    if language_counts.get("php", 0) > 0 or (project_root / "composer.json").exists():
        return "php"
    if language_counts.get("ruby", 0) > 0 or (project_root / "Gemfile").exists():
        return "ruby"
    if (
        (project_root / "tsconfig.json").exists()
        or "typescript" in dependencies
        or language_counts.get("typescript", 0)
    ):
        return "typescript"
    if (project_root / "package.json").exists():
        return (
            "typescript"
            if any(dep in dependencies for dep in ("next", "react", "vue"))
            else "javascript"
        )
    if language_counts:
        return max(language_counts.items(), key=lambda item: item[1])[0]
    return "unknown"


FRAMEWORK_SIGNATURES: dict[str, list[dict[str, Any]]] = {
    "typescript": [
        {
            "name": "nextjs",
            "files": ["next.config.js", "next.config.mjs"],
            "dependencies": ["next"],
            "weight": 0.9,
            "type": "fullstack",
        },
        {
            "name": "react",
            "files": ["src/App.tsx", "src/App.jsx"],
            "dependencies": ["react", "react-dom"],
            "weight": 0.8,
            "type": "ui",
        },
        {
            "name": "vue",
            "files": ["src/App.vue", "vue.config.js"],
            "dependencies": ["vue"],
            "weight": 0.8,
            "type": "ui",
        },
        {
            "name": "angular",
            "files": ["angular.json"],
            "dependencies": ["@angular/core"],
            "weight": 0.9,
            "type": "ui",
        },
    ],
    "javascript": [
        {
            "name": "nextjs",
            "files": ["next.config.js", "next.config.mjs"],
            "dependencies": ["next"],
            "weight": 0.9,
            "type": "fullstack",
        },
        {
            "name": "react",
            "files": ["src/App.jsx"],
            "dependencies": ["react", "react-dom"],
            "weight": 0.8,
            "type": "ui",
        },
        {
            "name": "vue",
            "files": ["src/App.vue", "vue.config.js"],
            "dependencies": ["vue"],
            "weight": 0.8,
            "type": "ui",
        },
        {
            "name": "express",
            "files": ["app.js", "server.js"],
            "dependencies": ["express"],
            "weight": 0.7,
            "type": "backend",
        },
    ],
    "python": [
        {
            "name": "django",
            "files": ["manage.py"],
            "dependencies": ["django"],
            "weight": 0.9,
            "type": "fullstack",
        },
        {
            "name": "fastapi",
            "files": ["main.py"],
            "dependencies": ["fastapi"],
            "weight": 0.8,
            "type": "backend",
        },
        {
            "name": "flask",
            "files": ["app.py", "wsgi.py"],
            "dependencies": ["flask"],
            "weight": 0.8,
            "type": "backend",
        },
    ],
    "dart": [
        {
            "name": "flutter",
            "files": ["pubspec.yaml", "lib/main.dart"],
            "dependencies": ["flutter"],
            "weight": 0.9,
            "type": "ui",
        },
    ],
    "php": [
        {
            "name": "laravel",
            "files": ["artisan"],
            "dependencies": ["laravel/framework"],
            "weight": 0.9,
            "type": "fullstack",
        },
        {
            "name": "symfony",
            "files": ["symfony.lock"],
            "dependencies": ["symfony/framework-bundle"],
            "weight": 0.9,
            "type": "fullstack",
        },
    ],
    "ruby": [
        {
            "name": "rails",
            "files": ["config/routes.rb"],
            "dependencies": ["rails"],
            "weight": 0.9,
            "type": "fullstack",
        },
        {
            "name": "sinatra",
            "files": ["config.ru"],
            "dependencies": ["sinatra"],
            "weight": 0.8,
            "type": "backend",
        },
    ],
}


def _score_frameworks(
    project_root: Path,
    language: str,
    dependencies: dict[str, str],
) -> tuple[dict[str, float], dict[str, list[str]], dict[str, str]]:
    scores: dict[str, float] = {}
    methods: dict[str, list[str]] = {}
    framework_types: dict[str, str] = {}
    signatures = FRAMEWORK_SIGNATURES.get(language, [])
    if language == "typescript":
        signatures = [*signatures, *FRAMEWORK_SIGNATURES.get("javascript", [])]
    for signature in signatures:
        name = str(signature["name"])
        weight = float(signature.get("weight", 0.5))
        score = 0.0
        reasons: list[str] = []
        for file_name in signature.get("files", []):
            if (project_root / file_name).exists():
                score += weight
                reasons.append(f"found file: {file_name}")
        for dep in signature.get("dependencies", []):
            if dep.lower() in dependencies:
                score += weight * 0.9
                reasons.append(f"found dependency: {dep}")
        scores[name] = score
        methods[name] = reasons
        if signature.get("type"):
            framework_types[name] = str(signature["type"])
    return scores, methods, framework_types


CSS_FRAMEWORK_SIGNATURES: dict[str, dict[str, Any]] = {
    "tailwind": {
        "dependencies": ["tailwindcss"],
        "files": ["tailwind.config.js", "tailwind.config.ts"],
        "weight": 0.9,
    },
    "bootstrap": {"dependencies": ["bootstrap"], "files": ["bootstrap.min.css"], "weight": 0.8},
    "material-ui": {
        "dependencies": ["@mui/material", "@material-ui/core"],
        "files": [],
        "weight": 0.8,
    },
    "styled-components": {"dependencies": ["styled-components"], "files": [], "weight": 0.7},
}


def _detect_css_frameworks(
    project_root: Path, dependencies: dict[str, str]
) -> list[CssFrameworkDetection]:
    detected: list[CssFrameworkDetection] = []
    for name, signature in CSS_FRAMEWORK_SIGNATURES.items():
        score = 0.0
        version: str | None = None
        for dep in signature["dependencies"]:
            if dep.lower() in dependencies:
                score += float(signature["weight"]) * 0.9
                version = dependencies.get(dep.lower())
        for file_name in signature["files"]:
            if (project_root / file_name).exists():
                score += float(signature["weight"])
        if score > 0:
            detected.append(
                CssFrameworkDetection(name=name, version=version, confidence=min(score, 1.0))
            )
    return sorted(detected, key=lambda item: (-item.confidence, item.name))


def _primary_dependency_for_framework(framework: str) -> str:
    return {
        "nextjs": "next",
        "react": "react",
        "vue": "vue",
        "angular": "@angular/core",
        "fastapi": "fastapi",
        "django": "django",
        "flask": "flask",
        "flutter": "flutter",
        "laravel": "laravel/framework",
        "rails": "rails",
        "sinatra": "sinatra",
    }.get(framework, framework)
