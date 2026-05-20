from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from ..discovery import ProjectContext
from ..orchestration.types import ReviewOptions
from ..strategies.base import EnhancedReviewContext, ReviewIntent


class PromptPackage(BaseModel):
    """
    Rendered prompt plus metadata passed into the model invocation node.
    """

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
    enhanced_context: EnhancedReviewContext
) -> PromptPackage:
    prompt = _format_template(
        PROMPT_TEMPLATE,
        title=intent.title,
        project_name=context.project_name,
        review_type=options.review_type,
        instructions=intent.instructions,
        focus_areas=_bullet_list(intent.focus_areas),
        output_expectations=_bullet_list(intent.output_expectations),
        context_block=_context_block(enhanced_context),
        docs_block=_docs_block(context),
        files_block=_files_block(context),
    )
    return PromptPackage(
        prompt=prompt,
        intent=intent,
        enhanced_context=enhanced_context,
        metadata={
            "review_type": options.review_type,
            "schema": intent.schema_name,
            "strategy": enhanced_context.metadata.get("strategy"),
            "context_sections": len(enhanced_context.context_sections)
        }
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


def _files_block(context: ProjectContext) -> str:
    sections: list[str] = []
    for file in context.files:
        sections.append(f"### {file.relative_path}\n```{file.language}\n{file.content}\n```")
    return "\n\n".join(sections) or "No files were included."