"""Quick-fixes review strategy."""

from __future__ import annotations

from ..discovery import ProjectContext
from ..orchestration.types import ReviewOptions

from .base import BaseReviewStrategy, ContextSection, EnhancedReviewContext, ReviewIntent
from .context import directory_summary_section


class QuickFixesReviewStrategy(BaseReviewStrategy):
    """
    Prepare intent and lightweight context for quick-fixes reviews.
    """

    def __init__(self) -> None:
        super().__init__("quick-fixes")

    def describe_intent(self, options: ReviewOptions) -> ReviewIntent:
        return ReviewIntent(
            review_type=self.review_type,
            title="Quick Fixes Review",
            instructions=(
                "Act as a pragmatic senior developer. Perform a quick fixes review focused on "
                "low-handing bugs, simple code improvements, basic security concerns, "
                "documentation quick wins, and simple testing opportunities."
            ),
            focus_areas=[
                "obvious defects",
                "small readability improvements",
                "safe refactors",
                "missing edge-case handling",
                "fast test improvements",
            ],
            output_expectations=[
                "Group findings by High, Medium, and Low priority.",
                "For each finding include issue, location, suggested fix, and impact.",
                "Prefer small actionable changes over broad redesign advice.",
            ],
            schema_name="quick-fixes-actionable-findings",
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
                title="Quick fixes context",
                content=(
                    "Prioritize quick, low-risk improvements. Treat compiler, lint, and test "
                    "signals as useful context when they are present in project files or reports."
                ),
                source="quick-fixes",
            ),
        ]
        return EnhancedReviewContext(
            context_sections=sections,
            metadata=self._base_metadata(context_focus="fast-actionable-findings")
        )