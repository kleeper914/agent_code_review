"""Unused-code review strategy."""

from __future__ import annotations

from ..discovery import ProjectContext
from ..orchestration.types import ReviewOptions

from .base import BaseReviewStrategy, ContextSection, EnhancedReviewContext, ReviewIntent
from .context import directory_summary_section, unused_code_tooling_sections


class UnusedCodeReviewStrategy(BaseReviewStrategy):
    """
    Prepare unused-code review intent and local analyzer context.
    """

    def __init__(self) -> None:
        super().__init__("unused-code")

    def describe_intent(self, options: ReviewOptions) -> ReviewIntent:
        return ReviewIntent(
            review_type=self.review_type,
            title="Unused Code Review",
            instructions=(
                "Act as a codebase cleanup specialist. Identify unused variables, functions, "
                "classes, modules, exports, dead branches, duplicate implementations, stale "
                "comments, deprecated paths, and public APIs that appear removable only with "
                "careful confidence scoring."
            ),
            focus_areas=[
                "unused imports and exports",
                "dead code paths",
                "unreferenced files",
                "duplicate implementations",
                "removal risk",
                "test and public API impact",
            ],
            output_expectations=[
                "For each finding include confidence, evidence, removal risk, and safe validation steps.",
                "Separate high-confidence removals from items that need manual verification.",
                "Do not recommend deleting public APIs without risk notes.",
            ],
            schema_name="unused-code-confidence-findings",
        )
    
    def enhance_context(
        self,
        context: ProjectContext,
        options: ReviewOptions
    ) -> EnhancedReviewContext:
        analyzer_sections, tooling = unused_code_tooling_sections(context, options)
        sections = [
            self._project_summary_section(context),
            directory_summary_section(context),
            ContextSection(
                title="Unused code review context",
                content=(
                    "Treat references conservatively. Consider dynamic imports, framework "
                    "conventions, exported package surfaces, tests, scripts, and docs before "
                    "suggesting deletion."
                ),
                source="unused-code",
                metadata={"focused": options.focused, "trace_code": options.trace_code},
            ),
            *analyzer_sections,
        ]
        return EnhancedReviewContext(
            context_sections=sections,
            metadata=self._base_metadata(
                focused=options.focused,
                trace_code=options.trace_code
            ),
            tooling=tooling,
        )