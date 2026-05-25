"""LangChain prompt rendering for provider-neutral review strategies."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from ..discovery import DiscoveredFile, ProjectContext
from ..orchestration.types import ReviewOptions
from ..strategies.base import ContextSection, EnhancedReviewContext, ReviewIntent

from .manager import PromptManager


class PromptPackage(BaseModel):
    """Rendered prompt plus metadata passed into the model invocation node."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    prompt: str
    intent: ReviewIntent
    enhanced_context: EnhancedReviewContext
    metadata: dict[str, Any] = Field(default_factory=dict)


PROMPT_TEMPLATE = """# {title} for {project_name}

IMPORTANT: Do not repeat these instructions. Return only actionable review findings.

## Review Intent
Review type: {review_type}

{instructions}

## Focus Areas
{focus_areas}

## Output Expectations
{output_expectations}

## Enhanced Context
{context_block}

## Project Documentation
{docs_block}

## Files To Review
{files_block}

If no relevant issues are found, say so clearly and explain the evidence considered.
"""


def build_prompt_package(
    options: ReviewOptions,
    context: ProjectContext,
    intent: ReviewIntent,
    enhanced_context: EnhancedReviewContext,
    *,
    files_override: list[DiscoveredFile] | None = None,
    review_context: str | None = None,
    tool_context: str | None = None,
    memory_context: str | None = None,
) -> PromptPackage:
    prompt_context = _with_additional_context(
        enhanced_context,
        review_context=review_context,
        tool_context=tool_context,
        memory_context=memory_context,
    )
    rendered = PromptManager().build_prompt(
        options,
        context,
        intent,
        prompt_context,
        files_override=files_override,
    )
    return PromptPackage(
        prompt=rendered.prompt,
        intent=intent,
        enhanced_context=prompt_context,
        metadata={
            "review_type": options.review_type,
            "schema": intent.schema_name,
            "strategy": prompt_context.metadata.get("strategy"),
            "context_sections": len(prompt_context.context_sections),
            **rendered.metadata,
        },
    )


def _format_template(template: str, **values: str) -> str:
    try:
        from langchain_core.prompts import PromptTemplate

        prompt_template = PromptTemplate.from_template(template)
        return prompt_template.format(**values)
    except Exception:
        return template.format(**values)


def _bullet_list(items: list[str]) -> str:
    return "\n".join(f"- {item}" for item in items) or "- None"


def _context_block(enhanced_context: EnhancedReviewContext) -> str:
    if not enhanced_context.context_sections:
        return "No enhanced context sections were provided."
    sections: list[str] = []
    for section in enhanced_context.context_sections:
        sections.append(f"### {section.title}\n{section.content}")
    return "\n\n".join(sections)


def _docs_block(context: ProjectContext) -> str:
    if not context.docs:
        return "No project documentation was included."
    sections: list[str] = []
    for name, content in context.docs.items():
        sections.append(f"### {name}\n{content}")
    return "\n\n".join(sections)


def _files_block(
    context: ProjectContext,
    *,
    files_override: list[DiscoveredFile] | None = None,
) -> str:
    sections: list[str] = []
    files = files_override if files_override is not None else context.files
    for file in files:
        sections.append(f"### {file.relative_path}\n```{file.language}\n{file.content}\n```")
    return "\n\n".join(sections) or "No files were included."


def _with_additional_context(
    enhanced_context: EnhancedReviewContext,
    *,
    review_context: str | None,
    tool_context: str | None,
    memory_context: str | None,
) -> EnhancedReviewContext:
    sections = list(enhanced_context.context_sections)
    if memory_context:
        sections.append(
            ContextSection(
                title="Memory context",
                content=memory_context,
                source="memory",
            )
        )
    if review_context:
        sections.append(
            ContextSection(
                title="Review Context",
                content=review_context,
                source="multi_pass",
            )
        )
    if tool_context:
        sections.append(
            ContextSection(
                title="Dependency tool context",
                content=tool_context,
                source="tooling",
            )
        )
    return EnhancedReviewContext(
        context_sections=sections,
        metadata=dict(enhanced_context.metadata),
        tooling=dict(enhanced_context.tooling),
        ai_detection=dict(enhanced_context.ai_detection),
    )
