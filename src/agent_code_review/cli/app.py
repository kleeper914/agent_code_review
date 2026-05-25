"""Command-line interface for the Python AI Code Review MVP."""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import yaml

from ..config import (
    ApiKeys,
    ResolvedConfig,
    parse_model,
    provider_display_name,
    require_api_key,
    resolve_config,
)
from ..llm_clients import create_llm_client, list_supported_models
from ..orchestration import ReviewService
from ..orchestration.reports import format_review_result
from ..orchestration.types import ReviewOptions
from ..orchestration.types import PUBLIC_REVIEW_TYPES
from ..observability import configure_observability
from ..runtime import RunLevel, RunPhase, create_runtime


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    try:
        if args and args[0] == "generate-config":
            return _run_generate_config(args[1:])
        if args and args[0] == "validate-config":
            return _run_validate_config(args[1:])
        if args and args[0] == "init":
            return _run_init(args[1:])
        if args and args[0] == "install":
            return _run_install(args[1:])
        if args and args[0] == "test-build":
            return _run_test_build(args[1:])
        if args and args[0] == "sync-github-projects":
            return _run_sync_github_projects(args[1:])
        if args and args[0] == "mcp":
            return _run_mcp(args[1:])
        if args and args[0] == "plugins":
            return _run_plugins(args[1:])
        if args and args[0] == "prompt-feedback":
            return _run_prompt_feedback(args[1:])
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
        writer_model=namespace.writer_model,
        output_dir=namespace.output_dir,
        language=namespace.language,
        framework=namespace.framework,
        prompt_file=namespace.prompt_file,
        interactive=namespace.interactive,
        return_only=namespace.return_only,
        priority_filter=namespace.priority_filter,
        test_api=namespace.test_api,
        stdout=namespace.stdout,
        include_tests=namespace.include_tests,
        include_project_docs=not namespace.no_project_docs,
        include_dependency_analysis=namespace.include_dependency_analysis,
        estimate=namespace.estimate,
        multi_pass=namespace.multi_pass,
        force_single_pass=namespace.force_single_pass,
        context_maintenance_factor=namespace.context_maintenance_factor,
        batch_token_limit=namespace.batch_token_limit,
        enable_semantic_chunking=namespace.enable_semantic_chunking,
        diagram=namespace.diagram,
        use_ts_prune=namespace.use_ts_prune,
        use_eslint=namespace.use_eslint,
        trace_code=namespace.trace_code,
        focused=namespace.focused,
        strategy=namespace.strategy,
        plugins_dir=namespace.plugins_dir,
        coding_test_config=namespace.coding_test_config,
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
        ai_detection_analyzers=_split_csv(namespace.ai_detection_analyzers)
        or [
            "git",
            "documentation",
        ],
        ai_detection_include_in_report=namespace.ai_detection_include_in_report,
        ai_detection_fail_on_detection=namespace.ai_detection_fail_on_detection,
        use_memory=namespace.use_memory,
        debug=namespace.debug,
        verbose=namespace.verbose,
        quiet=namespace.quiet,
        log_level=namespace.log_level,
        skip_key_check=namespace.skip_key_check,
        api_keys=cli_api_keys,
        otel_enabled=namespace.otel_enabled or _env_flag("AI_CODE_REVIEW_OTEL_ENABLED"),
        otel_endpoint=namespace.otel_endpoint or os.getenv("AI_CODE_REVIEW_OTEL_ENDPOINT"),
        otel_service_name=namespace.otel_service_name
        or os.getenv("AI_CODE_REVIEW_OTEL_SERVICE_NAME")
        or "aicode-review-python",
        otel_console=namespace.otel_console or _env_flag("AI_CODE_REVIEW_OTEL_CONSOLE"),
    )
    configure_observability(
        enabled=options.otel_enabled,
        endpoint=options.otel_endpoint,
        service_name=options.otel_service_name,
        console=options.otel_console,
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
    if options.interactive:
        runtime.emit(
            RunPhase.CONFIG,
            "Interactive mode is accepted for compatibility; structured processing is planned for a later phase.",
            level=RunLevel.WARNING,
            metadata={"interactive": True},
        )
    if options.test_api:
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
        runtime.emit(
            RunPhase.TEST_MODEL,
            "Model connection verified",
            metadata={"model": config.selected_model, "provider": config.provider},
        )
        if options.verbose:
            print(message, file=sys.stderr)
    try:
        result = ReviewService().run_review(options, config, runtime)
    except Exception as exc:
        if not any(RunLevel(event.level) is RunLevel.ERROR for event in runtime.events):
            runtime.emit(RunPhase.MODEL, str(exc), level=RunLevel.ERROR)
        return 1
    if options.stdout:
        print(format_review_result(result, options.output))
    return 0


def _run_mcp(argv: list[str]) -> int:
    parser = _mcp_parser()
    namespace = parser.parse_args(argv)
    return run_mcp_server(
        name=namespace.name,
        debug=namespace.debug,
        max_requests=namespace.max_requests,
        timeout=namespace.timeout,
    )


def _run_plugins(argv: list[str]) -> int:
    parser = _plugins_parser()
    namespace = parser.parse_args(argv)
    if namespace.plugins_command != "list":
        parser.error("plugins requires a subcommand")
    from ..plugins import (
        create_default_registry,
        load_plugins_from_directory,
        plugin_to_row,
    )

    registry = create_default_registry()
    load_plugins_from_directory(namespace.plugins_dir, registry)
    rows = [plugin_to_row(plugin) for plugin in registry.list_plugins()]
    for row in rows:
        print(f"{row['name']}\t{row['source']}\t{row['description']}")
    return 0


def _run_prompt_feedback(argv: list[str]) -> int:
    parser = _prompt_feedback_parser()
    namespace = parser.parse_args(argv)
    from ..prompts.feedback import PromptFeedback, PromptFeedbackStore, PromptOptimizer

    store = PromptFeedbackStore.for_project(Path.cwd())
    command = namespace.feedback_command
    if command == "add":
        store.add(
            PromptFeedback(
                review_type=namespace.review_type,
                prompt=namespace.prompt,
                rating=namespace.rating,
                comments=namespace.comments,
                positive_aspects=_split_csv(namespace.positive_aspects),
                negative_aspects=_split_csv(namespace.negative_aspects),
            )
        )
        print(f"Stored feedback for {namespace.review_type}")
        return 0
    if command == "list":
        for feedback_entry in store.list(namespace.review_type):
            print(
                f"{feedback_entry.rating}/5\t{feedback_entry.review_type}\t{feedback_entry.prompt}"
            )
        return 0
    if command == "best":
        best_entry = store.best(namespace.review_type)
        if best_entry is None:
            print(f"No feedback found for {namespace.review_type}")
            return 1
        if namespace.as_json:
            print(json.dumps(best_entry.model_dump(mode="json"), ensure_ascii=False))
        else:
            print(f"{best_entry.rating}/5\t{best_entry.review_type}\t{best_entry.prompt}")
        return 0
    if command == "optimize":
        config = resolve_config(
            cli_model=namespace.model,
            cli_api_keys=_api_keys_from_namespace(namespace),
            debug=namespace.debug,
            cli_log_level=namespace.log_level,
        )
        optimized = PromptOptimizer(store).optimize(
            review_type=namespace.review_type,
            original_prompt=namespace.prompt,
            review_result=namespace.review_result,
            config=config,
        )
        print(optimized)
        return 0
    parser.error("prompt-feedback requires a subcommand")
    return 2


def _run_generate_config(argv: list[str]) -> int:
    parser = _generate_config_parser()
    namespace = parser.parse_args(argv)
    output_path = Path(
        namespace.output
        or (".ai-code-review.json" if namespace.format == "json" else ".ai-code-review/config.yaml")
    )
    if output_path.exists() and not namespace.force:
        print(
            f"Configuration file already exists at {output_path}. Use --force to overwrite.",
            file=sys.stderr,
        )
        return 1
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = _sample_config_payload()
    if namespace.format == "json":
        output_path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
    else:
        output_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    print(f"Sample {namespace.format.upper()} configuration file created at: {output_path}")
    return 0


def _run_validate_config(argv: list[str]) -> int:
    parser = _validate_config_parser()
    namespace = parser.parse_args(argv)
    try:
        config = _resolve_config_for_validation(namespace.config)
        require_api_key(config)
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1
    if namespace.test_connections:
        try:
            print(test_model_connection(config))
        except Exception as exc:
            print(str(exc), file=sys.stderr)
            return 1
    else:
        print(f"Configuration is valid for {config.selected_model}")
    return 0


def _run_init(argv: list[str]) -> int:
    parser = _init_parser()
    namespace = parser.parse_args(argv)
    config_path = Path(".ai-code-review/config.yaml")
    if config_path.exists() and not namespace.force:
        print(f"Configuration already exists at {config_path}")
        return 0
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        yaml.safe_dump(_sample_config_payload(), sort_keys=False), encoding="utf-8"
    )
    print(f"Project configuration initialized at {config_path}")
    return 0


