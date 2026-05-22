"""Manifest readers for dependency analysis."""

from __future__ import annotations

import json
import re
from pathlib import Path

from pydantic import BaseModel


class DependencyInfo(BaseModel):
    """Dependency discovered from a project manifest."""

    name: str
    version: str | None = None
    ecosystem: str
    dev_dependency: bool = False
    source: str


def discover_dependencies(project_root: Path) -> list[DependencyInfo]:
    dependencies: list[DependencyInfo] = []
    dependencies.extend(_read_package_json(project_root / "package.json"))
    dependencies.extend(_read_requirements(project_root / "requirements.txt"))
    dependencies.extend(_read_pyproject(project_root / "pyproject.toml"))
    dependencies.extend(_read_gemfile(project_root / "Gemfile"))
    dependencies.extend(_read_composer(project_root / "composer.json"))
    return dependencies


def format_dependencies(dependencies: list[DependencyInfo]) -> str:
    if not dependencies:
        return "No dependency manifests were found."
    lines = ["## Dependency Inventory"]
    for dep in dependencies:
        dev = " (dev)" if dep.dev_dependency else ""
        version = f" {dep.version}" if dep.version else ""
        lines.append(f"- [{dep.ecosystem}] {dep.name}{version}{dev} from {dep.source}")
    return "\n".join(lines)


def _read_package_json(path: Path) -> list[DependencyInfo]:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    deps: list[DependencyInfo] = []
    for section, dev in (("dependencies", False), ("devDependencies", True)):
        for name, version in (data.get(section) or {}).items():
            deps.append(
                DependencyInfo(
                    name=name,
                    version=str(version),
                    ecosystem="npm",
                    dev_dependency=dev,
                    source="package.json",
                )
            )
    return deps


def _read_requirements(path: Path) -> list[DependencyInfo]:
    if not path.exists():
        return []
    deps: list[DependencyInfo] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        clean = line.split("#", 1)[0].strip()
        if not clean or clean.startswith(("-", "git+", "http")):
            continue
        match = re.match(r"([A-Za-z0-9_.-]+)\s*([<>=!~].+)?", clean)
        if match:
            deps.append(
                DependencyInfo(
                    name=match.group(1),
                    version=match.group(2),
                    ecosystem="pip",
                    source="requirements.txt",
                )
            )
    return deps


def _read_pyproject(path: Path) -> list[DependencyInfo]:
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8", errors="replace")
    deps: list[DependencyInfo] = []
    in_dependencies = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("dependencies"):
            in_dependencies = True
            continue
        if in_dependencies and stripped.startswith("]"):
            in_dependencies = False
        if in_dependencies:
            match = re.search(r'"([^"<>=!~\[]+)([^"]*)"', stripped)
            if match:
                deps.append(
                    DependencyInfo(
                        name=match.group(1),
                        version=match.group(2).strip() or None,
                        ecosystem="pip",
                        source="pyproject.toml",
                    )
                )
    return deps


def _read_gemfile(path: Path) -> list[DependencyInfo]:
    if not path.exists():
        return []
    deps: list[DependencyInfo] = []
    pattern = re.compile(r"^\s*gem\s+['\"]([^'\"]+)['\"](?:,\s*['\"]([^'\"]+)['\"])?")
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if match := pattern.search(line):
            deps.append(
                DependencyInfo(
                    name=match.group(1),
                    version=match.group(2),
                    ecosystem="gem",
                    source="Gemfile",
                )
            )
    return deps


def _read_composer(path: Path) -> list[DependencyInfo]:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    deps: list[DependencyInfo] = []
    for section, dev in (("require", False), ("require-dev", True)):
        for name, version in (data.get(section) or {}).items():
            if name == "php":
                continue
            deps.append(
                DependencyInfo(
                    name=name,
                    version=str(version),
                    ecosystem="composer",
                    dev_dependency=dev,
                    source="composer.json",
                )
            )
    return deps
