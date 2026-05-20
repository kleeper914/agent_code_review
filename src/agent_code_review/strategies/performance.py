"""Performance review strategy."""

from __future__ import annotations

from ..discovery import ProjectContext
from ..orchestration.types import ReviewOptions

from .base import BaseReviewStrategy, ContextSection, EnhancedReviewContext, ReviewIntent
from .context import directory_summary_section


class PerformanceReviewStrategy(BaseReviewStrategy):
    """
    Prepare performance review intent and context.
    """

    def __init__(self) -> None:
        super().__init__("performance")

    def describe_intent(self, options: ReviewOptions) -> ReviewIntent:
        return ReviewIntent(
            review_type=self.review_type,
            title="Performance Review",
            instructions=(
                "Act as a performance-focused senior engineer. Review algorithms, resource "
                "usage, concurrency, caching, database or network access patterns, rendering "
                "costs, and scale-sensitive code paths."
            ),
            focus_areas=[
                "algorithmic complexity",
                "unnecessary allocations",
                "I/O and network hot paths",
                "caching opportunities",
                "concurrency and batching",
                "load and scale behavior",
            ],
            output_expectations=[
                "Rank findings by expected performance impact and confidence.",
                "Include location, why it matters, and a practical improvement path.",
                "Do not recommend micro-optimizations without measurable impact.",
            ],
            schema_name="performance-impact-findings",
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
                title="Performance context",
                content=(
                   "Look for repeated work, synchronous blocking calls, expensive loops, "
                    "large-memory transformations, missing pagination, avoidable serialization, "
                    "and places where tests or docs imply expected scale." 
                ),
                source="performance",
            ),
        ]
        return EnhancedReviewContext(
            context_sections=sections,
            metadata=self._base_metadata(context_focus="runtime-and-scale")
        )