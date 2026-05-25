"""Provider-neutral review strategy contracts for phase 3."""

from __future__ import annotations

from typing import Any, Protocol

from pydantic import BaseModel, Field

from ..discovery import ProjectContext
from ..orchestration.types import ReviewOptions, ReviewType


class ContextSection(BaseModel):
    """A named context block produced before prompt rendering."""

    title: str
    content: str
    source: str = "strategy"
    metadata: dict[str, Any] = Field(default_factory=dict)


class ReviewIntent(BaseModel):
    """Review-type-specific instructions without model or provider details."""

    review_type: ReviewType
    title: str
    instructions: str
    focus_areas: list[str] = Field(default_factory=list)
    output_expectations: list[str] = Field(default_factory=list)
    schema_name: str | None = None


class EnhancedReviewContext(BaseModel):
    """Context sections and metadata added by a review strategy."""

    context_sections: list[ContextSection] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    tooling: dict[str, Any] = Field(default_factory=dict)
    ai_detection: dict[str, Any] = Field(default_factory=dict)


class PostprocessResult(BaseModel):
    """Provider-neutral response post-processing result."""

    content: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class ReviewStrategy(Protocol):
    """Strategy boundary used by orchestration."""

    review_type: ReviewType

    def describe_intent(self, options: ReviewOptions) -> ReviewIntent:
        """Return the review intent and output expectations."""

    def enhance_context(
        self,
        context: ProjectContext,
        options: ReviewOptions,
    ) -> EnhancedReviewContext:
        """Return additional context for prompt construction."""

    def postprocess_response(
        self,
        content: str,
        context: ProjectContext,
        options: ReviewOptions,
        enhanced_context: EnhancedReviewContext,
    ) -> PostprocessResult:
        """Normalize the model response without calling a model."""


class BaseReviewStrategy:
    """Common behavior for phase 3 strategies."""

    review_type: ReviewType

    def __init__(self, review_type: ReviewType) -> None:
        self.review_type = review_type

    @property
    def strategy_name(self) -> str:
        return self.__class__.__name__

    def _base_metadata(self, **extra: Any) -> dict[str, Any]:
        return {"strategy": self.strategy_name, "review_type": self.review_type, **extra}

    def _project_summary_section(self, context: ProjectContext) -> ContextSection:
        languages = sorted({file.language for file in context.files})
        return ContextSection(
            title="Project context",
            content=(
                f"Project: {context.project_name}\n"
                f"Target: {context.target}\n"
                f"Files: {len(context.files)}\n"
                f"Languages: {', '.join(languages) if languages else 'unknown'}"
            ),
            source="common",
            metadata={"file_count": len(context.files), "languages": languages},
        )

    def describe_intent(self, options: ReviewOptions) -> ReviewIntent:
        """Subclasses provide review-type-specific prompt intent."""
        raise NotImplementedError

    def postprocess_response(
        self,
        content: str,
        context: ProjectContext,
        options: ReviewOptions,
        enhanced_context: EnhancedReviewContext,
    ) -> PostprocessResult:
        return PostprocessResult(
            content=content,
            metadata={
                "parsed_schema": {
                    "reviewType": self.review_type,
                    "schema": self.describe_intent(options).schema_name,
                },
                "tooling": enhanced_context.tooling,
                "ai_detection": enhanced_context.ai_detection,
            },
        )
