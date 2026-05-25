"""OutputManager equivalent for formatting and saving review artifacts."""

from __future__ import annotations

import json
import re
import stat
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from ..discovery import generate_file_tree
from ..tools.dependency_discovery import discover_dependencies, format_dependencies

from .reports import format_review_result
from .types import ReviewOptions, ReviewResult


@dataclass
class OutputArtifact:
    """Paths and formatted content produced by OutputManager."""

    formatted_output: str
    output_path: Path | None = None
    raw_data_path: Path | None = None
    diagram_paths: list[Path] = field(default_factory=list)
    removal_script_path: Path | None = None


class OutputManager:
    """Centralize report formatting, file naming, and secondary artifacts."""

    def __init__(self, output_dir: Path) -> None:
        self.output_dir = output_dir

    def save(self, result: ReviewResult, options: ReviewOptions) -> OutputArtifact:
        file_tree = generate_file_tree([file.relative_path for file in result.files])
        result.metadata["fileTree"] = file_tree
        if "usage" in result.metadata:
            result.metadata["usage"] = _normalize_usage_keys(result.metadata["usage"])

        dependency_section = self._dependency_section(result, options)
        if dependency_section:
            result.metadata["dependencyAnalysis"] = dependency_section

        formatted = format_review_result(result, options.output)
        formatted = self._add_file_tree(formatted, file_tree, options.output)
        if dependency_section:
            formatted = self._add_dependency_section(formatted, dependency_section, options.output)

        artifact = OutputArtifact(formatted_output=formatted)
        if options.stdout or options.return_only:
            return artifact

        self.output_dir.mkdir(parents=True, exist_ok=True)
        output_path = self._unique_output_path(result.review_type, options.output)
        output_path.write_text(formatted, encoding="utf-8")
        artifact.output_path = output_path
        result.output_path = output_path
        result.metadata["outputPath"] = str(output_path)

        if options.debug:
            raw_path = self._unique_named_path(
                f"{result.review_type}-review-raw-data-{output_path.stem}.json"
            )
            raw_path.write_text(
                json.dumps(_safe_result_payload(result), indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            artifact.raw_data_path = raw_path
            result.metadata["rawDataPath"] = str(raw_path)

        if options.diagram and result.review_type == "architectural":
            artifact.diagram_paths = self._save_diagrams(formatted, output_path)
            if artifact.diagram_paths:
                result.metadata["diagramPaths"] = [str(path) for path in artifact.diagram_paths]

        if result.review_type == "unused-code" and result.metadata.get("removalScript"):
            artifact.removal_script_path = self._save_removal_script(str(result.metadata["removalScript"]))
            if artifact.removal_script_path:
                result.metadata["removalScriptPath"] = str(artifact.removal_script_path)

        return artifact

    def _unique_output_path(self, review_type: str, output_format: str) -> Path:
        extension = "json" if output_format == "json" else "md"
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        return self._unique_named_path(f"{review_type}-review-{timestamp}.{extension}")

    def _unique_named_path(self, file_name: str) -> Path:
        path = self.output_dir / file_name
        if not path.exists():
            return path
        counter = 1
        while True:
            candidate = path.with_name(f"{path.stem}-{counter}{path.suffix}")
            if not candidate.exists():
                return candidate
            counter += 1

    def _add_file_tree(self, formatted: str, file_tree: str, output_format: str) -> str:
        if output_format == "json":
            payload = json.loads(formatted)
            payload["analyzedFiles"] = [file["relativePath"] for file in payload.get("files", [])]
            payload["fileTree"] = file_tree
            payload.setdefault("metadata", {})["fileTree"] = file_tree
            return json.dumps(payload, indent=2, ensure_ascii=False)
        return f"{formatted.rstrip()}\n\n## Files Analyzed\n\n{file_tree}\n"

    def _dependency_section(self, result: ReviewResult, options: ReviewOptions) -> str:
        should_include = (
            options.include_dependency_analysis is True
            and result.review_type in {"architectural", "security"}
            and result.files
        )
        if not should_include:
            return ""
        project_root = result.files[0].path
        while project_root.parent != project_root and not (
            (project_root / "package.json").exists()
            or (project_root / "pyproject.toml").exists()
            or (project_root / "requirements.txt").exists()
            or (project_root / "Gemfile").exists()
            or (project_root / "composer.json").exists()
        ):
            project_root = project_root.parent
        return format_dependencies(discover_dependencies(project_root))

    def _add_dependency_section(self, formatted: str, section: str, output_format: str) -> str:
        if output_format == "json":
            payload = json.loads(formatted)
            payload["dependencyAnalysis"] = section
            payload.setdefault("metadata", {})["dependencyAnalysis"] = section
            return json.dumps(payload, indent=2, ensure_ascii=False)
        return f"{formatted.rstrip()}\n\n{section}\n"

    def _save_diagrams(self, formatted: str, output_path: Path) -> list[Path]:
        diagrams = extract_mermaid_diagrams(formatted)
        paths: list[Path] = []
        for index, diagram in enumerate(diagrams, start=1):
            suffix = f"-{index}" if len(diagrams) > 1 else ""
            diagram_path = output_path.with_name(f"{output_path.stem}-diagram{suffix}.md")
            diagram_path.write_text(
                "\n".join(
                    [
                        f"# Architecture Diagram{f' {index}' if len(diagrams) > 1 else ''}",
                        "",
                        f"Generated from: {output_path.name}",
                        "",
                        "```mermaid",
                        diagram,
                        "```",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            paths.append(diagram_path)
        return paths

    def _save_removal_script(self, script: str) -> Path:
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        script_path = self._unique_named_path(f"unused-code-removal-script-{timestamp}.sh")
        script_path.write_text(script, encoding="utf-8")
        script_path.chmod(script_path.stat().st_mode | stat.S_IXUSR)
        return script_path


def extract_mermaid_diagrams(content: str) -> list[str]:
    diagrams = [match.strip() for match in re.findall(r"```mermaid\s*\n([\s\S]*?)```", content)]
    inline = re.findall(r"(^graph\s+(?:TB|TD|BT|RL|LR)[\s\S]*?)(?=\n\n|\n##|\Z)", content, re.MULTILINE)
    for diagram in inline:
        clean = diagram.strip()
        if clean and clean not in diagrams:
            diagrams.append(clean)
    return diagrams


def _safe_result_payload(result: ReviewResult) -> dict[str, Any]:
    payload = result.model_dump(mode="json")
    metadata = dict(payload.get("metadata") or {})
    metadata.pop("prompt", None)
    payload["metadata"] = metadata
    return payload


def _normalize_usage_keys(value: Any) -> Any:
    if not isinstance(value, dict):
        return value
    mapping = {
        "inputTokens": "input_tokens",
        "outputTokens": "output_tokens",
        "totalTokens": "total_tokens",
    }
    return {mapping.get(key, key): item for key, item in value.items()}