def _run_install(argv: list[str]) -> int:
    parser = _install_parser()
    namespace = parser.parse_args(argv)
    output_path = Path(".mcp.json")
    if output_path.exists() and not namespace.force:
        print(f"Project MCP config already exists at {output_path}")
        return 0
    payload: dict[str, Any] = {
        "mcpServers": {
            "ai-code-review": {
                "command": "ai-code-review",
                "args": ["mcp"],
                "env": {"PROJECT_PATH": str(Path.cwd())},
            }
        }
    }
    output_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"Project-level MCP config created at {output_path}")
    return 0


def _run_test_build(argv: list[str]) -> int:
    parser = _test_build_parser()
    namespace = parser.parse_args(argv)
    from ..strategies import supported_review_types

    review_types = list(supported_review_types())
    models = list(list_supported_models())
    payload = {
        "summary": {
            "supportedReviewTypes": len(review_types),
            "registeredModels": len(models),
            "remoteModelTests": "deferred-to-phase-9",
        },
        "reviewTypes": review_types,
        "models": [model.key for model in models],
    }
    if namespace.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print("Local Phase 7 build compatibility check passed")
        print(f"Supported review types: {len(review_types)}")
        print(f"Registered models: {len(models)}")
        print("Remote model matrix testing is deferred to Phase 9.")
    return 0


