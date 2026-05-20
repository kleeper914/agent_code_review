"""Command-line interface for the Python AI Code Review MVP."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

import typer

from ..config import (
    ResolvedConfig,
    parse_model,
    provider_display_name,
    resolve_config,
)
from ..llm_clients import create_llm_client, list_supported_models
from ..orchestration import run_review
from ..orchestration.types import ReviewOptions
from ..runtime import RunLevel, RunPhase, create_runtime


app = typer.Typer(add_completion=False, help="AI Code Review Python MVP")


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    try:
        if args and args[0] == "test-model":
            return _run_test_model(args[1:])
        return _run_review_or_models(args)
    except SystemExit as exc:
        return int(exc.code or 0)
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1


def _run_review_or_models(argv: list[str]) -> int:
    parser = _review_parser()
    namespace = parser.parse_args(argv)

    if namespace.models or namespace.listmodels:
        _print_models()
        return 0

    cli_api_keys = _api_keys_from_namespace(namespace)
    options = ReviewOptions(
        target=namespace.target,
        review_type=namespace.review_type,
        output=namespace.output,
        model=namespace.model,
        output_dir=namespace.output_dir,
        include_tests=namespace.include_tests,
        include_project_docs=not namespace.no_project_docs,
        include_dependency_analysis=namespace.include_dependency_analysis,
        diagram=namespace.diagram,
        use_ts_prune=namespace.use_ts_prune,
        use_eslint=namespace.use_eslint,
        trace_code=namespace.trace_code,
        focused=namespace.focused,
        assignment_file=namespace.assignment_file,
        assignment_url=namespace.assignment_url,
        assignment_text=namespace.assignment_text,
        evaluation_template=namespace.evaluation_template,
        template_url=namespace.template_url,
        rubric_file=namespace.rubric_file,
        assessment_type=namespace.assessment_type,
        difficulty_level=namespace.difficulty_level,
        time_limit=namespace.time_limit,
        weight_correctness=namespace.weight_correctness,
        weight_code_quality=namespace.weight_code_quality,
        weight_architecture=namespace.weight_architecture,
        weight_performance=namespace.weight_performance,
        weight_testing=namespace.weight_testing,
        evaluate_documentation=namespace.evaluate_documentation,
        evaluate_git_history=namespace.evaluate_git_history,
        evaluate_edge_cases=namespace.evaluate_edge_cases,
        evaluate_error_handling=namespace.evaluate_error_handling,
        scoring_system=namespace.scoring_system,
        max_score=namespace.max_score,
        passing_threshold=namespace.passing_threshold,
        score_breakdown=not namespace.no_score_breakdown,
        feedback_level=namespace.feedback_level,
        include_examples=not namespace.no_examples,
        include_suggestions=not namespace.no_suggestions,
        include_resources=namespace.include_resources,
        allowed_libraries=_split_csv(namespace.allowed_libraries),
        forbidden_patterns=_split_csv(namespace.forbidden_patterns),
        node_version=namespace.node_version,
        typescript_version=namespace.typescript_version,
        memory_limit=namespace.memory_limit,
        execution_timeout=namespace.execution_timeout,
        enable_ai_detection=namespace.enable_ai_detection,
        ai_detection_threshold=namespace.ai_detection_threshold,
        ai_detection_analyzers=_split_csv(namespace.ai_detection_analyzers) or [
            "git",
            "documentation",
        ],
        ai_detection_include_in_report=namespace.ai_detection_include_in_report,
        ai_detection_fail_on_detection=namespace.ai_detection_fail_on_detection,
        debug=namespace.debug,
        verbose=namespace.verbose,
        quiet=namespace.quiet,
        log_level=namespace.log_level,
        skip_key_check=namespace.skip_key_check,
        api_keys=cli_api_keys,
    )
    config = resolve_config(
        cli_model=options.model,
        cli_output_dir=options.output_dir,
        cli_output_format=options.output,
        cli_api_keys=cli_api_keys,
        cli_log_level=options.log_level,
        debug=options.debug,
        skip_key_check=options.skip_key_check,
    )
    runtime = create_runtime(config, options)
    runtime.emit(
        RunPhase.CONFIG,
        "Configuration resolved",
        metadata={
            "model": config.selected_model,
            "provider": config.provider,
            "outputDir": str(config.output_dir),
            "logLevel": config.log_level,
        },
    )
    try:
        run_review(options, config, runtime)
    except Exception as exc:
        if not any(RunLevel(event.level) is RunLevel.ERROR for event in runtime.events):
            runtime.emit(RunPhase.MODEL, str(exc), level=RunLevel.ERROR)
        return 1
    return 0


def test_model_connection(config: ResolvedConfig) -> str:
    client = create_llm_client(config)
    response = client.generate_review(
        "Reply with a short sentence confirming this model is available for code review."
    )
    return f"✓ {config.selected_model}: {response.content}"


def _review_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="aicode-review")
    parser.add_argument("target", nargs="?", default=".")
    parser.add_argument(
        "--type",
        "-t",
        dest="review_type",
        choices=[
            "quick-fixes",
            "security",
            "architectural",
            "performance",
            "coding-test",
            "unused-code",
        ],
        default="quick-fixes",
    )
    parser.add_argument("--output", "-o", choices=["markdown", "json"], default="markdown")
    parser.add_argument("--output-dir", dest="output_dir")
    parser.add_argument("--model", "-m")
    parser.add_argument("--include-tests", action="store_true")
    parser.add_argument("--no-project-docs", action="store_true")
    parser.add_argument("--include-dependency-analysis", action="store_true")
    parser.add_argument("--diagram", action="store_true")
    parser.add_argument("--use-ts-prune", action="store_true")
    parser.add_argument("--use-eslint", action="store_true")
    parser.add_argument("--trace-code", action="store_true")
    parser.add_argument("--focused", action="store_true")
    parser.add_argument("--assignment-file")
    parser.add_argument("--assignment-url")
    parser.add_argument("--assignment-text")
    parser.add_argument("--evaluation-template")
    parser.add_argument("--template-url")
    parser.add_argument("--rubric-file")
    parser.add_argument(
        "--assessment-type",
        choices=["coding-challenge", "take-home", "live-coding", "code-review"],
        default="coding-challenge",
    )
    parser.add_argument(
        "--difficulty-level",
        choices=["junior", "mid", "senior", "lead", "architect"],
        default="mid",
    )
    parser.add_argument("--time-limit", type=int)
    parser.add_argument("--weight-correctness", type=int, default=30)
    parser.add_argument("--weight-code-quality", type=int, default=25)
    parser.add_argument("--weight-architecture", type=int, default=20)
    parser.add_argument("--weight-performance", type=int, default=15)
    parser.add_argument("--weight-testing", type=int, default=10)
    parser.add_argument("--evaluate-documentation", action="store_true")
    parser.add_argument("--evaluate-git-history", action="store_true")
    parser.add_argument("--evaluate-edge-cases", action="store_true")
    parser.add_argument("--evaluate-error-handling", action="store_true")
    parser.add_argument(
        "--scoring-system",
        choices=["numeric", "letter", "pass-fail", "custom"],
        default="numeric",
    )
    parser.add_argument("--max-score", type=int, default=100)
    parser.add_argument("--passing-threshold", type=int, default=70)
    parser.add_argument("--no-score-breakdown", action="store_true")
    parser.add_argument(
        "--feedback-level",
        choices=["basic", "detailed", "comprehensive"],
        default="detailed",
    )
    parser.add_argument("--no-examples", action="store_true")
    parser.add_argument("--no-suggestions", action="store_true")
    parser.add_argument("--include-resources", action="store_true")
    parser.add_argument("--allowed-libraries")
    parser.add_argument("--forbidden-patterns")
    parser.add_argument("--node-version")
    parser.add_argument("--typescript-version")
    parser.add_argument("--memory-limit", type=int)
    parser.add_argument("--execution-timeout", type=int)
    parser.add_argument("--enable-ai-detection", action="store_true")
    parser.add_argument("--ai-detection-threshold", type=float, default=0.7)
    parser.add_argument("--ai-detection-analyzers", default="git,documentation")
    parser.add_argument(
        "--ai-detection-include-in-report",
        action=argparse.BooleanOptionalAction,
        default=True,
    )
    parser.add_argument("--ai-detection-fail-on-detection", action="store_true")
    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--quiet", action="store_true")
    parser.add_argument("--log-level", choices=["debug", "info", "warning", "error", "none"])
    parser.add_argument("--skip-key-check", action="store_true")
    parser.add_argument("--models", action="store_true")
    parser.add_argument("--listmodels", action="store_true")
    _add_api_key_options(parser)
    return parser


def _add_api_key_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--google-api-key")
    parser.add_argument("--anthropic-api-key")
    parser.add_argument("--openrouter-api-key")
    parser.add_argument("--openai-api-key")
    parser.add_argument("--deepseek-api-key")


def _api_keys_from_namespace(namespace: argparse.Namespace) -> dict[str, str]:
    keys = {
        "google": namespace.google_api_key,
        "anthropic": namespace.anthropic_api_key,
        "openrouter": namespace.openrouter_api_key,
        "openai": namespace.openai_api_key,
        "deepseek": namespace.deepseek_api_key,
    }
    return {provider: value for provider, value in keys.items() if value}


def _split_csv(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def _print_models() -> None:
    print("Supported models:")
    for model in list_supported_models():
        provider, _ = parse_model(model.key)
        print(
            f"- {model.key} | {provider_display_name(provider)} | "
            f"{model.display_name} | {model.context_window:,} context"
        )


# ========= test ==============

def _test_model_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="aicode-review test-model")
    parser.add_argument("model_arg", nargs="?")
    parser.add_argument("--model", "-m")
    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--quiet", action="store_true")
    parser.add_argument("--log-level", choices=["debug", "info", "warning", "error", "none"])
    _add_api_key_options(parser)
    return parser


def _run_test_model(argv: list[str]) -> int:
    parser = _test_model_parser()
    namespace = parser.parse_args(argv)
    selected_model = namespace.model or namespace.model_arg
    cli_api_keys = _api_keys_from_namespace(namespace)
    config = resolve_config(
        cli_model=selected_model,
        cli_api_keys=cli_api_keys,
        cli_log_level=namespace.log_level,
        debug=namespace.debug,
    )
    options = ReviewOptions(
        model=selected_model,
        debug=namespace.debug,
        verbose=namespace.verbose,
        quiet=namespace.quiet,
        log_level=namespace.log_level,
    )
    runtime = create_runtime(config, options)
    runtime.emit(
        RunPhase.TEST_MODEL,
        "Testing model",
        metadata={"model": config.selected_model, "provider": config.provider},
    )

    try:
        message = test_model_connection(config)
    except Exception as exc:
        runtime.emit(
            RunPhase.TEST_MODEL,
            str(exc),
            level=RunLevel.ERROR,
            metadata={"model": config.selected_model, "provider": config.provider},
        )
        return 1

    print(message)
    return 0