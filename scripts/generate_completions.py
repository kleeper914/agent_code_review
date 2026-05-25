#!/usr/bin/env python3
"""Generate static shell completions from the Python CLI source of truth."""

from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from agent_code_review.llm_clients import list_supported_models  # noqa: E402
from agent_code_review.orchestration.types import PUBLIC_REVIEW_TYPES  # noqa: E402


# Keep completions static for broad shell compatibility, but derive review types
# and model names from package code so generated files do not drift.
SUBCOMMANDS = (
    "generate-config",
    "validate-config",
    "init",
    "install",
    "test-build",
    "sync-github-projects",
    "mcp",
    "plugins",
    "list",
    "prompt-feedback",
    "test-model",
)
OPTIONS = (
    "--type",
    "-t",
    "--output",
    "-o",
    "--model",
    "-m",
    "--writer-model",
    "--language",
    "--framework",
    "--prompt-file",
    "--interactive",
    "--return-only",
    "--priority-filter",
    "--test-api",
    "--stdout",
    "--include-tests",
    "--no-project-docs",
    "--include-dependency-analysis",
    "--estimate",
    "--multi-pass",
    "--force-single-pass",
    "--enable-semantic-chunking",
    "--no-enable-semantic-chunking",
    "--use-memory",
    "--diagram",
    "--use-ts-prune",
    "--use-eslint",
    "--trace-code",
    "--focused",
    "--strategy",
    "--plugins-dir",
    "--coding-test-config",
    "--assignment-file",
    "--assignment-url",
    "--assignment-text",
    "--evaluation-template",
    "--template-url",
    "--rubric-file",
    "--debug",
    "--verbose",
    "--quiet",
    "--log-level",
    "--skip-key-check",
    "--models",
    "--listmodels",
    "--help",
)
OUTPUT_FORMATS = ("markdown", "json")
LANGUAGES = ("typescript", "javascript", "python", "php", "ruby", "dart", "go", "java", "rust")
FRAMEWORKS = (
    "react",
    "angular",
    "vue",
    "nextjs",
    "django",
    "laravel",
    "flask",
    "fastapi",
    "flutter",
    "rails",
    "pyramid",
)


def main() -> int:
    completions_dir = PROJECT_ROOT / "completions"
    completions_dir.mkdir(parents=True, exist_ok=True)
    models = tuple(model.key for model in list_supported_models())

    _write(completions_dir / "ai-code-review.bash", _bash_completion(models))
    _write(completions_dir / "ai-code-review.zsh", _zsh_completion(models))
    _write(completions_dir / "ai-code-review.fish", _fish_completion(models))
    return 0


