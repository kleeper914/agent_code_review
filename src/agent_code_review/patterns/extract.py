"""Validation models for extract-patterns review output."""

from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError


class _CamelModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True)


class Technology(_CamelModel):
    name: str
    version: str | None = None
    purpose: str
    configuration_notes: str | None = Field(default=None, alias="configurationNotes")


class ComplexityDistribution(_CamelModel):
    simple: int
    moderate: int
    complex: int


class CodeMetrics(_CamelModel):
    average_function_length: float = Field(alias="averageFunctionLength")
    average_file_length: float = Field(alias="averageFileLength")
    total_files: int = Field(alias="totalFiles")
    total_lines_of_code: int = Field(alias="totalLinesOfCode")
    complexity_distribution: ComplexityDistribution = Field(alias="complexityDistribution")
    test_coverage: float | None = Field(default=None, alias="testCoverage")


class ArchitecturalPattern(_CamelModel):
    pattern_name: str = Field(alias="patternName")
    usage: Literal["Primary", "Secondary", "Occasional"]
    implementation: str
    examples: list[str]
    effectiveness: Literal["Excellent", "Good", "Adequate", "Poor"]


class ProjectOverview(_CamelModel):
    purpose: str
    scale: dict[str, str]
    architecture: dict[str, str]


class TechnologyStack(_CamelModel):
    core_languages: list[Technology] = Field(alias="coreLanguages")
    frameworks: list[Technology]
    build_tools: list[Technology] = Field(alias="buildTools")
    development_tools: list[Technology] = Field(alias="developmentTools")
    testing_tools: list[Technology] = Field(alias="testingTools")
    deployment_tools: list[Technology] | None = Field(default=None, alias="deploymentTools")


class CodeStyle(_CamelModel):
    naming_conventions: dict[str, Any] = Field(alias="namingConventions")
    organization_patterns: dict[str, Any] = Field(alias="organizationPatterns")
    documentation_style: dict[str, Any] = Field(alias="documentationStyle")


class TestingStrategy(_CamelModel):
    test_types: list[str] = Field(alias="testTypes")
    test_organization: str = Field(alias="testOrganization")
    mocking_strategy: str = Field(alias="mockingStrategy")
    test_naming: str = Field(alias="testNaming")
    coverage_approach: str = Field(alias="coverageApproach")
    test_utilities: list[str] = Field(alias="testUtilities")


class ExemplarCharacteristics(_CamelModel):
    strengths: list[str]
    patterns_to_emulate: list[str] = Field(alias="patternsToEmulate")
    lessons_learned: list[str] = Field(alias="lessonsLearned")


class ReplicationGuide(_CamelModel):
    setup_requirements: list[str] = Field(alias="setupRequirements")
    key_decisions: list[str] = Field(alias="keyDecisions")
    implementation_order: list[str] = Field(alias="implementationOrder")
    common_pitfalls: list[str] = Field(alias="commonPitfalls")


class ExtractPatternsReview(_CamelModel):
    version: Literal["1.0"]
    timestamp: str
    project_name: str = Field(alias="projectName")
    project_overview: ProjectOverview = Field(alias="projectOverview")
    technology_stack: TechnologyStack = Field(alias="technologyStack")
    code_metrics: CodeMetrics = Field(alias="codeMetrics")
    architectural_patterns: list[ArchitecturalPattern] = Field(alias="architecturalPatterns")
    code_style: CodeStyle = Field(alias="codeStyle")
    testing_strategy: TestingStrategy = Field(alias="testingStrategy")
    exemplar_characteristics: ExemplarCharacteristics = Field(alias="exemplarCharacteristics")
    replication_guide: ReplicationGuide = Field(alias="replicationGuide")
    summary: str


class ExtractPatternsRoot(_CamelModel):
    patterns: ExtractPatternsReview


class ValidationIssue(_CamelModel):
    field: str
    severity: Literal["critical", "warning", "info"]
    message: str
    suggestion: str | None = None


class QualityMetrics(_CamelModel):
    completeness: int
    accuracy: int
    usefulness: int
    specificity: int
    overall: int


class ValidationResult(_CamelModel):
    is_valid: bool = Field(alias="isValid")
    quality_level: Literal["excellent", "good", "adequate", "poor"] = Field(alias="qualityLevel")
    quality_metrics: QualityMetrics = Field(alias="qualityMetrics")
    issues: list[ValidationIssue]
    suggestions: list[str]
    summary: str
    pattern_count: int = Field(default=0, alias="patternCount")

    def to_metadata(self) -> dict[str, Any]:
        return self.model_dump(by_alias=True)


