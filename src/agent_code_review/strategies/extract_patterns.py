"""Specialized extract-patterns review strategy."""

from __future__ import annotations

import json
from typing import Any

from ..discovery import ProjectContext
from ..orchestration.types import ReviewOptions
from ..patterns.extract import ExtractPatternsValidator

from .base import (
    BaseReviewStrategy,
    ContextSection,
    EnhancedReviewContext,
    PostprocessResult,
    ReviewIntent,
)
from .context import dependency_sections, directory_summary_section


class ExtractPatternsReviewStrategy(BaseReviewStrategy):
    """Extract reusable architecture, tooling, and workflow patterns from a project."""

    def __init__(self) -> None:
        super().__init__("extract-patterns")

    def describe_intent(self, options: ReviewOptions) -> ReviewIntent:
        return ReviewIntent(
            review_type="extract-patterns",
            title="Extract Patterns Review",
            instructions=(
                "Extract reusable project patterns as a structured pattern library. Focus on "
                "architecture, technology stack, code style, testing approach, exemplar "
                "characteristics, and replication guidance."
            ),
            focus_areas=[
                "project purpose and architecture",
                "technology stack and tooling decisions",
                "architectural and code organization patterns",
                "testing and documentation conventions",
                "replicable decisions and pitfalls",
            ],
            output_expectations=[
                "Return a JSON object with a top-level `patterns` property.",
                "Include concrete file examples for each architectural pattern.",
                "Prefer reusable, evidence-backed patterns over generic praise.",
            ],
            schema_name="extract-patterns-schema",
        )

    def enhance_context(
        self,
        context: ProjectContext,
        options: ReviewOptions,
    ) -> EnhancedReviewContext:
        metrics = _project_metrics(context)
        sections = [
            self._project_summary_section(context),
            directory_summary_section(context),
            ContextSection(
                title="Pattern extraction context",
                content=(
                    "Analyze this project as an exemplar candidate. Capture patterns that can "
                    "be stored in a pattern database and reused by future reviews.\n\n"
                    f"Files: {metrics['file_count']}\n"
                    f"Lines of code: {metrics['line_count']}\n"
                    f"Average file length: {metrics['average_file_length']:.1f}\n"
                    f"Languages: {', '.join(metrics['languages']) or 'unknown'}"
                ),
                source="extract-patterns",
                metadata=metrics,
            ),
        ]
        # Pattern extraction benefits from dependency and tooling context when available.
        sections.extend(dependency_sections(context, options.include_dependency_analysis))
        return EnhancedReviewContext(
            context_sections=sections,
            metadata=self._base_metadata(
                patternDatabaseReady=True,
                includeDependencyAnalysis=options.include_dependency_analysis,
            ),
        )

    def postprocess_response(
        self,
        content: str,
        context: ProjectContext,
        options: ReviewOptions,
        enhanced_context: EnhancedReviewContext,
    ) -> PostprocessResult:
        validation = ExtractPatternsValidator.validate(_json_or_text(content))
        return PostprocessResult(
            content=content,
            metadata={
                "parsed_schema": {
                    "reviewType": self.review_type,
                    "schema": self.describe_intent(options).schema_name,
                },
                "extractPatternsValidation": validation.to_metadata(),
                "patternDatabase": {
                    "ready": enhanced_context.metadata.get("patternDatabaseReady", False),
                    "projectName": context.project_name,
                },
            },
        )


def _project_metrics(context: ProjectContext) -> dict[str, Any]:
    line_counts = [len(file.content.splitlines()) for file in context.files]
    languages = sorted({file.language for file in context.files if file.language})
    return {
        "file_count": len(context.files),
        "line_count": sum(line_counts),
        "average_file_length": sum(line_counts) / len(line_counts) if line_counts else 0,
        "languages": languages,
    }


def _json_or_text(content: str) -> Any:
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        return content