def _write(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def _words(values: tuple[str, ...]) -> str:
    return " ".join(values)


def _bash_completion(models: tuple[str, ...]) -> str:
    return f"""#!/bin/bash
# Bash completion for ai-code-review.
# Generated from aicode_review.orchestration.types.PUBLIC_REVIEW_TYPES; run
# scripts/generate_completions.py after changing CLI review types or options.

_ai_code_review() {{
    local cur prev opts review_types output_formats models languages frameworks subcommands
    COMPREPLY=()
    cur="${{COMP_WORDS[COMP_CWORD]}}"
    prev="${{COMP_WORDS[COMP_CWORD-1]}}"

    review_types="{_words(PUBLIC_REVIEW_TYPES)}"
    output_formats="{_words(OUTPUT_FORMATS)}"
    models="{_words(models)}"
    languages="{_words(LANGUAGES)}"
    frameworks="{_words(FRAMEWORKS)}"
    subcommands="{_words(SUBCOMMANDS)}"
    opts="{_words(OPTIONS)}"

    case "${{prev}}" in
        --type|-t)
            COMPREPLY=( $(compgen -W "${{review_types}}" -- "${{cur}}") )
            return 0
            ;;
        --output|-o)
            COMPREPLY=( $(compgen -W "${{output_formats}}" -- "${{cur}}") )
            return 0
            ;;
        --model|-m|--writer-model)
            COMPREPLY=( $(compgen -W "${{models}}" -- "${{cur}}") )
            return 0
            ;;
        --language)
            COMPREPLY=( $(compgen -W "${{languages}}" -- "${{cur}}") )
            return 0
            ;;
        --framework)
            COMPREPLY=( $(compgen -W "${{frameworks}}" -- "${{cur}}") )
            return 0
            ;;
        --prompt-file|--plugins-dir|--coding-test-config|--assignment-file|--evaluation-template|--rubric-file)
            COMPREPLY=( $(compgen -f -- "${{cur}}") )
            return 0
            ;;
    esac

    if [[ ${{COMP_CWORD}} -eq 1 ]]; then
        COMPREPLY=( $(compgen -W "${{subcommands}}" -- "${{cur}}") )
        [[ ${{#COMPREPLY[@]}} -gt 0 ]] && return 0
    fi

    if [[ ${{cur}} == -* ]] ; then
        COMPREPLY=( $(compgen -W "${{opts}}" -- "${{cur}}") )
        return 0
    fi

    COMPREPLY=( $(compgen -f -- "${{cur}}") )
}}

complete -F _ai_code_review ai-code-review
complete -F _ai_code_review aicode-review
"""


def _zsh_completion(models: tuple[str, ...]) -> str:
    return f"""#compdef ai-code-review aicode-review
# Zsh completion for ai-code-review.
# Generated from aicode_review.orchestration.types.PUBLIC_REVIEW_TYPES; run
# scripts/generate_completions.py after changing CLI review types or options.

_ai_code_review() {{
    _arguments \\
        '1:command or target:(({_words(SUBCOMMANDS)}))' \\
        '--type[Type of review]:review type:(({_words(PUBLIC_REVIEW_TYPES)}))' \\
        '-t[Type of review]:review type:(({_words(PUBLIC_REVIEW_TYPES)}))' \\
        '--output[Output format]:format:(({_words(OUTPUT_FORMATS)}))' \\
        '-o[Output format]:format:(({_words(OUTPUT_FORMATS)}))' \\
        '--model[Model to use]:model:(({_words(models)}))' \\
        '-m[Model to use]:model:(({_words(models)}))' \\
        '--writer-model[Writer model for consolidation]:model:(({_words(models)}))' \\
        '--language[Programming language]:language:(({_words(LANGUAGES)}))' \\
        '--framework[Framework]:framework:(({_words(FRAMEWORKS)}))' \\
        '--prompt-file[Custom prompt file]:file:_files' \\
        '--plugins-dir[Plugin directory]:directory:_files -/' \\
        '--coding-test-config[Coding test config]:file:_files' \\
        '--assignment-file[Assignment file]:file:_files' \\
        '--evaluation-template[Evaluation template]:file:_files' \\
        '--rubric-file[Rubric file]:file:_files' \\
        '*:target:_files'
}}

_ai_code_review "$@"
"""


def _fish_completion(models: tuple[str, ...]) -> str:
    lines = [
        "# Fish completion for ai-code-review.",
        "# Generated from aicode_review.orchestration.types.PUBLIC_REVIEW_TYPES; run",
        "# scripts/generate_completions.py after changing CLI review types or options.",
        "",
    ]
    for command in ("ai-code-review", "aicode-review"):
        lines.append(
            f"complete -c {command} -n '__fish_use_subcommand' -xa \"{_words(SUBCOMMANDS)}\""
        )
        lines.append(
            f"complete -c {command} -l type -s t -d 'Type of review' -xa \"{_words(PUBLIC_REVIEW_TYPES)}\""
        )
        lines.append(
            f"complete -c {command} -l output -s o -d 'Output format' -xa \"{_words(OUTPUT_FORMATS)}\""
        )
        lines.append(
            f"complete -c {command} -l model -s m -d 'Model to use' -xa \"{_words(models)}\""
        )
        lines.append(
            f"complete -c {command} -l writer-model -d 'Writer model for consolidation' -xa \"{_words(models)}\""
        )
        lines.append(
            f"complete -c {command} -l language -d 'Programming language' -xa \"{_words(LANGUAGES)}\""
        )
        lines.append(
            f"complete -c {command} -l framework -d 'Framework' -xa \"{_words(FRAMEWORKS)}\""
        )
        for option in OPTIONS:
            if option.startswith("--") and option not in {
                "--type",
                "--output",
                "--model",
                "--writer-model",
                "--language",
                "--framework",
            }:
                lines.append(f"complete -c {command} -l {option[2:]} -d '{option[2:]}'")
        lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