def _run_sync_github_projects(argv: list[str]) -> int:
    parser = _sync_github_projects_parser()
    parser.parse_args(argv)
    print(
        "sync-github-projects is recognized by the Python CLI, but full GitHub Projects "
        "sync is deferred to Phase 11.",
        file=sys.stderr,
    )
    return 1


def run_mcp_server(
    *,
    name: str = "ai-code-review",
    debug: bool = False,
    max_requests: int = 5,
    timeout: int = 300000,
) -> int:
    from ..mcp_server.server import run_mcp_server as start_server

    return start_server(name=name, debug=debug, max_requests=max_requests, timeout=timeout)


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
        choices=PUBLIC_REVIEW_TYPES,
        default="quick-fixes",
    )
    parser.add_argument("--output", "-o", choices=["markdown", "json"], default="markdown")
    parser.add_argument("--output-dir", dest="output_dir")
    parser.add_argument("--model", "-m")
    parser.add_argument("--writer-model")
    parser.add_argument("--language")
    parser.add_argument("--framework")
    parser.add_argument("--prompt-file")
    parser.add_argument("--interactive", "-i", action="store_true")
    parser.add_argument("--return-only", action="store_true")
    parser.add_argument("--priority-filter", choices=["h", "m", "l", "a"])
    parser.add_argument("--test-api", action="store_true")
    parser.add_argument("--stdout", action="store_true")
    parser.add_argument("--include-tests", action="store_true")
    parser.add_argument("--no-project-docs", action="store_true")
    parser.add_argument("--include-dependency-analysis", action="store_true")
    parser.add_argument("--estimate", action="store_true")
    parser.add_argument("--multi-pass", action="store_true")
    parser.add_argument("--force-single-pass", action="store_true")
    parser.add_argument("--context-maintenance-factor", type=float, default=0.15)
    parser.add_argument("--batch-token-limit", type=int)
    parser.add_argument(
        "--enable-semantic-chunking",
        action=argparse.BooleanOptionalAction,
        default=True,
    )
    parser.add_argument("--use-memory", action="store_true")
    parser.add_argument("--diagram", action="store_true")
    parser.add_argument("--use-ts-prune", action="store_true")
    parser.add_argument("--use-eslint", action="store_true")
    parser.add_argument("--trace-code", action="store_true")
    parser.add_argument("--focused", action="store_true")
    parser.add_argument("--strategy")
    parser.add_argument("--plugins-dir")
    parser.add_argument("--coding-test-config")
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
    parser.add_argument("--otel-enabled", action="store_true")
    parser.add_argument("--otel-endpoint")
    parser.add_argument("--otel-service-name")
    parser.add_argument("--otel-console", action="store_true")
    parser.add_argument("--models", action="store_true")
    parser.add_argument("--listmodels", action="store_true")
    _add_api_key_options(parser)
    return parser


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


def _mcp_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="aicode-review mcp")
    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--name", default="ai-code-review")
    parser.add_argument("--max-requests", type=int, default=5)
    parser.add_argument("--timeout", type=int, default=300000)
    return parser


def _plugins_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="aicode-review plugins")
    subparsers = parser.add_subparsers(dest="plugins_command")
    list_parser = subparsers.add_parser("list")
    list_parser.add_argument("--plugins-dir")
    return parser