class ExtractPatternsValidator:
    """Validate and score structured extract-patterns payloads."""

    @staticmethod
    def validate(output: Any) -> ValidationResult:
        try:
            payload = _parse_payload(output)
        except ValueError as exc:
            return ValidationResult(
                is_valid=False,
                quality_level="poor",
                quality_metrics=_default_metrics(),
                issues=[
                    ValidationIssue(
                        field="root",
                        severity="critical",
                        message=str(exc),
                        suggestion="Ensure output is valid JSON or a Python mapping.",
                    )
                ],
                suggestions=["Fix schema validation errors before using pattern output."],
                summary="Output does not conform to the extract-patterns schema.",
            )
        try:
            root = ExtractPatternsRoot.model_validate(payload)
        except ValidationError as exc:
            return ValidationResult(
                is_valid=False,
                quality_level="poor",
                quality_metrics=_default_metrics(),
                issues=[
                    ValidationIssue(
                        field=".".join(str(part) for part in issue["loc"]) or "root",
                        severity="critical",
                        message=str(issue["msg"]),
                        suggestion="Ensure this field is present and has the expected type.",
                    )
                    for issue in exc.errors()
                ],
                suggestions=["Fix schema validation errors before using pattern output."],
                summary="Output does not conform to the extract-patterns schema.",
            )

        content_issues = _content_issues(root.patterns)
        metrics = _quality_metrics(root.patterns, content_issues)
        level = _quality_level(metrics.overall)
        return ValidationResult(
            is_valid=True,
            quality_level=level,
            quality_metrics=metrics,
            issues=content_issues,
            suggestions=_suggestions(root.patterns, content_issues),
            summary=(
                f"{level.title()} quality pattern extraction. "
                f"Overall score: {metrics.overall}/100 with {len(content_issues)} validation issues."
            ),
            pattern_count=len(root.patterns.architectural_patterns),
        )


def _parse_payload(output: Any) -> Any:
    if isinstance(output, str):
        try:
            return json.loads(output)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Failed to parse output as JSON: {exc}") from exc
    return output


def _content_issues(patterns: ExtractPatternsReview) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    if len(patterns.project_overview.purpose) < 20:
        issues.append(
            ValidationIssue(
                field="projectOverview.purpose",
                severity="warning",
                message="Project purpose description is too brief.",
            )
        )
    if not patterns.technology_stack.core_languages:
        issues.append(
            ValidationIssue(
                field="technologyStack.coreLanguages",
                severity="critical",
                message="No core languages identified.",
            )
        )
    if patterns.code_metrics.total_files <= 0:
        issues.append(
            ValidationIssue(
                field="codeMetrics.totalFiles",
                severity="critical",
                message="Total files count must be greater than zero.",
            )
        )
    if not patterns.architectural_patterns:
        issues.append(
            ValidationIssue(
                field="architecturalPatterns",
                severity="warning",
                message="No architectural patterns identified.",
            )
        )
    for index, pattern in enumerate(patterns.architectural_patterns):
        if not pattern.examples:
            issues.append(
                ValidationIssue(
                    field=f"architecturalPatterns[{index}].examples",
                    severity="warning",
                    message=f"No examples provided for pattern: {pattern.pattern_name}.",
                )
            )
    if not patterns.exemplar_characteristics.strengths:
        issues.append(
            ValidationIssue(
                field="exemplarCharacteristics.strengths",
                severity="warning",
                message="No exemplar strengths identified.",
            )
        )
    if not patterns.exemplar_characteristics.patterns_to_emulate:
        issues.append(
            ValidationIssue(
                field="exemplarCharacteristics.patternsToEmulate",
                severity="warning",
                message="No patterns to emulate identified.",
            )
        )
    if len(patterns.summary) < 50:
        issues.append(
            ValidationIssue(
                field="summary",
                severity="warning",
                message="Summary is too brief.",
            )
        )
    return issues


def _quality_metrics(
    patterns: ExtractPatternsReview, issues: list[ValidationIssue]
) -> QualityMetrics:
    critical = len([issue for issue in issues if issue.severity == "critical"])
    warning = len([issue for issue in issues if issue.severity == "warning"])
    completeness = max(0, 100 - critical * 20 - warning * 5)
    accuracy = 100
    if patterns.code_metrics.average_function_length > 200:
        accuracy -= 10
    if patterns.code_metrics.average_file_length > 1000:
        accuracy -= 10
    if any(not pattern.examples for pattern in patterns.architectural_patterns):
        accuracy -= 15
    usefulness = 100
    if not patterns.exemplar_characteristics.patterns_to_emulate:
        usefulness -= 20
    if len(patterns.replication_guide.key_decisions) < 3:
        usefulness -= 15
    if not patterns.replication_guide.common_pitfalls:
        usefulness -= 10
    vague_text = [
        patterns.project_overview.purpose,
        patterns.summary,
        *patterns.exemplar_characteristics.strengths,
    ]
    specificity = (
        80 if any("good" in text.lower() or "nice" in text.lower() for text in vague_text) else 100
    )
    if not patterns.architectural_patterns:
        specificity -= 30
    overall = round(completeness * 0.3 + accuracy * 0.25 + usefulness * 0.25 + specificity * 0.2)
    return QualityMetrics(
        completeness=round(completeness),
        accuracy=max(0, round(accuracy)),
        usefulness=max(0, round(usefulness)),
        specificity=max(0, round(specificity)),
        overall=max(0, overall),
    )


def _quality_level(overall: int) -> Literal["excellent", "good", "adequate", "poor"]:
    if overall >= 90:
        return "excellent"
    if overall >= 75:
        return "good"
    if overall >= 60:
        return "adequate"
    return "poor"


def _suggestions(patterns: ExtractPatternsReview, issues: list[ValidationIssue]) -> list[str]:
    suggestions: list[str] = []
    if any("architecturalPatterns" in issue.field for issue in issues):
        suggestions.append("Identify concrete design or architecture patterns with file examples.")
    if len(patterns.replication_guide.key_decisions) < 5:
        suggestions.append("Document more architectural and tooling decisions for replication.")
    if len(patterns.exemplar_characteristics.strengths) < 3:
        suggestions.append("Add more concrete strengths that make this codebase exemplary.")
    return suggestions


def _default_metrics() -> QualityMetrics:
    return QualityMetrics(
        completeness=0,
        accuracy=0,
        usefulness=0,
        specificity=0,
        overall=0,
    )
