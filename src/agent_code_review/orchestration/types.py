"""Shared data models for review orchestration."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from ..discovery import DiscoveredFile

PUBLIC_REVIEW_TYPES = (
    "quick-fixes",
    "architectural",
    "security",
    "performance",
    "unused-code",
    "focused-unused-code",
    "code-tracing-unused-code",
    "consolidated",
    "best-practices",
    "evaluation",
    "extract-patterns",
    "coding-test",
    "ai-integration",
    "cloud-native",
    "developer-experience",
    "comprehensive",
)

ReviewType = Literal[
    "quick-fixes",
    "architectural",
    "security",
    "performance",
    "unused-code",
    "focused-unused-code",
    "code-tracing-unused-code",
    "consolidated",
    "best-practices",
    "evaluation",
    "extract-patterns",
    "coding-test",
    "ai-integration",
    "cloud-native",
    "developer-experience",
    "comprehensive",
]
OutputFormat = Literal["markdown", "json"]
PriorityFilter = Literal["h", "m", "l", "a"]
PromptFragmentPosition = Literal["start", "middle", "end"]
AssessmentType = Literal["coding-challenge", "take-home", "live-coding", "code-review"]
DifficultyLevel = Literal["junior", "mid", "senior", "lead", "architect"]
ScoringSystem = Literal["numeric", "letter", "pass-fail", "custom"]
FeedbackLevel = Literal["basic", "detailed", "comprehensive"]


class PromptFragment(BaseModel):
    """User-provided prompt text inserted around the selected template."""

    content: str
    position: PromptFragmentPosition = "middle"
    priority: int = 5


class ReviewOptions(BaseModel):
    """Normalized review options from the CLI."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    target: str = "."
    review_type: ReviewType = "quick-fixes"
    output: OutputFormat = "markdown"
    model: str | None = None
    writer_model: str | None = None
    output_dir: str | None = None
    language: str | None = None
    framework: str | None = None
    prompt_file: str | None = None
    prompt_fragments: list[PromptFragment] = Field(default_factory=list)
    interactive: bool = False
    return_only: bool = False
    priority_filter: PriorityFilter | None = None
    test_api: bool = False
    stdout: bool = False
    include_tests: bool = False
    include_project_docs: bool = True
    include_dependency_analysis: bool | None = None
    estimate: bool = False
    multi_pass: bool = False
    force_single_pass: bool = False
    context_maintenance_factor: float = 0.15
    batch_token_limit: int | None = None
    enable_semantic_chunking: bool = True
    diagram: bool = False
    use_ts_prune: bool = False
    use_eslint: bool = False
    trace_code: bool = False
    focused: bool = False
    strategy: str | None = None
    plugins_dir: str | None = None
    coding_test_config: str | None = None
    assignment_file: str | None = None
    assignment_url: str | None = None
    assignment_text: str | None = None
    evaluation_template: str | None = None
    template_url: str | None = None
    rubric_file: str | None = None
    assessment_type: AssessmentType = "coding-challenge"
    difficulty_level: DifficultyLevel = "mid"
    time_limit: int | None = None
    weight_correctness: int = 30
    weight_code_quality: int = 25
    weight_architecture: int = 20
    weight_performance: int = 15
    weight_testing: int = 10
    evaluate_documentation: bool = False
    evaluate_git_history: bool = False
    evaluate_edge_cases: bool = False
    evaluate_error_handling: bool = False
    scoring_system: ScoringSystem = "numeric"
    max_score: int = 100
    passing_threshold: int = 70
    score_breakdown: bool = True
    feedback_level: FeedbackLevel = "detailed"
    include_examples: bool = True
    include_suggestions: bool = True
    include_resources: bool = False
    allowed_libraries: list[str] = Field(default_factory=list)
    forbidden_patterns: list[str] = Field(default_factory=list)
    node_version: str | None = None
    typescript_version: str | None = None
    memory_limit: int | None = None
    execution_timeout: int | None = None
    enable_ai_detection: bool = False
    ai_detection_threshold: float = 0.7
    ai_detection_analyzers: list[str] = Field(default_factory=lambda: ["git", "documentation"])
    ai_detection_include_in_report: bool = True
    ai_detection_fail_on_detection: bool = False
    use_memory: bool = False
    debug: bool = False
    verbose: bool = False
    quiet: bool = False
    log_level: str | None = None
    skip_key_check: bool = False
    api_keys: dict[str, str] = Field(default_factory=dict)
    otel_enabled: bool = False
    otel_endpoint: str | None = None
    otel_service_name: str = "aicode-review-python"
    otel_console: bool = False


class ReviewResult(BaseModel):
    """Standard review result consumed by Markdown and JSON formatters."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    content: str
    file_path: str
    review_type: str
    timestamp: str
    model_used: str
    files: list[DiscoveredFile] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    output_path: Path | None = None


class PassResult(BaseModel):
    """One completed multi-pass review invocation."""

    pass_number: int
    files: list[str] = Field(default_factory=list)
    estimated_token_count: int = 0
    content: str = ""
    success: bool = True
    error: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
