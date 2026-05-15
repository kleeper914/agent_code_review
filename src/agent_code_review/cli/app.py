"""Command-line interface for the Python AI Code Review MVP."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
import os
import typer

from ..config import (
    ResolvedConfig,
    parse_model,
    provider_display_name,
    require_api_key,
    resolve_config,
)
from ..orchestration import run_review
from ..orchestration.models import list_supported_models
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
            "logLevel": config.log_level
        }
    )
    try:
        run_review(options, config, runtime)
    except Exception as exc:
        if not any(RunLevel(event.level) is RunLevel.ERROR for event in runtime.events):
            runtime.emit(
                RunPhase.MODEL,
                str(exc),
                level=RunLevel.ERROR
            )
        return 1
    return 0


def test_model_connection(config: ResolvedConfig) -> str:
    require_api_key(config)
    from ..orchestration import models

    chat_model = models.create_chat_model(config)
    response = chat_model.invoke(
        "Reply with a short sentence confirming this model is available for code review."
    )
    content = getattr(response, "content", response)
    return f"✓ {config.selected_model}: {content}"


def _review_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="agent-code-review")
    parser.add_argument("target", nargs="?", default=".")
    parser.add_argument("--type", "-t", dest="review_type", default="quick-fixes")
    parser.add_argument("--output", "-o", choices=["markdown", "json"], default="markdown")
    parser.add_argument("--output-dir", dest="output_dir")
    parser.add_argument("--model", "-m")
    parser.add_argument("--include-tests", action="store_true")
    parser.add_argument("--no-project-docs", action="store_true")
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


def _print_models() -> None:
    print("Supported models:")
    for model in list_supported_models():
        provider, _ = parse_model(model.key)
        print(
            f"- {model.key} | {provider_display_name(provider)} | "
            f"{model.display_name} | {model.context_window:,} context"
        )



# ==================================
# Test model
# ==================================

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
        log_level=namespace.log_level
    )
    runtime = create_runtime(config, options)
    runtime.emit(
        RunPhase.TEST_MODEL,
        "Testing model",
        metadata={"model": config.selected_model, "provider": config.provider},
    )

    try:
        message = test_model_connection(config)
    except ValueError as exc:
        runtime.emit(
            RunPhase.TEST_MODEL,
            str(exc),
            level=RunLevel.ERROR,
            metadata={"model": config.selected_model, "provider": config.provider},
        )
        return 1

    print(message)
    return 0


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