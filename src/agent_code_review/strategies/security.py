"""Security review strategy."""

from __future__ import annotations

from ..discovery import ProjectContext
from ..orchestration.types import ReviewOptions

from .base import BaseReviewStrategy, ContextSection, EnhancedReviewContext, ReviewIntent
from .context import dependency_sections, directory_summary_section


class SecurityReviewStrategy(BaseReviewStrategy):
    """
    Prepare security review intent and dependency context.
    """

    def __init__(self) -> None:
        super().__init__("security")
    
    def describe_intent(self, options: ReviewOptions) -> ReviewIntent:
        return ReviewIntent(
            review_type=self.review_type,
            title="Security Review",
            instructions=(
                "Act as a security-focused senior developer. Perform a security-focused code "
                "review for hardcoded credentials, authorization gaps, injection risks, unsafe "
                "file handing, data leakage, instance logging, API security, and missing "
                "security tests."
            ),
            focus_areas=[
                "input validation",
                "authentication and authorization",
                "dependency and supply-chain risk",
                "data leakage",
                "unsafe filesystem or command execution",
                "secure error handling",
            ],
            output_expectations=[
                "Group findlings by Critical, High, Medium, and Low severity.",
                "Include exploit scenario, affected location, suggested fix, and test idea.",
                "Avoid speculative findings when there is no supporting code evidence.",
            ],
            schema_name="security-severity-findings",
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
                title="Security context",
                content=(
                    "Review trust boundaries, external inputs, secrets, dependency manifests, "
                    "and user-controlled data flow. Treat tests and docs as evidence for "
                    "security intent when present."
                ),
                source="security",
            ),
            *dependency_sections(context, options.include_dependency_analysis),
        ]
        return EnhancedReviewContext(
            context_sections=sections,
            metadata=self._base_metadata(
                dependency_analysis=options.include_dependency_analysis is not False
            ),
        )