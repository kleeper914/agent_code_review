"""Function-calling definitions and execution helpers."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from ..llm_clients.registry import supports_tool_calling

from .dependency_discovery import DependencyInfo, discover_dependencies, format_dependencies
from .dependency_security import batch_search_dependency_security, search_dependency_security


class ToolCallSpec(BaseModel):
    """Provider-neutral tool call request."""

    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class ToolExecutionResult(BaseModel):
    """Result returned from a function-call tool."""

    tool_name: str
    result: str
    success: bool = True
    error: str | None = None


class DependencyToolContext(BaseModel):
    """Dependency analysis context prepared for prompts and optional tool binding."""

    enabled: bool
    skipped_reason: str | None = None
    dependencies: list[DependencyInfo] = Field(default_factory=list)
    static_context: str = ""
    tool_results: list[ToolExecutionResult] = Field(default_factory=list)
    tool_schemas: list[dict[str, Any]] = Field(default_factory=list)


DEPENDENCY_TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "name": "search_dependency_security",
        "description": "Search for security information about one software package dependency.",
        "parameters": {
            "type": "object",
            "properties": {
                "package_name": {"type": "string"},
                "package_version": {"type": "string"},
                "ecosystem": {"type": "string", "enum": ["npm", "composer", "pip", "gem"]},
            },
            "required": ["package_name", "ecosystem"],
        },
    },
    {
        "name": "batch_search_dependency_security",
        "description": "Search for security information about multiple package dependencies.",
        "parameters": {
            "type": "object",
            "properties": {
                "packages": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "version": {"type": "string"},
                        },
                        "required": ["name"],
                    },
                },
                "ecosystem": {"type": "string", "enum": ["npm", "composer", "pip", "gem"]},
                "limit": {"type": "number"},
            },
            "required": ["packages", "ecosystem"],
        },
    },
]


def prepare_dependency_tool_context(
    project_root: Path,
    *,
    review_type: str,
    include_dependency_analysis: bool | None,
    provider: str,
    model_name: str,
) -> DependencyToolContext:
    dependencies = discover_dependencies(project_root)
    static_context = format_dependencies(dependencies)
    should_use = include_dependency_analysis is True and review_type in {"architectural", "security"}
    if not should_use:
        return DependencyToolContext(
            enabled=False,
            skipped_reason="Dependency analysis was not requested for this review type",
            dependencies=dependencies,
            static_context=static_context,
        )
    if not supports_tool_calling(model_name):
        return DependencyToolContext(
            enabled=False,
            skipped_reason=f"Model {model_name} does not support dependency tool calling",
            dependencies=dependencies,
            static_context=static_context,
        )
    if not os.getenv("SERPAPI_KEY"):
        return DependencyToolContext(
            enabled=False,
            skipped_reason="SERPAPI_KEY is not configured",
            dependencies=dependencies,
            static_context=static_context,
        )
    return DependencyToolContext(
        enabled=True,
        dependencies=dependencies,
        static_context=static_context,
        tool_schemas=DEPENDENCY_TOOL_SCHEMAS,
    )


def execute_tool_call(spec: ToolCallSpec) -> ToolExecutionResult:
    try:
        if spec.name == "search_dependency_security":
            result = search_dependency_security(
                package_name=str(spec.arguments.get("package_name", "")),
                package_version=spec.arguments.get("package_version"),
                ecosystem=str(spec.arguments.get("ecosystem", "")),
            )
        elif spec.name == "batch_search_dependency_security":
            result = batch_search_dependency_security(
                packages=list(spec.arguments.get("packages") or []),
                ecosystem=str(spec.arguments.get("ecosystem", "")),
                limit=int(spec.arguments.get("limit") or 5),
            )
        else:
            raise ValueError(f"Unknown tool: {spec.name}")
        return ToolExecutionResult(tool_name=spec.name, result=result)
    except Exception as exc:
        return ToolExecutionResult(
            tool_name=spec.name,
            result=f"Error executing tool call: {exc}",
            success=False,
            error=str(exc),
        )
