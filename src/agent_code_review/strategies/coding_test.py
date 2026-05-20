"""Coding-test review strategy."""

from __future__ import annotations

import json

from ..discovery import ProjectContext
from ..evaluation import build_ai_detection_summary
from ..orchestration.types import ReviewOptions

from .base import (
    BaseReviewStrategy,
    ContextSection,
    EnhancedReviewContext,
    PostprocessResult,
    ReviewIntent
)
from .context import directory_summary_section, read_optional_file


class CodingTestReviewStrategy(BaseReviewStrategy):
    """
    Prepare coding-test assessment intent and evaluation context.
    """

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
            schema_name="coding-test-assessment"
        )
    
    def enhance_context(
        self,
        context: ProjectContext,
        options: ReviewOptions,
    ) -> EnhancedReviewContext:
        assignment_text, assignment_file_metadata = read_optional_file(
            options.assignment_file,
            context.project_root
        )
        rubric_text, rubric_file_metadata = read_optional_file(options.rubric_file, context.project_root)
        ai_detection = build_ai_detection_summary(context, options)
        evaluation_payload = {
            "assignment": {
                "text": options.assignment_text or assignment_text,
                "url": options.assignment_url,
                "file": assignment_file_metadata,
                "type": options.assessment_type,
                "difficulty": options.difficulty_level,
                "timeLimitMinutes": options.time_limit,
            },
            "rubric": {
                "file": rubric_file_metadata,
                "text": rubric_text,
                "weights": {
                    "correctness": options.weight_correctness,
                    "code_quality": options.weight_code_quality,
                    "architecture": options.weight_architecture,
                    "performance": options.weight_performance,
                    "testing": options.weight_testing,
                },
                "scoring": {
                    "system": options.scoring_system,
                    "maxScore": options.max_score,
                    "passingThreshold": options.passing_threshold,
                    "scoreBreakdown": options.score_breakdown,
                },
            },
            "feedback": {
                "level": options.feedback_level,
                "includeExamples": options.include_examples,
                "includeSuggestions": options.include_suggestions,
                "includeResources": options.include_resources,
            },
            "constraints": {
                "allowedLibraries": options.allowed_libraries,
                "forbiddenPatterns": options.forbidden_patterns,
                "nodeVersion": options.node_version,
                "typescriptVersion": options.typescript_version,
                "memoryLimitMb": options.memory_limit,
                "executionTimeoutSeconds": options.execution_timeout,
            },
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
                content=f"AI detection summary:\n{json.dumps(ai_detection, ensure_ascii=False, indent=2)}",
                source="ai-detection",
                metadata={"enabled": options.enable_ai_detection},
            ),
        ]
        return EnhancedReviewContext(
            context_sections=sections,
            metadata=self._base_metadata(
                assessment_type=options.assessment_type,
                difficulty=options.difficulty_level,
                ai_detection=ai_detection,
            ),
            ai_detection=ai_detection
        )
    
    def postprocess_response(
        self,
        content: str,
        context: ProjectContext,
        options: ReviewOptions,
        enhanced_context: EnhancedReviewContext,
    ) -> PostprocessResult:
        base = super().postprocess_response(content, context, options, enhanced_context)
        base.metadata["coding_test"] = {
            "assessmentType": options.assessment_type,
            "difficultyLevel": options.difficulty_level,
            "scoringSystem": options.scoring_system,
            "maxScore": options.max_score,
            "passingThreshold": options.passing_threshold,
            "weights": {
                "correctness": options.weight_correctness,
                "codeQuality": options.weight_code_quality,
                "architecture": options.weight_architecture,
                "performance": options.weight_performance,
                "testing": options.weight_testing,
            },
        }
        return base


def _coding_test_context_text(payload: dict) -> str:
    assignment = payload["assignment"]
    rubric = payload["rubric"]
    feedback = payload["feedback"]
    constraints = payload["constraints"]
    focus = payload["focus"]
    lines = [
        f"Assessment type: {assignment['type']}",
        f"Difficulty level: {assignment['difficulty']}",
    ]
    if assignment.get("timeLimitMinutes"):
        lines.append(f"Time limit: {assignment['timeLimitMinutes']} minutes")
    if assignment.get("text"):
        lines.append(f"Assignment:\n{assignment['text']}")
    if assignment.get("url"):
        lines.append(f"Assignment URL: {assignment['url']}")
    if rubric.get("text"):
        lines.append(f"Rubric:\n{rubric['text']}")
    weights = rubric["weights"]
    lines.append(
        "Weights: "
        f"correctness: {weights['correctness']}, "
        f"code_quality: {weights['code_quality']}, "
        f"architecture: {weights['architecture']}, "
        f"performance: {weights['performance']}, "
        f"testing: {weights['testing']}"
    )
    scoring = rubric["scoring"]
    lines.append(
        "Scoring: "
        f"{scoring['system']}, max {scoring['maxScore']}, "
        f"passing threshold {scoring['passingThreshold']}, "
        f"breakdown {scoring['scoreBreakdown']}"
    )
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
