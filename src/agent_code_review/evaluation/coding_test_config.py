"""Coding-test assessment configuration models and merge helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

from ..orchestration.types import ReviewOptions


AssessmentType = Literal["coding-challenge", "take-home", "live-coding", "code-review"]
DifficultyLevel = Literal["junior", "mid", "senior", "lead", "architect"]
ScoringSystem = Literal["numeric", "letter", "pass-fail", "custom"]
FeedbackLevel = Literal["basic", "detailed", "comprehensive"]


class AssignmentConfig(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    title: str = "Coding Challenge"
    description: str = "Complete the coding challenge according to the provided requirements."
    requirements: list[str] = Field(
        default_factory=lambda: [
            "Implement the core functionality",
            "Include proper error handling",
            "Write comprehensive tests",
            "Provide clear documentation",
        ]
    )
    difficulty: DifficultyLevel = "mid"
    time_limit: int | None = Field(default=120, alias="timeLimit")
    type: AssessmentType = "coding-challenge"
    url: str | None = None
    file: str | None = None


class CriteriaWeights(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    correctness: float = 30
    codeQuality: float = 25
    architecture: float = 20
    performance: float = 15
    testing: float = 10
    documentation: float = 0
    errorHandling: float = 0
    security: float = 0


class ScoringConfig(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    system: ScoringSystem = "numeric"
    max_score: int = Field(default=100, alias="maxScore")
    passing_threshold: int = Field(default=70, alias="passingThreshold")
    breakdown: bool = True


class FeedbackConfig(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    level: FeedbackLevel = "detailed"
    include_examples: bool = Field(default=True, alias="includeExamples")
    include_suggestions: bool = Field(default=True, alias="includeSuggestions")
    include_resources: bool = Field(default=False, alias="includeResources")


class ConstraintsConfig(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    allowed_libraries: list[str] = Field(default_factory=list, alias="allowedLibraries")
    forbidden_patterns: list[str] = Field(default_factory=list, alias="forbiddenPatterns")
    target_language: str | None = Field(default=None, alias="targetLanguage")
    framework: str | None = None
    node_version: str | None = Field(default=None, alias="nodeVersion")
    typescript_version: str | None = Field(default=None, alias="typescriptVersion")
    memory_limit: int | None = Field(default=None, alias="memoryLimit")
    execution_timeout: int | None = Field(default=None, alias="executionTimeout")


class AIDetectionOptions(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    enabled: bool = False
    threshold: float = 0.7
    analyzers: list[str] = Field(default_factory=lambda: ["git", "documentation"])
    include_in_report: bool = Field(default=True, alias="includeInReport")
    fail_on_detection: bool = Field(default=False, alias="failOnDetection")


class CodingTestConfig(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    assignment: AssignmentConfig = Field(default_factory=AssignmentConfig)
    criteria: CriteriaWeights = Field(default_factory=CriteriaWeights)
    scoring: ScoringConfig = Field(default_factory=ScoringConfig)
    feedback: FeedbackConfig = Field(default_factory=FeedbackConfig)
    constraints: ConstraintsConfig = Field(default_factory=ConstraintsConfig)
    ai_detection: AIDetectionOptions = Field(default_factory=AIDetectionOptions, alias="aiDetection")


def default_coding_test_config() -> CodingTestConfig:
    return CodingTestConfig()


def load_coding_test_config(path: str | Path) -> CodingTestConfig:
    config_path = Path(path).expanduser()
    text = config_path.read_text(encoding="utf-8")
    if config_path.suffix.lower() == ".json":
        payload = json.loads(text)
    elif config_path.suffix.lower() in {".yaml", ".yml"}:
        payload = yaml.safe_load(text) or {}
    else:
        raise ValueError(f"Unsupported coding-test config format: {config_path.suffix}")
    return _config_from_payload(payload)


def build_coding_test_config(options: ReviewOptions, project_root: Path) -> CodingTestConfig:
    config = default_coding_test_config()
    if options.coding_test_config:
        config_path = Path(options.coding_test_config).expanduser()
        if not config_path.is_absolute():
            config_path = project_root / config_path
        config = load_coding_test_config(config_path)

    payload = config.model_dump(by_alias=True)
    _merge_assignment_overrides(payload, options, project_root)
    _merge_rubric_overrides(payload, options)
    _merge_feedback_overrides(payload, options)
    _merge_constraint_overrides(payload, options)
    _merge_ai_detection_overrides(payload, options)

    return _config_from_payload(payload)


def _config_from_payload(payload: dict[str, Any]) -> CodingTestConfig:
    normalized = dict(payload)
    if "evaluation" in normalized:
        evaluation = normalized.pop("evaluation") or {}
        if "criteria" in evaluation and "criteria" not in normalized:
            normalized["criteria"] = evaluation["criteria"]
    criteria = _normalize_criteria(normalized.get("criteria") or {})
    normalized["criteria"] = criteria
    return CodingTestConfig.model_validate(normalized)


def _normalize_criteria(raw_criteria: dict[str, Any]) -> dict[str, float]:
    defaults = CriteriaWeights().model_dump()
    merged: dict[str, float] = dict(defaults)
    for key, value in raw_criteria.items():
        if isinstance(value, dict):
            value = value.get("weight", 0)
        merged[key] = float(value)

    total = sum(merged.values())
    if total <= 0:
        return defaults

    # 中文注释：评分权重允许用户写成任意总和，这里统一归一化到 100，避免 prompt 和报告解释不一致。
    factor = 100 / total
    return {key: round(value * factor, 4) for key, value in merged.items()}


def _merge_assignment_overrides(
    payload: dict[str, Any],
    options: ReviewOptions,
    project_root: Path,
) -> None:
    assignment = dict(payload.get("assignment") or {})
    if options.assignment_text:
        assignment["description"] = options.assignment_text
    if options.assignment_file:
        file_path = Path(options.assignment_file).expanduser()
        if not file_path.is_absolute():
            file_path = project_root / file_path
        assignment["file"] = str(file_path)
        assignment.update(_parse_assignment_text(file_path.read_text(encoding="utf-8")))
    if options.assignment_url:
        assignment["url"] = options.assignment_url
    if options.assessment_type != "coding-challenge":
        assignment["type"] = options.assessment_type
    if options.difficulty_level != "mid":
        assignment["difficulty"] = options.difficulty_level
    if options.time_limit is not None:
        assignment["timeLimit"] = options.time_limit
    payload["assignment"] = assignment


def _merge_rubric_overrides(payload: dict[str, Any], options: ReviewOptions) -> None:
    criteria = dict(payload.get("criteria") or {})
    default = ReviewOptions()
    option_weights = {
        "correctness": options.weight_correctness,
        "codeQuality": options.weight_code_quality,
        "architecture": options.weight_architecture,
        "performance": options.weight_performance,
        "testing": options.weight_testing,
    }
    default_weights = {
        "correctness": default.weight_correctness,
        "codeQuality": default.weight_code_quality,
        "architecture": default.weight_architecture,
        "performance": default.weight_performance,
        "testing": default.weight_testing,
    }
    # 中文注释：ReviewOptions 无法区分“用户显式传入默认值”和“解析器默认值”，只覆盖与默认不同的权重。
    for key, value in option_weights.items():
        if value != default_weights[key]:
            criteria[key] = value
    payload["criteria"] = criteria

    scoring = dict(payload.get("scoring") or {})
    if options.scoring_system != default.scoring_system:
        scoring["system"] = options.scoring_system
    if options.max_score != default.max_score:
        scoring["maxScore"] = options.max_score
    if options.passing_threshold != default.passing_threshold:
        scoring["passingThreshold"] = options.passing_threshold
    if options.score_breakdown != default.score_breakdown:
        scoring["breakdown"] = options.score_breakdown
    payload["scoring"] = scoring


def _merge_feedback_overrides(payload: dict[str, Any], options: ReviewOptions) -> None:
    default = ReviewOptions()
    feedback = dict(payload.get("feedback") or {})
    if options.feedback_level != default.feedback_level:
        feedback["level"] = options.feedback_level
    if options.include_examples != default.include_examples:
        feedback["includeExamples"] = options.include_examples
    if options.include_suggestions != default.include_suggestions:
        feedback["includeSuggestions"] = options.include_suggestions
    if options.include_resources != default.include_resources:
        feedback["includeResources"] = options.include_resources
    payload["feedback"] = feedback


def _merge_constraint_overrides(payload: dict[str, Any], options: ReviewOptions) -> None:
    constraints = dict(payload.get("constraints") or {})
    if options.allowed_libraries:
        constraints["allowedLibraries"] = options.allowed_libraries
    if options.forbidden_patterns:
        constraints["forbiddenPatterns"] = options.forbidden_patterns
    if options.language:
        constraints["targetLanguage"] = options.language
    if options.framework:
        constraints["framework"] = options.framework
    if options.node_version:
        constraints["nodeVersion"] = options.node_version
    if options.typescript_version:
        constraints["typescriptVersion"] = options.typescript_version
    if options.memory_limit is not None:
        constraints["memoryLimit"] = options.memory_limit
    if options.execution_timeout is not None:
        constraints["executionTimeout"] = options.execution_timeout
    payload["constraints"] = constraints


def _merge_ai_detection_overrides(payload: dict[str, Any], options: ReviewOptions) -> None:
    ai_detection = dict(payload.get("aiDetection") or payload.get("ai_detection") or {})
    if options.enable_ai_detection:
        ai_detection["enabled"] = True
    if options.ai_detection_threshold != ReviewOptions().ai_detection_threshold:
        ai_detection["threshold"] = options.ai_detection_threshold
    if options.ai_detection_analyzers:
        ai_detection["analyzers"] = options.ai_detection_analyzers
    ai_detection["includeInReport"] = options.ai_detection_include_in_report
    ai_detection["failOnDetection"] = options.ai_detection_fail_on_detection
    payload["aiDetection"] = ai_detection


def _parse_assignment_text(text: str) -> dict[str, Any]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return {}
    title = lines[0].lstrip("#").strip()
    requirements = [
        line.lstrip("-*0123456789. ").strip()
        for line in lines[1:]
        if line.startswith(("-", "*")) or line[:1].isdigit()
    ]
    description_lines = [line for line in lines[1:] if line not in requirements]
    result: dict[str, Any] = {"title": title}
    if description_lines:
        result["description"] = "\n".join(description_lines)
    if requirements:
        result["requirements"] = requirements
    return result
