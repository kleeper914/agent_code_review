from __future__ import annotations

from dataclasses import dataclass
from typing import Any
import os

from ..config import ResolvedConfig, parse_model, require_api_key


@dataclass(frozen=True)
class ModelInfo:
    key: str
    provider: str
    display_name: str
    context_window: int


MODEL_REGISTRY = [
    ModelInfo("gemini:gemini-3.1-pro", "gemini", "Gemini 3.1 Pro", 1_048_576),
    ModelInfo("anthropic:claude-opus-4-7", "anthropic", "Claude Opus 4.7", 1_000_000),
    ModelInfo("openai:gpt-5.5", "openai", "GPT-5.5", 1_000_000),
    ModelInfo("openrouter:qwen/qwen-3.6-plus-preview", "openrouter", "OpenRouter (Qwen 3.6 Plus)", 1_000_000),
    ModelInfo("openai:gpt-5", "openai", "GPT-5", 400_000)
]

def list_supported_models() -> list[ModelInfo]:
    return MODEL_REGISTRY

def create_chat_model(config: ResolvedConfig) -> Any:
    """
    Create a LangChain chat model for the selected provider
    """

    provider, model_name = parse_model(config.selected_model)
    api_key = require_api_key(config)

    if provider in {"gemini", "google"}:
        from langchain_google_genai import ChatGoogleGenerativeAI

        return ChatGoogleGenerativeAI(
            model=model_name,
            google_api_key=api_key
        )
    
    if provider == "anthropic":
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(
            model=model_name,
            api_key=api_key,
        )

    if provider == "openai":
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=model_name,
            api_key=api_key,
            base_url=os.getenv("LLM_BASE_URL")
        )
    
    if provider == "openrouter":
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=model_name,
            api_key=api_key,
            base_url=os.getenv("LLM_BASE_URL"),
        )
    
    raise ValueError(f"Unsupported provider: {provider}")