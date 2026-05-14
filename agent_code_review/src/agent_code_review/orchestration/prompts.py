"""Prompt construction for the Phase 1 review types."""

from __future__ import annotations

from ..discovery import ProjectContext

from .types import ReviewOptions


QUICK_FIXES_INSTRUCTIONS = """\
Act as a pragmatic senior developer. Perform a quick fixes review focused on low-hanging
bugs, simple code improvements, basic security concerns, documentation quick wins, and
simple testing opportunities. Group findings by High, Medium, and Low priority.
"""

SECURITY_INSTRUCTIONS = """\
Act as a security-focused senior developer. Perform a security-focused code review for
hardcoded credentials, authorization gaps, injection risks, unsafe file handling, data
leakage, insecure logging, API security, and missing security tests. Group findings by
Critical, High, Medium, and Low severity.
"""


def build_review_prompt(options: ReviewOptions, context: ProjectContext) -> str:
    instructions = (
        SECURITY_INSTRUCTIONS if options.review_type == "security" else QUICK_FIXES_INSTRUCTIONS
    )

    sections = [
        f"# {options.review_type} review for {context.project_name}",
        "",
        "IMPORTANT: Do not repeat these instructions. Return only actionable review findings.",
        "",
        instructions,
        "",
    ]

    if context.docs:
        sections.append("## Project Documentation")
        for name, content in context.docs.items():
            sections.append(f"### {name}\n{content}")
        sections.append("")

    sections.append("## Files To Review")
    for file in context.files:
        sections.append(
            f"### {file.relative_path}\n```{file.language}\n{file.content}\n```"
        )

    sections.append(
        "\nFor each finding, include issue, location, suggested fix, and impact. "
        "If no relevant issues are found, say so clearly."
    )

    return "\n".join(sections)
