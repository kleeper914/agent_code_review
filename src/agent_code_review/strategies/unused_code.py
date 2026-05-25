"""Unused-code review strategy."""

from __future__ import annotations

from ..discovery import ProjectContext
from ..orchestration.types import ReviewOptions, ReviewType

from .base import BaseReviewStrategy, ContextSection, EnhancedReviewContext, ReviewIntent
from .context import directory_summary_section, unused_code_tooling_sections


class UnusedCodeReviewStrategy(BaseReviewStrategy):
    """Prepare unused-code review intent and local analyzer context."""

    def __init__(self, review_type: ReviewType = "unused-code") -> None:
        super().__init__(review_type)

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
        options: ReviewOptions,
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
                trace_code=options.trace_code,
                variant="standard",
            ),
            tooling=tooling,
        )


class FocusedUnusedCodeReviewStrategy(UnusedCodeReviewStrategy):
    """Focused unused-code compatibility strategy."""

    def describe_intent(self, options: ReviewOptions) -> ReviewIntent:
        return ReviewIntent(
            review_type=self.review_type,
            title="Focused Unused Code Review",
            instructions=(
                "Act as a focused unused-code specialist. Identify high-signal unused files, "
                "functions, classes, imports, variables, and exports with conservative "
                "confidence scoring and practical cleanup guidance."
            ),
            focus_areas=[
                "high-confidence unused files",
                "unused functions and classes",
                "unused imports and variables",
                "safe removal candidates",
                "manual verification steps",
            ],
            output_expectations=[
                "Separate high-confidence removals from uncertain candidates.",
                "Include evidence, confidence, risk, and validation steps for every finding.",
            ],
            schema_name="focused-unused-code-findings",
        )

    def enhance_context(
        self,
        context: ProjectContext,
        options: ReviewOptions,
    ) -> EnhancedReviewContext:
        enhanced = super().enhance_context(context, options)
        enhanced.context_sections.append(
            ContextSection(
                title="Focused unused-code mode",
                content=(
                    "Prioritize concise, high-confidence cleanup candidates. Avoid broad "
                    "architectural critique unless it directly affects unused-code confidence."
                ),
                source="focused-unused-code",
            )
        )
        enhanced.metadata.update(
            self._base_metadata(
                compatibility="phase7",
                focused=True,
                trace_code=False,
                variant="focused",
            )
        )
        return enhanced


class CodeTracingUnusedCodeReviewStrategy(UnusedCodeReviewStrategy):
    """Code-tracing unused-code compatibility strategy."""

    def describe_intent(self, options: ReviewOptions) -> ReviewIntent:
        return ReviewIntent(
            review_type=self.review_type,
            title="Code Tracing Unused Code Review",
            instructions=(
                "Act as a code tracing specialist. Map entry points, imports, exports, "
                "call chains, framework conventions, and dynamic references before making "
                "unused-code recommendations."
            ),
            focus_areas=[
                "entry point mapping",
                "reference tracing",
                "dynamic import and framework conventions",
                "false-positive risk",
                "evidence-backed removal confidence",
            ],
            output_expectations=[
                "Explain the trace evidence behind each unused-code finding.",
                "Document assumptions and false-positive risks before recommending removal.",
            ],
            schema_name="code-tracing-unused-code-findings",
        )

    def enhance_context(
        self,
        context: ProjectContext,
        options: ReviewOptions,
    ) -> EnhancedReviewContext:
        enhanced = super().enhance_context(context, options)
        enhanced.context_sections.append(
            ContextSection(
                title="Code tracing unused-code mode",
                content=(
                    "Trace likely entry points, imports, exports, call sites, tests, scripts, "
                    "configuration hooks, and framework conventions before marking code unused."
                ),
                source="code-tracing-unused-code",
            )
        )
        enhanced.metadata.update(
            self._base_metadata(
                compatibility="phase7",
                focused=options.focused,
                trace_code=True,
                variant="code-tracing",
            )
        )
        return enhanced
