"""Factory for unified LLM provider adapters."""

from __future__ import annotations

from ..config import ResolvedConfig, parse_model, require_api_key

from .base import ProviderAdapter
from .registry import resolve_model_info


def create_llm_client(config: ResolvedConfig) -> ProviderAdapter:
    """Create the provider adapter for the selected model."""

    provider, model_name = parse_model(config.selected_model)
    model_resolution = resolve_model_info(config.selected_model)
    model_info = model_resolution.info
    api_model_name = model_info.api_identifier or model_name
    streaming = model_info.provider_features.supports_streaming

    if provider in {"gemini", "google"}:
        from .gemini import create_gemini_adapter

        api_key = require_api_key(config)
        return create_gemini_adapter(
            model_name=api_model_name,
            full_model=config.selected_model,
            api_key=api_key,
            streaming=streaming,
            provider_features=model_info.provider_features,
            model_warnings=model_resolution.warnings,
        )

    if provider == "anthropic":
        from .anthropic import create_anthropic_adapter

        api_key = require_api_key(config)
        return create_anthropic_adapter(
            model_name=api_model_name,
            full_model=config.selected_model,
            api_key=api_key,
            streaming=streaming,
            provider_features=model_info.provider_features,
            model_warnings=model_resolution.warnings,
        )

    if provider == "openai":
        from .openai import create_openai_adapter

        api_key = require_api_key(config)
        return create_openai_adapter(
            model_name=api_model_name,
            full_model=config.selected_model,
            api_key=api_key,
            streaming=streaming,
            provider_features=model_info.provider_features,
            model_warnings=model_resolution.warnings,
        )

    if provider == "openrouter":
        from .openrouter import create_openrouter_adapter

        api_key = require_api_key(config)
        return create_openrouter_adapter(
            model_name=api_model_name,
            full_model=config.selected_model,
            api_key=api_key,
            streaming=streaming,
            provider_features=model_info.provider_features,
            model_warnings=model_resolution.warnings,
        )

    if provider == "deepseek":
        from .deepseek import create_deepseek_adapter

        api_key = require_api_key(config)
        return create_deepseek_adapter(
            model_name=api_model_name,
            full_model=config.selected_model,
            api_key=api_key,
            streaming=streaming,
            provider_features=model_info.provider_features,
            model_warnings=model_resolution.warnings,
        )

    raise ValueError(f"Unsupported provider: {provider}")
