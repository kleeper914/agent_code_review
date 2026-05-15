"""Configuration loading."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field

load_dotenv()
DEFAULT_MODEL = os.getenv("DEFAULT_MODEL")
DEFAULT_OUTPUT_DIR = "ai-code-review-docs"


class ApiKeys(BaseModel):
    """Provider API keys resolved from env, project config, and CLI."""

    google: str | None = None
    anthropic: str | None = None
    openrouter: str | None = None
    openai: str | None = None
    deepseek: str | None = None

    def for_provider(self, provider: str) -> str | None:
        normalized = "google" if provider == "gemini" else provider
        return getattr(self, normalized, None)

    def redacted(self) -> dict[str, str | None]:
        """
        生成脱敏字典, 用于日志输出
        """
        return {
            provider: "[REDACTED]" if value else None
            for provider, value in self.model_dump().items()
        }


class ResolvedConfig(BaseModel):
    """Fully merged runtime configuration."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    selected_model: str = DEFAULT_MODEL
    api_keys: ApiKeys = Field(default_factory=ApiKeys)
    output_dir: Path
    output_format: str = "markdown"
    debug: bool = False
    log_level: str = "info"
    skip_key_check: bool = False
    project_root: Path

    @property
    def provider(self) -> str:
        return parse_model(self.selected_model)[0]

    @property
    def model_name(self) -> str:
        return parse_model(self.selected_model)[1]

    def api_key_for_selected_model(self) -> str | None:
        return self.api_keys.for_provider(self.provider)

    def redacted(self) -> dict[str, Any]:
        return {
            "selectedModel": self.selected_model,
            "apiKeys": self.api_keys.redacted(),
            "outputDir": str(self.output_dir),
            "outputFormat": self.output_format,
            "debug": self.debug,
            "log_level": self.log_level,
            "skipKeyCheck": self.skip_key_check,
        }


def parse_model(model: str) -> tuple[str, str]:
    """Parse provider:model strings, defaulting bare names to OpenAI."""

    if not model or not model.strip():
        raise ValueError("Model string cannot be empty")

    if ":" not in model:
        return "openai", model

    provider, model_name = model.split(":", 1)
    if not provider or not model_name:
        raise ValueError(f"Invalid model format: {model}. Expected provider:model-name")
    return provider.lower(), model_name


def provider_display_name(provider: str) -> str:
    names = {
        "gemini": "Google",
        "google": "Google",
        "anthropic": "Anthropic",
        "openai": "OpenAI",
        "openrouter": "OpenRouter",
        "deepseek": "DeepSeek",
    }
    return names.get(provider.lower(), provider)


def _load_env_files(project_root: Path) -> None:
    for file_name in (".env.local", ".env"):
        env_path = project_root / file_name
        if env_path.exists():
            load_dotenv(env_path, override=False)


def _load_project_config(project_root: Path) -> dict[str, Any]:
    candidates = [
        project_root / ".ai-code-review" / "config.yaml",
        project_root / ".ai-code-review" / "config.yml",
        project_root / ".ai-code-review.yaml",
        project_root / ".ai-code-review.yml",
        project_root / ".ai-code-review.json",
    ]

    for candidate in candidates:
        if not candidate.exists():
            continue
        text = candidate.read_text(encoding="utf-8")
        if candidate.suffix == ".json":
            return json.loads(text) or {}
        return yaml.safe_load(text) or {}

    return {}


def _env_api_keys() -> dict[str, str | None]:
    return {
        "google": (
            os.getenv("AI_CODE_REVIEW_GOOGLE_API_KEY")
            or os.getenv("GOOGLE_GENERATIVE_AI_KEY")
            or os.getenv("GOOGLE_AI_STUDIO_KEY")
        ),
        "anthropic": (
            os.getenv("AI_CODE_REVIEW_ANTHROPIC_API_KEY") or os.getenv("ANTHROPIC_API_KEY")
        ),
        "openrouter": (
            os.getenv("AI_CODE_REVIEW_OPENROUTER_API_KEY") or os.getenv("OPENROUTER_API_KEY")
        ),
        "openai": os.getenv("AI_CODE_REVIEW_OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY"),
        "deepseek": os.getenv("DEEPSEEK_API_KEY"),
    }


def _project_api_keys(project_config: dict[str, Any]) -> dict[str, str | None]:
    keys = (project_config.get("api") or {}).get("keys") or {}
    return {
        "google": keys.get("google") or None,
        "anthropic": keys.get("anthropic") or None,
        "openrouter": keys.get("openrouter") or None,
        "openai": keys.get("openai") or None,
        "deepseek": keys.get("deepseek") or None,
    }


def _project_model(project_config: dict[str, Any]) -> str | None:
    api = project_config.get("api") or {}
    model = project_config.get("model") or {}
    return api.get("model") or model.get("default")


def _project_output_dir(project_config: dict[str, Any]) -> str | None:
    output = project_config.get("output") or {}
    return output.get("directory") or output.get("dir")


def _resolve_output_dir(project_root: Path, value: str | None) -> Path:
    raw = value or DEFAULT_OUTPUT_DIR
    output_path = Path(raw).expanduser()
    if output_path.is_absolute():
        return output_path
    return project_root / output_path


def resolve_config(
    *,
    project_root: Path | None = None,
    cli_model: str | None = None,
    cli_output_dir: str | None = None,
    cli_output_format: str | None = None,
    cli_api_keys: dict[str, str] | None = None,
    cli_log_level: str | None = None,
    debug: bool | None = None,
    skip_key_check: bool | None = None,
) -> ResolvedConfig:
    """Resolve config with CLI > project config > environment > defaults precedence."""

    root = (project_root or Path.cwd()).resolve()
    _load_env_files(root)
    project_config = _load_project_config(root)

    env_keys = _env_api_keys()
    project_keys = _project_api_keys(project_config)
    cli_keys = cli_api_keys or {}

    merged_keys = {
        provider: cli_keys.get(provider) or project_keys.get(provider) or env_keys.get(provider)
        for provider in ("google", "anthropic", "openrouter", "openai", "deepseek")
    }

    project_skip = (project_config.get("preferences") or {}).get("skip_validation")

    selected_model = (
        cli_model
        or _project_model(project_config)
        or DEFAULT_MODEL
    )

    output_dir = _resolve_output_dir(
        root,
        cli_output_dir
        or _project_output_dir(project_config)
        or os.getenv("AI_CODE_REVIEW_OUTPUT_DIR")
        or DEFAULT_OUTPUT_DIR,
    )

    return ResolvedConfig(
        selected_model=selected_model,
        api_keys=ApiKeys(**merged_keys),
        output_dir=output_dir,
        output_format=cli_output_format
        or os.getenv("OUTPUT_FORMAT")
        or (project_config.get("output") or {}).get("format")
        or "markdown",
        debug=debug if debug is not None else os.getenv("AI_CODE_REVIEW_DEBUG") == "true",
        log_level=cli_log_level
        or os.getenv("LOG_LEVEL")
        or (project_config.get("behavior") or {}).get("log_level")
        or (project_config.get("system") or {}).get("log_level")
        or "info",
        skip_key_check=skip_key_check if skip_key_check is not None else bool(project_skip),
        project_root=root,
    )


def require_api_key(config: ResolvedConfig) -> str:
    """Return the selected provider key or raise a user-friendly error."""

    api_key = config.api_key_for_selected_model()
    if api_key:
        return api_key

    provider = parse_model(config.selected_model)[0]
    display_name = provider_display_name(provider)
    raise ValueError(f"Missing {display_name} API key for model {config.selected_model}")