def _prompt_feedback_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="aicode-review prompt-feedback")
    subparsers = parser.add_subparsers(dest="feedback_command")

    add_parser = subparsers.add_parser("add")
    add_parser.add_argument("--type", dest="review_type", required=True)
    add_parser.add_argument("--prompt", required=True)
    add_parser.add_argument("--rating", type=int, required=True)
    add_parser.add_argument("--comments")
    add_parser.add_argument("--positive-aspects")
    add_parser.add_argument("--negative-aspects")

    list_parser = subparsers.add_parser("list")
    list_parser.add_argument("--type", dest="review_type")

    best_parser = subparsers.add_parser("best")
    best_parser.add_argument("--type", dest="review_type", required=True)
    best_parser.add_argument("--json", action="store_true", dest="as_json")

    optimize_parser = subparsers.add_parser("optimize")
    optimize_parser.add_argument("--type", dest="review_type", required=True)
    optimize_parser.add_argument("--prompt", required=True)
    optimize_parser.add_argument("--review-result", required=True)
    optimize_parser.add_argument("--model")
    optimize_parser.add_argument("--debug", action="store_true")
    optimize_parser.add_argument(
        "--log-level", choices=["debug", "info", "warning", "error", "none"]
    )
    _add_api_key_options(optimize_parser)

    return parser


def _generate_config_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="aicode-review generate-config")
    parser.add_argument("--output", "-o")
    parser.add_argument("--format", "-f", choices=["yaml", "json"], default="yaml")
    parser.add_argument("--force", action="store_true")
    return parser


def _validate_config_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="aicode-review validate-config")
    parser.add_argument("--config")
    parser.add_argument("--test-connections", action="store_true")
    return parser


def _init_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="aicode-review init")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--debug", action="store_true")
    return parser


def _install_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="aicode-review install")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--debug", action="store_true")
    return parser


def _test_build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="aicode-review test-build")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--fail-on-error", action="store_true")
    parser.add_argument("--provider")
    return parser


def _sync_github_projects_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="aicode-review sync-github-projects")
    parser.add_argument("--direction", choices=["to-github", "from-github"], default="to-github")
    parser.add_argument("--project-path")
    parser.add_argument("--description-only", action="store_true")
    parser.add_argument("--token")
    parser.add_argument("--org")
    parser.add_argument("--output-dir")
    parser.add_argument("--debug", action="store_true")
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


def _env_flag(name: str) -> bool:
    return os.getenv(name, "").lower() in {"1", "true", "yes", "on"}


def _sample_config_payload() -> dict[str, object]:
    return {
        "api": {
            "model": "gemini:gemini-2.5-pro",
            "keys": {
                "google": "your_google_api_key_here",
                "anthropic": "your_anthropic_api_key_here",
                "openrouter": "your_openrouter_api_key_here",
                "openai": "your_openai_api_key_here",
                "deepseek": "your_deepseek_api_key_here",
            },
        },
        "output": {
            "directory": "ai-code-review-docs",
            "format": "markdown",
        },
        "behavior": {
            "log_level": "info",
        },
        "preferences": {
            "skip_validation": False,
        },
    }


def _resolve_config_for_validation(config_path: str | None) -> ResolvedConfig:
    if not config_path:
        return resolve_config()

    path = Path(config_path).expanduser().resolve()
    data = _load_config_file(path)
    api = _mapping(data.get("api"))
    keys = _mapping(api.get("keys"))
    output = _mapping(data.get("output"))
    behavior = _mapping(data.get("behavior"))
    preferences = _mapping(data.get("preferences"))

    return ResolvedConfig(
        selected_model=str(api.get("model") or data.get("model") or "gemini:gemini-2.5-pro"),
        api_keys=ApiKeys(
            google=_placeholder_to_none(keys.get("google")),
            anthropic=_placeholder_to_none(keys.get("anthropic")),
            openrouter=_placeholder_to_none(keys.get("openrouter")),
            openai=_placeholder_to_none(keys.get("openai")),
            deepseek=_placeholder_to_none(keys.get("deepseek")),
        ),
        output_dir=_validation_output_dir(
            path.parent, output.get("directory") or output.get("dir")
        ),
        output_format=str(output.get("format") or "markdown"),
        debug=False,
        log_level=str(behavior.get("log_level") or "info"),
        skip_key_check=bool(preferences.get("skip_validation")),
        project_root=path.parent,
    )


def _load_config_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Configuration file not found: {path}")
    text = path.read_text(encoding="utf-8")
    if path.suffix == ".json":
        payload = json.loads(text) or {}
    else:
        payload = yaml.safe_load(text) or {}
    if not isinstance(payload, dict):
        raise ValueError(f"Configuration file must contain an object: {path}")
    return payload


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _placeholder_to_none(value: object) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    if value.startswith("your_") and value.endswith("_here"):
        return None
    return value


def _validation_output_dir(config_dir: Path, value: object) -> Path:
    raw = str(value or "ai-code-review-docs")
    path = Path(raw).expanduser()
    if path.is_absolute():
        return path
    return config_dir / path


def _print_models() -> None:
    print("Supported models:")
    for model in list_supported_models():
        provider, _ = parse_model(model.key)
        print(
            f"- {model.key} | {provider_display_name(provider)} | "
            f"{model.display_name} | {model.context_window:,} context"
        )
