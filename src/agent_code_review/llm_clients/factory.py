"""Factory for unified LLM provider adapters."""

from __future__ import annotations

from ..config import ResolvedConfig, parse_model, require_api_key
from .base import ProviderAdapter


def create_llm_client(config: ResolvedConfig) -> ProviderAdapter:
    """Create the provider adapter for the selected model."""
    
    provider, model_name = parse_model(config.selected_model)

    if provider in {"gemini", "google"}:
        from .gemini import create_gemini_adapter

        api_key = require_api_key(config)
        return create_gemini_adapter(
            model_name=model_name,
            full_model=config.selected_model,
            api_key=api_key
        )
    
    if provider == "anthropic":
        from .anthropic import create_anthropic_adapter

        api_key = require_api_key(config)
        return create_anthropic_adapter(
            model_name=model_name,
            full_model=config.selected_model,
            api_key=api_key
        )
    
    if provider == "openai":
        from .openai import create_openai_adapter

        api_key = require_api_key(config)
        return create_openai_adapter(
            model_name=model_name,
            full_model=config.selected_model,
            api_key=api_key
        )
    
    if provider == "openrouter":
        from .openrouter import create_openrouter_adapter

        api_key = require_api_key(config)
        return create_openrouter_adapter(
            model_name=model_name,
            full_model=config.selected_model,
            api_key=api_key,
        )
    
    if provider == "deepseek":
        from .deepseek import create_deepseek_adapter

        api_key = require_api_key(config)
        return create_deepseek_adapter(
            model_name=model_name,
            full_model=config.selected_model,
            api_key=api_key,
        )

    raise ValueError(f"Unsupported provider: {provider}")