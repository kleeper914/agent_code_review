from __future__ import annotations

from dataclasses import dataclass

from ..discovery import ProjectContext
from ..orchestration.types import ReviewOptions, ReviewType

from .base import BaseReviewStrategy, ContextSection, EnhancedReviewContext, ReviewIntent
from .context import dependency_sections, directory_summary_section


@dataclass(frozen=True)
class CompatibilityProfile:
    title: str
    instructions: str
    focus_areas: list[str]
    output_expectations: list[str]
    schema_name: str
    include_dependencies: bool = False
    include_docs: bool = True


COMPATIBILITY_PROFILES: dict[str, CompatibilityProfile] = {
    "comprehensive": CompatibilityProfile(
        title="Comprehensive Review",
        instructions=(
            "Act as a senior cross-functional reviewer. Assess correctness, security, "
            "architecture, performance, maintainability, tests, documentation, and "
            "developer experience with balanced prioritization."
        ),
        focus_areas=[
            "correctness and defects",
            "security and privacy",
            "architecture and maintainability",
            "performance risks",
            "testing and documentation gaps",
        ],
        output_expectations=[
            "Group findings by severity and include evidence from the reviewed code.",
            "Call out strengths, risks, suggested fixes, and validation steps.",
            "Prefer actionable findings over broad commentary.",
        ],
        schema_name="comprehensive-findings",
        include_dependencies=True,
    ),
    "best-practices": CompatibilityProfile(
        title="Best Practices Review",
        instructions=(
            "Act as a best-practices reviewer. Identify deviations from idiomatic, "
            "maintainable, and framework-appropriate implementation patterns."
        ),
        focus_areas=[
            "idiomatic language usage",
            "maintainability",
            "error handling",
            "testability",
            "documentation quality",
        ],
        output_expectations=[
            "Explain the practice, affected location, and concrete improvement.",
            "Separate must-fix issues from style or polish suggestions.",
        ],
        schema_name="best-practices-findings",
    ),
    "evaluation": CompatibilityProfile(
        title="Evaluation Review",
        instructions=(
            "Act as an evaluator. Assess the submission against explicit and inferred "
            "requirements, quality standards, and readiness for production or acceptance."
        ),
        focus_areas=[
            "requirement coverage",
            "correctness",
            "quality score",
            "risk and blockers",
            "recommended next steps",
        ],
        output_expectations=[
            "Include an overall assessment and clear pass/fail or readiness rationale.",
            "List evidence, gaps, and improvement recommendations.",
        ],
        schema_name="evaluation-assessment",
    ),
    "extract-patterns": CompatibilityProfile(
        title="Extract Patterns Review",
        instructions=(
            "Act as a pattern extraction specialist. Identify reusable architecture, "
            "domain, testing, integration, and implementation patterns from the codebase."
        ),
        focus_areas=[
            "architectural patterns",
            "reusable abstractions",
            "domain conventions",
            "testing patterns",
            "anti-patterns worth avoiding",
        ],
        output_expectations=[
            "Describe each pattern, where it appears, why it matters, and how to reuse it.",
            "Separate exemplar patterns from risky or inconsistent patterns.",
        ],
        schema_name="extract-patterns-library",
        include_dependencies=True,
    ),
    "ai-integration": CompatibilityProfile(
        title="AI Integration Review",
        instructions=(
            "Act as an AI integration reviewer. Assess model calls, prompt construction, "
            "tooling, data handling, fallback behavior, evaluation, observability, and cost risk."
        ),
        focus_areas=[
            "prompt and context quality",
            "model and provider boundaries",
            "fallback and retry behavior",
            "privacy and data handling",
            "evaluation and observability",
        ],
        output_expectations=[
            "Include risks specific to AI behavior and provider integrations.",
            "Suggest concrete reliability, safety, and cost controls.",
        ],
        schema_name="ai-integration-findings",
        include_dependencies=True,
    ),
    "cloud-native": CompatibilityProfile(
        title="Cloud Native Review",
        instructions=(
            "Act as a cloud-native reviewer. Assess deployment readiness, configuration, "
            "scalability, resilience, observability, security posture, and operational fit."
        ),
        focus_areas=[
            "configuration and secrets",
            "resilience and scaling",
            "observability",
            "deployment portability",
            "cloud security",
        ],
        output_expectations=[
            "Tie each finding to an operational risk and a concrete mitigation.",
            "Call out missing deployment or runtime assumptions.",
        ],
        schema_name="cloud-native-findings",
        include_dependencies=True,
    ),
    "developer-experience": CompatibilityProfile(
        title="Developer Experience Review",
        instructions=(
            "Act as a developer-experience reviewer. Assess setup, commands, errors, docs, "
            "configuration, tests, local workflows, and contributor ergonomics."
        ),
        focus_areas=[
            "setup and onboarding",
            "command clarity",
            "error messages",
            "configuration ergonomics",
            "test and development workflow",
        ],
        output_expectations=[
            "Prioritize friction that slows real contributors.",
            "Suggest precise documentation, command, or workflow improvements.",
        ],
        schema_name="developer-experience-findings",
    ),
    "consolidated": CompatibilityProfile(
        title="Consolidated Review",
        instructions=(
            "Act as a report consolidator. Produce a coherent project-level review that "
            "deduplicates overlapping findings and preserves the highest-priority evidence."
        ),
        focus_areas=[
            "cross-file themes",
            "deduplicated findings",
            "severity prioritization",
            "project-level recommendations",
            "validation plan",
        ],
        output_expectations=[
            "Group related findings into consolidated themes.",
            "Include evidence locations and avoid repeating the same issue.",
        ],
        schema_name="consolidated-findings",
    ),
}


class CompatibilityReviewStrategy(BaseReviewStrategy):
    """Minimal strategy route for public review types not yet specialized in Python."""

    def __init__(self, review_type: ReviewType) -> None:
        super().__init__(review_type)
        self.profile = COMPATIBILITY_PROFILES[review_type]

    def describe_intent(self, options: ReviewOptions) -> ReviewIntent:
        return ReviewIntent(
            review_type=self.review_type,
            title=self.profile.title,
            instructions=self.profile.instructions,
            focus_areas=self.profile.focus_areas,
            output_expectations=self.profile.output_expectations,
            schema_name=self.profile.schema_name,
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
                title=f"{self.profile.title} compatibility context",
                content=(
                    "This route preserves the public review type surface. "
                    "Use the intent, selected language/framework, project files, and available "
                    "documentation to produce a focused review while dedicated prompt templates "
                    "are completed in Phase 8."
                ),
                source="compatibility",
                metadata={
                    "language": options.language,
                    "framework": options.framework,
                    "writer_model": options.writer_model,
                },
            ),
        ]
        if self.profile.include_dependencies:
            sections.extend(dependency_sections(context, options.include_dependency_analysis))
        return EnhancedReviewContext(
            context_sections=sections,
            metadata=self._base_metadata(
                compatibility="compatibility",
                language=options.language,
                framework=options.framework,
                writer_model=options.writer_model,
            ),
        )
