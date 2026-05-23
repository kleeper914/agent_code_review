"""Coding-test review strategy."""

from __future__ import annotations

import json

from ..discovery import ProjectContext
from ..evaluation import build_coding_test_config
from ..evaluation.detection import build_ai_detection_result
from ..orchestration.types import ReviewOptions

from .base import (
    BaseReviewStrategy,
    ContextSection,
    EnhancedReviewContext,
    PostprocessResult,
    ReviewIntent,
)
from .context import directory_summary_section, read_optional_file


class CodingTestReviewStrategy(BaseReviewStrategy):
    """Prepare coding-test assessment intent and evaluation context."""

    def __init__(self) -> None:
        super().__init__("coding-test")

    def describe_intent(self, options: ReviewOptions) -> ReviewIntent:
        return ReviewIntent(
            review_type=self.review_type,
            title="Coding Test Assessment",
            instructions=(
                "Act as a fair senior hiring evaluator. Assess the submitted code against the "
                "assignment, expected difficulty, scoring rubric, correctness, code quality, "
                "architecture, performance, tests, constraints, and optional AI-assistance "
                "signals."
            ),
            focus_areas=[
                "assignment correctness",
                "code quality",
                "architecture and maintainability",
                "performance",
                "testing",
                "candidate feedback",
            ],
            output_expectations=[
                "Return a structured assessment with score, pass/fail recommendation, strengths, and risks.",
                "Use the configured weights and passing threshold.",
                "Include concrete evidence from the submitted files.",
            ],
            schema_name="coding-test-assessment",
        )

    def enhance_context(
        self,
        context: ProjectContext,
        options: ReviewOptions,
    ) -> EnhancedReviewContext:
        rubric_text, rubric_file_metadata = read_optional_file(
            options.rubric_file, context.project_root
        )
        config = build_coding_test_config(options, context.project_root)
        ai_detection_result = build_ai_detection_result(
            context,
            threshold=config.ai_detection.threshold,
            analyzers=config.ai_detection.analyzers,
            enabled=config.ai_detection.enabled,
            fail_on_detection=config.ai_detection.fail_on_detection,
        )
        ai_detection = ai_detection_result.to_report_dict(
            fail_on_detection=config.ai_detection.fail_on_detection
        )
        ai_detection["threshold"] = config.ai_detection.threshold
        ai_detection["analyzers"] = config.ai_detection.analyzers
        ai_detection["includeInReport"] = config.ai_detection.include_in_report
        evaluation_payload = {
            "config": config.model_dump(by_alias=True),
            "rubricFile": rubric_file_metadata,
            "rubricText": rubric_text,
            "cliWeightOverrides": _cli_weight_overrides(options),
            "focus": {
                "documentation": options.evaluate_documentation,
                "gitHistory": options.evaluate_git_history,
                "edgeCases": options.evaluate_edge_cases,
                "errorHandling": options.evaluate_error_handling,
            },
        }
        sections = [
            self._project_summary_section(context),
            directory_summary_section(context),
            ContextSection(
                title="Coding test assignment and rubric context",
                content=_coding_test_context_text(evaluation_payload),
                source="coding-test",
                metadata={"format": "text"},
            ),
            ContextSection(
                title="AI detection context",
                content=f"AI detection result:\n{json.dumps(ai_detection, ensure_ascii=False, indent=2)}",
                source="ai-detection",
                metadata={"enabled": config.ai_detection.enabled},
            ),
        ]
        return EnhancedReviewContext(
            context_sections=sections,
            metadata=self._base_metadata(
                assessment_type=config.assignment.type,
                difficulty=config.assignment.difficulty,
                ai_detection=ai_detection,
                coding_test=config.model_dump(by_alias=True),
            ),
            ai_detection=ai_detection,
        )

    def postprocess_response(
        self,
        content: str,
        context: ProjectContext,
        options: ReviewOptions,
        enhanced_context: EnhancedReviewContext,
    ) -> PostprocessResult:
        base = super().postprocess_response(content, context, options, enhanced_context)
        config = enhanced_context.metadata.get("coding_test") or {}
        scoring = config.get("scoring") or {}
        assignment = config.get("assignment") or {}
        base.metadata["coding_test"] = {
            "assessmentType": assignment.get("type", options.assessment_type),
            "difficultyLevel": assignment.get("difficulty", options.difficulty_level),
            "scoringSystem": scoring.get("system", options.scoring_system),
            "maxScore": scoring.get("maxScore", options.max_score),
            "passingThreshold": scoring.get("passingThreshold", options.passing_threshold),
            "weights": config.get("criteria") or {},
        }
        return base


def _coding_test_context_text(payload: dict) -> str:
    config = payload["config"]
    assignment = config["assignment"]
    feedback = config["feedback"]
    constraints = config["constraints"]
    scoring = config["scoring"]
    weights = config["criteria"]
    focus = payload["focus"]
    lines = [
        "## Assignment Context",
        f"Assessment type: {assignment['type']}",
        f"Difficulty level: {assignment['difficulty']}",
        f"Assignment title: {assignment.get('title')}",
    ]
    if assignment.get("timeLimit"):
        lines.append(f"Time limit: {assignment['timeLimit']} minutes")
    if assignment.get("description"):
        lines.append(f"Assignment:\n{assignment['description']}")
    if assignment.get("requirements"):
        lines.append("Requirements:")
        lines.extend(f"- {item}" for item in assignment["requirements"])
    if assignment.get("url"):
        lines.append(f"Assignment URL: {assignment['url']}")
    if payload.get("rubricText"):
        lines.append(f"Rubric:\n{payload['rubricText']}")
    lines.append("## Evaluation Criteria")
    for name, weight in weights.items():
        if weight:
            lines.append(f"- {name}: {weight}")
    if payload.get("cliWeightOverrides"):
        lines.append("CLI Weight Overrides:")
        for name, weight in payload["cliWeightOverrides"].items():
            lines.append(f"- {name}: {weight}")
    lines.append("## Scoring")
    lines.append(
        "Scoring: "
        f"{scoring['system']}, max {scoring['maxScore']}, "
        f"passing threshold {scoring['passingThreshold']}, "
        f"breakdown {scoring['breakdown']}"
    )
    lines.append("## Feedback")
    lines.append(
        "Feedback: "
        f"{feedback['level']}, examples {feedback['includeExamples']}, "
        f"suggestions {feedback['includeSuggestions']}, resources {feedback['includeResources']}"
    )
    if any(constraints.values()):
        lines.append(f"Constraints:\n{json.dumps(constraints, ensure_ascii=False, indent=2)}")
    if any(focus.values()):
        lines.append(f"Extra evaluation focus:\n{json.dumps(focus, ensure_ascii=False, indent=2)}")
    return "\n".join(lines)


def _cli_weight_overrides(options: ReviewOptions) -> dict[str, int]:
    defaults = ReviewOptions()
    values = {
        "correctness": options.weight_correctness,
        "codeQuality": options.weight_code_quality,
        "architecture": options.weight_architecture,
        "performance": options.weight_performance,
        "testing": options.weight_testing,
    }
    default_values = {
        "correctness": defaults.weight_correctness,
        "codeQuality": defaults.weight_code_quality,
        "architecture": defaults.weight_architecture,
        "performance": defaults.weight_performance,
        "testing": defaults.weight_testing,
    }
    return {
        key: value
        for key, value in values.items()
        if value != default_values[key]
    }
