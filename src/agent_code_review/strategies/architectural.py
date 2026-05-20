"""Architectural review strategy."""

from __future__ import annotations

from ..discovery import ProjectContext
from ..orchestration.types import ReviewOptions

from .base import BaseReviewStrategy, ContextSection, EnhancedReviewContext, ReviewIntent
from .context import directory_summary_section


class ArchitecturalReviewStrategy(BaseReviewStrategy):
    """
    Prepare architectural review intent and diagram context.
    """

    def __init__(self) -> None:
        super().__init__("architectural")

    def describe_intent(self, options: ReviewOptions) -> ReviewIntent:
        expectations = [
            "Explain architectural risks with concrete file or module references.",
            "Identify coupling, cohesion, layering, dependency, and scalability concerns.",
            "Separate immediate refactors from larger design recommendations.",
        ]
        if options.diagram:
            expectations.append("Include Mermaid diagrams that summarize the current or proposed shape.")
        return ReviewIntent(
            review_type=self.review_type,
            title="Architectural Review",
            instructions=(
                "Act as a principal engineer reviewing system architecture. Focus on component "
                "boundaries, layering, dependency direction, separation of concerns, extensibility, "
                "maintainability, and whether the structure supports future change."
            ),
            focus_areas=[
                "module boundaries",
                "dependency direction",
                "separation of concerns",
                "reuse and duplication",
                "scalability",
                "operational maintainability",
            ],
            output_expectations=expectations,
            schema_name="architectural-findings",
        )
    
    def enhance_context(
        self,
        context: ProjectContext,
        options: ReviewOptions,
    ) -> EnhancedReviewContext:
        sections = [
            self._project_summary_section(context),
            directory_summary_section(context),
            ContextSection(
                title="Architectural context",
                content=(
                    "Infer system structure from file organization, imports, naming, docs, and "
                    "entry points. Call out uncertainty when the available files do not prove a "
                    "relationship."
                ),
                source="architectural",
            ),
        ]
        if options.diagram:
            sections.append(
                ContextSection(
                    title="Architecture diagram context",
                    content=(
                        "Mermaid output requested. Include concise Mermaid diagrams only when "
                        "they clarify architecture. Use valid fenced mermaid blocks."
                    ),
                    source="architectural",
                    metadata={"diagram": True}
                )
            )
        return EnhancedReviewContext(
            context_sections=sections,
            metadata=self._base_metadata(diagram=options.diagram)
        )