"""Enhanced model registry for unified provider adapters."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal

Provider = Literal["gemini", "anthropic", "openai", "openrouter", "deepseek"]
ModelStatus = Literal["available", "preview", "deprecated", "retiring"]
ToolCallingSupport = Literal["full", "partial", "none"]


@dataclass(frozen=True)
class TieredPricing:
    """Pricing tier whose rates apply starting at token_threshold."""

    token_threshold: int
    input_price_per_million: float
    output_price_per_million: float


@dataclass(frozen=True)
class ProviderFeatures:
    """Provider/model feature flags used before invoking a client."""

    supports_streaming: bool = True
    supports_batch: bool = False
    supports_prompt_caching: bool = False
    rate_limit: int | None = None
    custom_headers: dict[str, str] = field(default_factory=dict)
    tool_calling_support: ToolCallingSupport = "none"


@dataclass(frozen=True)
class ModelInfo:
    """Enhanced model metadata.

    The first four fields intentionally match the Phase 2 constructor shape so
    existing tests and callers can keep instantiating ModelInfo(key, provider,
    display_name, context_window).
    """

    key: str
    provider: str
    display_name: str
    context_window: int
    api_identifier: str | None = None
    output_limit: int = 8_192
    input_price_per_million: float | None = None
    output_price_per_million: float | None = None
    tiered_pricing: tuple[TieredPricing, ...] = ()
    status: ModelStatus = "available"
    categories: tuple[str, ...] = ()
    capabilities: tuple[str, ...] = ()
    provider_features: ProviderFeatures = field(default_factory=ProviderFeatures)
    supports_tool_calling: bool = False
    api_key_env_var: str = "AI_CODE_REVIEW_GOOGLE_API_KEY"
    notes: str | None = None
    python_extension: bool = False


@dataclass(frozen=True)
class ModelResolution:
    """Result of resolving a requested model key."""

    info: ModelInfo
    is_fallback: bool = False
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ModelValidation:
    """Validation result for a model key."""

    is_valid: bool
    error: str | None = None
    warning: str | None = None
    suggestion: str | None = None


DEFAULT_CONTEXT_WINDOWS: dict[str, int] = {
    "gemini": 1_048_576,
    "google": 1_048_576,
    "anthropic": 200_000,
    "openai": 128_000,
    "openrouter": 128_000,
    "deepseek": 1_000_000,
}

DEFAULT_OUTPUT_LIMITS: dict[str, int] = {
    "gemini": 8_192,
    "google": 8_192,
    "anthropic": 8_192,
    "openai": 16_384,
    "openrouter": 8_192,
    "deepseek": 8_192,
}

API_KEY_ENV_VARS: dict[str, str] = {
    "gemini": "AI_CODE_REVIEW_GOOGLE_API_KEY",
    "google": "AI_CODE_REVIEW_GOOGLE_API_KEY",
    "anthropic": "AI_CODE_REVIEW_ANTHROPIC_API_KEY",
    "openai": "AI_CODE_REVIEW_OPENAI_API_KEY",
    "openrouter": "AI_CODE_REVIEW_OPENROUTER_API_KEY",
    "deepseek": "AI_CODE_REVIEW_DEEPSEEK_API_KEY",
}

OPENROUTER_CONTEXT_OVERRIDES: tuple[tuple[re.Pattern[str], int, int | None], ...] = (
    (re.compile(r"google\/gemini", re.I), 1_048_576, None),
    (re.compile(r"anthropic\/claude", re.I), 200_000, None),
    (re.compile(r"openai\/gpt-4o", re.I), 128_000, 16_384),
    (re.compile(r"openai\/gpt-4", re.I), 128_000, 16_384),
    (re.compile(r"openai\/o[134]", re.I), 200_000, 100_000),
    (re.compile(r"meta-llama\/llama-3", re.I), 131_072, None),
    (re.compile(r"deepseek\/", re.I), 65_536, None),
    (re.compile(r"mistralai\/", re.I), 131_072, None),
    (re.compile(r"qwen\/", re.I), 131_072, None),
)


def _features(
    *,
    streaming: bool = True,
    batch: bool = False,
    prompt_caching: bool = False,
    rate_limit: int | None = None,
    tool_calling: ToolCallingSupport = "none",
    custom_headers: dict[str, str] | None = None,
) -> ProviderFeatures:
    return ProviderFeatures(
        supports_streaming=streaming,
        supports_batch=batch,
        supports_prompt_caching=prompt_caching,
        rate_limit=rate_limit,
        custom_headers=custom_headers or {},
        tool_calling_support=tool_calling,
    )


def _tier(
    token_threshold: int,
    input_price_per_million: float,
    output_price_per_million: float,
) -> TieredPricing:
    return TieredPricing(token_threshold, input_price_per_million, output_price_per_million)


MODEL_REGISTRY = [
    ModelInfo(
        "gemini:gemini-2.5-pro",
        "gemini",
        "Gemini 2.5 Pro",
        1_048_576,
        api_identifier="gemini-2.5-pro-preview-05-06",
        output_limit=8_192,
        tiered_pricing=(_tier(0, 1.25, 5.0), _tier(200_000, 2.5, 10.0)),
        status="available",
        categories=("reasoning", "long-context", "multimodal"),
        capabilities=("advanced-reasoning", "multimodal", "code-generation", "long-context"),
        provider_features=_features(batch=True, tool_calling="partial"),
        api_key_env_var=API_KEY_ENV_VARS["gemini"],
    ),
    ModelInfo(
        "gemini:gemini-2.0-flash-lite",
        "gemini",
        "Gemini 2.0 Flash Lite",
        1_048_576,
        api_identifier="gemini-2.0-flash-lite",
        input_price_per_million=0.05,
        output_price_per_million=0.15,
        categories=("fast-inference", "cost-optimized"),
        capabilities=("fast-inference", "basic-reasoning"),
        provider_features=_features(batch=True),
        api_key_env_var=API_KEY_ENV_VARS["gemini"],
    ),
    ModelInfo(
        "gemini:gemini-2.0-flash",
        "gemini",
        "Gemini 2.0 Flash",
        1_048_576,
        api_identifier="gemini-2.0-flash-preview-05-07",
        input_price_per_million=0.3,
        output_price_per_million=1.2,
        status="preview",
        categories=("fast-inference", "long-context"),
        capabilities=("fast-inference", "good-reasoning", "long-context"),
        provider_features=_features(batch=True, tool_calling="partial"),
        api_key_env_var=API_KEY_ENV_VARS["gemini"],
    ),
    ModelInfo(
        "gemini:gemini-1.5-flash-8b",
        "gemini",
        "Gemini 1.5 Flash 8B",
        1_048_576,
        api_identifier="gemini-1.5-flash-8b",
        input_price_per_million=0.0375,
        output_price_per_million=0.15,
        categories=("fast-inference", "cost-optimized"),
        capabilities=("fast-inference", "basic-reasoning"),
        provider_features=_features(batch=True),
        api_key_env_var=API_KEY_ENV_VARS["gemini"],
        notes="Ultra-fast inference for simple code review tasks",
    ),
    ModelInfo(
        "anthropic:claude-4-opus",
        "anthropic",
        "Claude 4 Opus",
        200_000,
        api_identifier="claude-4-opus-20241022",
        input_price_per_million=15.0,
        output_price_per_million=75.0,
        supports_tool_calling=True,
        categories=("reasoning", "coding"),
        capabilities=("advanced-reasoning", "code-generation", "code-review", "analysis"),
        provider_features=_features(batch=True, prompt_caching=True, tool_calling="full"),
        api_key_env_var=API_KEY_ENV_VARS["anthropic"],
    ),
    ModelInfo(
        "anthropic:claude-4-sonnet",
        "anthropic",
        "Claude 4 Sonnet",
        200_000,
        api_identifier="claude-4-sonnet-20241022",
        input_price_per_million=3.0,
        output_price_per_million=15.0,
        supports_tool_calling=True,
        categories=("reasoning", "coding", "cost-optimized"),
        capabilities=("good-reasoning", "code-generation", "code-review"),
        provider_features=_features(batch=True, prompt_caching=True, tool_calling="full"),
        api_key_env_var=API_KEY_ENV_VARS["anthropic"],
        notes="Recommended model for code review tasks",
    ),
    ModelInfo(
        "anthropic:claude-3.5-sonnet",
        "anthropic",
        "Claude 3.5 Sonnet",
        200_000,
        api_identifier="claude-3-5-sonnet-20241022",
        input_price_per_million=3.0,
        output_price_per_million=15.0,
        status="retiring",
        supports_tool_calling=True,
        categories=("reasoning", "coding"),
        capabilities=("good-reasoning", "code-generation", "code-review"),
        provider_features=_features(batch=True, prompt_caching=True, tool_calling="full"),
        api_key_env_var=API_KEY_ENV_VARS["anthropic"],
    ),
    ModelInfo(
        "anthropic:claude-3-5-sonnet-latest",
        "anthropic",
        "Claude 3.5 Sonnet",
        200_000,
        api_identifier="claude-3-5-sonnet-latest",
        input_price_per_million=3.0,
        output_price_per_million=15.0,
        status="retiring",
        supports_tool_calling=True,
        categories=("reasoning", "coding"),
        capabilities=("good-reasoning", "code-generation", "code-review"),
        provider_features=_features(batch=True, prompt_caching=True, tool_calling="full"),
        api_key_env_var=API_KEY_ENV_VARS["anthropic"],
    ),
    ModelInfo(
        "anthropic:claude-3.5-haiku",
        "anthropic",
        "Claude 3.5 Haiku",
        200_000,
        api_identifier="claude-3-5-haiku-20241022",
        input_price_per_million=1.0,
        output_price_per_million=5.0,
        supports_tool_calling=True,
        categories=("fast-inference", "cost-optimized"),
        capabilities=("fast-inference", "basic-reasoning"),
        provider_features=_features(batch=True, prompt_caching=True, tool_calling="full"),
        api_key_env_var=API_KEY_ENV_VARS["anthropic"],
    ),
    ModelInfo(
        "openai:gpt-4o",
        "openai",
        "GPT-4o",
        128_000,
        api_identifier="gpt-4o",
        output_limit=16_384,
        input_price_per_million=2.5,
        output_price_per_million=10.0,
        supports_tool_calling=True,
        categories=("reasoning", "multimodal", "coding"),
        capabilities=("advanced-reasoning", "multimodal", "code-generation", "vision"),
        provider_features=_features(batch=True, rate_limit=10_000, tool_calling="full"),
        api_key_env_var=API_KEY_ENV_VARS["openai"],
    ),
    ModelInfo(
        "openai:gpt-4-turbo",
        "openai",
        "GPT-4 Turbo",
        128_000,
        api_identifier="gpt-4-turbo",
        output_limit=16_384,
        input_price_per_million=10.0,
        output_price_per_million=30.0,
        supports_tool_calling=True,
        categories=("reasoning", "coding"),
        capabilities=("good-reasoning", "code-generation"),
        provider_features=_features(batch=True, rate_limit=10_000, tool_calling="full"),
        api_key_env_var=API_KEY_ENV_VARS["openai"],
    ),
    ModelInfo(
        "openai:gpt-3.5-turbo",
        "openai",
        "GPT-3.5 Turbo",
        16_384,
        api_identifier="gpt-3.5-turbo",
        output_limit=4_096,
        input_price_per_million=0.5,
        output_price_per_million=1.5,
        status="deprecated",
        supports_tool_calling=True,
        categories=("fast-inference", "cost-optimized"),
        capabilities=("fast-inference", "basic-reasoning", "code-generation"),
        provider_features=_features(batch=True, rate_limit=10_000, tool_calling="full"),
        api_key_env_var=API_KEY_ENV_VARS["openai"],
    ),
    ModelInfo(
        "openai:gpt-4o-mini",
        "openai",
        "GPT-4o Mini",
        128_000,
        api_identifier="gpt-4o-mini",
        output_limit=16_384,
        input_price_per_million=0.15,
        output_price_per_million=0.6,
        supports_tool_calling=True,
        categories=("cost-optimized", "multimodal"),
        capabilities=("good-reasoning", "multimodal", "code-generation", "vision"),
        provider_features=_features(batch=True, rate_limit=30_000, tool_calling="full"),
        api_key_env_var=API_KEY_ENV_VARS["openai"],
        notes="Recommended for cost-sensitive code review tasks with good performance",
    ),
    ModelInfo(
        "openai:o1",
        "openai",
        "O1 Reasoning Model",
        128_000,
        api_identifier="o1-preview",
        output_limit=100_000,
        input_price_per_million=15.0,
        output_price_per_million=60.0,
        status="preview",
        categories=("reasoning",),
        capabilities=("advanced-reasoning", "problem-solving", "code-analysis"),
        provider_features=_features(streaming=False, rate_limit=500),
        api_key_env_var=API_KEY_ENV_VARS["openai"],
    ),
    ModelInfo(
        "openai:o1-mini",
        "openai",
        "O1 Mini",
        128_000,
        api_identifier="o1-mini",
        output_limit=65_536,
        input_price_per_million=3.0,
        output_price_per_million=12.0,
        categories=("reasoning", "cost-optimized"),
        capabilities=("good-reasoning", "problem-solving"),
        provider_features=_features(streaming=False, rate_limit=1_000),
        api_key_env_var=API_KEY_ENV_VARS["openai"],
    ),
    ModelInfo(
        "openrouter:anthropic/claude-4-opus",
        "openrouter",
        "Claude 4 Opus (via OpenRouter)",
        200_000,
        api_identifier="anthropic/claude-4-opus",
        input_price_per_million=15.0,
        output_price_per_million=75.0,
        categories=("reasoning", "coding"),
        capabilities=("advanced-reasoning", "code-generation", "code-review"),
        provider_features=_features(custom_headers={"X-Title": "AI Code Review"}),
        api_key_env_var=API_KEY_ENV_VARS["openrouter"],
    ),
    ModelInfo(
        "openrouter:anthropic/claude-4-sonnet",
        "openrouter",
        "Claude 4 Sonnet (via OpenRouter)",
        200_000,
        api_identifier="anthropic/claude-4-sonnet",
        input_price_per_million=3.0,
        output_price_per_million=15.0,
        categories=("reasoning", "coding", "cost-optimized"),
        capabilities=("good-reasoning", "code-generation", "code-review"),
        provider_features=_features(custom_headers={"X-Title": "AI Code Review"}),
        api_key_env_var=API_KEY_ENV_VARS["openrouter"],
    ),
    ModelInfo(
        "openrouter:openai/gpt-4o",
        "openrouter",
        "GPT-4o (via OpenRouter)",
        128_000,
        api_identifier="openai/gpt-4o",
        output_limit=16_384,
        input_price_per_million=2.5,
        output_price_per_million=10.0,
        categories=("reasoning", "multimodal"),
        capabilities=("advanced-reasoning", "multimodal", "code-generation"),
        provider_features=_features(custom_headers={"X-Title": "AI Code Review"}),
        api_key_env_var=API_KEY_ENV_VARS["openrouter"],
    ),
    ModelInfo(
        "openrouter:anthropic/claude-3.5-sonnet",
        "openrouter",
        "Claude 3.5 Sonnet (via OpenRouter)",
        200_000,
        api_identifier="anthropic/claude-3-5-sonnet-20241022",
        input_price_per_million=3.0,
        output_price_per_million=15.0,
        status="retiring",
        categories=("reasoning", "coding"),
        capabilities=("good-reasoning", "code-generation", "code-review"),
        provider_features=_features(custom_headers={"X-Title": "AI Code Review"}),
        api_key_env_var=API_KEY_ENV_VARS["openrouter"],
    ),
    ModelInfo(
        "openrouter:google/gemini-2.0-pro",
        "openrouter",
        "Gemini 2.0 Pro (via OpenRouter)",
        1_048_576,
        api_identifier="google/gemini-2.0-pro-latest",
        input_price_per_million=1.25,
        output_price_per_million=5.0,
        categories=("reasoning", "long-context"),
        capabilities=("advanced-reasoning", "long-context"),
        provider_features=_features(custom_headers={"X-Title": "AI Code Review"}),
        api_key_env_var=API_KEY_ENV_VARS["openrouter"],
    ),
    ModelInfo(
        "openrouter:meta-llama/llama-3.3-70b",
        "openrouter",
        "Llama 3.3 70B (via OpenRouter)",
        131_072,
        api_identifier="meta-llama/llama-3.3-70b",
        input_price_per_million=0.59,
        output_price_per_million=0.79,
        categories=("cost-optimized", "coding"),
        capabilities=("good-reasoning", "code-generation"),
        provider_features=_features(custom_headers={"X-Title": "AI Code Review"}),
        api_key_env_var=API_KEY_ENV_VARS["openrouter"],
    ),
    ModelInfo(
        "openrouter:openai/gpt-4-turbo",
        "openrouter",
        "GPT-4 Turbo (via OpenRouter)",
        128_000,
        api_identifier="openai/gpt-4-turbo",
        output_limit=16_384,
        input_price_per_million=10.0,
        output_price_per_million=30.0,
        categories=("reasoning", "coding"),
        capabilities=("advanced-reasoning", "code-generation"),
        provider_features=_features(custom_headers={"X-Title": "AI Code Review"}),
        api_key_env_var=API_KEY_ENV_VARS["openrouter"],
    ),
    ModelInfo(
        "openrouter:openai/gpt-4o-mini",
        "openrouter",
        "GPT-4o Mini (via OpenRouter)",
        128_000,
        api_identifier="openai/gpt-4o-mini",
        output_limit=16_384,
        input_price_per_million=0.15,
        output_price_per_million=0.6,
        categories=("cost-optimized", "coding"),
        capabilities=("good-reasoning", "code-generation"),
        provider_features=_features(custom_headers={"X-Title": "AI Code Review"}),
        api_key_env_var=API_KEY_ENV_VARS["openrouter"],
    ),
    ModelInfo(
        "openrouter:google/gemini-1.5-flash",
        "openrouter",
        "Gemini 1.5 Flash (via OpenRouter)",
        1_048_576,
        api_identifier="google/gemini-1.5-flash",
        input_price_per_million=0.075,
        output_price_per_million=0.3,
        categories=("fast-inference", "long-context"),
        capabilities=("fast-inference", "long-context"),
        provider_features=_features(custom_headers={"X-Title": "AI Code Review"}),
        api_key_env_var=API_KEY_ENV_VARS["openrouter"],
    ),
    ModelInfo(
        "openrouter:deepseek/deepseek-v3",
        "openrouter",
        "DeepSeek V3 (via OpenRouter)",
        65_536,
        api_identifier="deepseek/deepseek-v3",
        input_price_per_million=0.14,
        output_price_per_million=0.28,
        categories=("reasoning", "coding", "cost-optimized"),
        capabilities=("advanced-reasoning", "code-generation", "multilingual"),
        provider_features=_features(custom_headers={"X-Title": "AI Code Review"}),
        api_key_env_var=API_KEY_ENV_VARS["openrouter"],
    ),
    ModelInfo(
        "openrouter:qwen/qwen-2.5-coder-32b",
        "openrouter",
        "Qwen 2.5 Coder 32B (via OpenRouter)",
        32_768,
        api_identifier="qwen/qwen-2.5-coder-32b",
        input_price_per_million=0.18,
        output_price_per_million=0.18,
        categories=("coding", "cost-optimized"),
        capabilities=("code-generation", "code-review", "debugging"),
        provider_features=_features(custom_headers={"X-Title": "AI Code Review"}),
        api_key_env_var=API_KEY_ENV_VARS["openrouter"],
    ),
    ModelInfo(
        "deepseek:deepseek-v4-pro",
        "deepseek",
        "DeepSeek V4 Pro",
        1_000_000,
        api_identifier="deepseek-v4-pro",
        input_price_per_million=0.55,
        output_price_per_million=2.19,
        categories=("reasoning", "coding", "long-context"),
        capabilities=("advanced-reasoning", "code-generation", "code-review", "multilingual"),
        provider_features=_features(tool_calling="partial"),
        api_key_env_var=API_KEY_ENV_VARS["deepseek"],
        notes="Python-only extension retained from earlier refactor phases.",
        python_extension=True,
    ),
    ModelInfo(
        "deepseek:deepseek-v4-flash",
        "deepseek",
        "DeepSeek V4 Flash",
        1_000_000,
        api_identifier="deepseek-v4-flash",
        input_price_per_million=0.14,
        output_price_per_million=0.28,
        categories=("fast-inference", "coding", "cost-optimized"),
        capabilities=("fast-inference", "code-generation", "code-review", "multilingual"),
        provider_features=_features(tool_calling="partial"),
        api_key_env_var=API_KEY_ENV_VARS["deepseek"],
        notes="Python-only extension retained from earlier refactor phases.",
        python_extension=True,
    ),
]

_MODEL_MAP = {model.key: model for model in MODEL_REGISTRY}


def list_supported_models() -> list[ModelInfo]:
    return MODEL_REGISTRY


def resolve_model_info(model_key: str) -> ModelResolution:
    exact = _MODEL_MAP.get(model_key)
    if exact:
        warnings: list[str] = []
        if exact.status == "retiring":
            warnings.append(f"Model '{model_key}' is being retired.")
        elif exact.status == "deprecated":
            warnings.append(f"Model '{model_key}' is deprecated.")
        return ModelResolution(info=exact, warnings=warnings)

    provider, model_name = parse_model_key(model_key)
    context_window = DEFAULT_CONTEXT_WINDOWS.get(provider, 100_000)
    output_limit = DEFAULT_OUTPUT_LIMITS.get(provider, 8_192)
    warnings = [f"Model '{model_key}' not in registry. Using {provider} defaults."]

    if provider == "openrouter":
        inferred = _infer_openrouter_limits(model_name, context_window, output_limit)
        if inferred != (context_window, output_limit):
            context_window, output_limit = inferred
            warnings.append(
                "Inferred OpenRouter context window for "
                f"'{model_name}': {context_window:,} tokens."
            )

    info = ModelInfo(
        key=model_key,
        provider=provider,
        display_name=model_name,
        context_window=context_window,
        api_identifier=model_name,
        output_limit=output_limit,
        input_price_per_million=0,
        output_price_per_million=0,
        api_key_env_var=API_KEY_ENV_VARS.get(provider, "AI_CODE_REVIEW_GOOGLE_API_KEY"),
        provider_features=ProviderFeatures(supports_streaming=True, tool_calling_support="none"),
        notes=f"Unknown model: {model_key}",
    )
    return ModelResolution(info=info, is_fallback=True, warnings=warnings)


def get_model_info(model_key: str) -> ModelInfo:
    return resolve_model_info(model_key).info


def get_api_identifier(model_key: str) -> str:
    info = get_model_info(model_key)
    if info.api_identifier:
        return info.api_identifier
    return parse_model_key(model_key)[1]


def validate_model_key(model_key: str) -> ModelValidation:
    exact = _MODEL_MAP.get(model_key)
    if exact is None:
        provider, _model_name = parse_model_key(model_key)
        return ModelValidation(
            is_valid=True,
            warning=f"Model '{model_key}' not in registry. Using {provider} defaults.",
        )
    if exact.status == "deprecated":
        return ModelValidation(
            is_valid=False,
            error=f"Model '{model_key}' is deprecated",
            warning="Please migrate to an alternative model.",
        )
    if exact.status == "retiring":
        return ModelValidation(
            is_valid=True,
            warning=f"Model '{model_key}' is being retired.",
            suggestion="Consider migrating soon.",
        )
    return ModelValidation(is_valid=True)


def supports_tool_calling(model_key: str) -> bool:
    return get_model_info(model_key).supports_tool_calling


def get_provider_features(model_key: str) -> ProviderFeatures:
    return get_model_info(model_key).provider_features


def parse_model_key(model_key: str) -> tuple[str, str]:
    if not model_key or not model_key.strip():
        raise ValueError("Model string cannot be empty")
    if ":" not in model_key:
        return "gemini", model_key
    provider, model_name = model_key.split(":", 1)
    if not provider or not model_name:
        raise ValueError(f"Invalid model format: {model_key}. Expected provider:model-name")
    return provider.lower(), model_name


def _infer_openrouter_limits(model_name: str, context_window: int, output_limit: int) -> tuple[int, int]:
    for pattern, inferred_context, inferred_output in OPENROUTER_CONTEXT_OVERRIDES:
        if pattern.search(model_name):
            return inferred_context, inferred_output or output_limit
    return context_window, output_limit
