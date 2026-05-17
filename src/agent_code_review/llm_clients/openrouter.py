"""OpenRouter provider adapter."""

from __future__ import annotations

from .base import BaseLangChainAdapter


OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


def create_openrouter_adapter(
    *,
    model_name: str,
    full_model: str,
    api_key: str,
) -> BaseLangChainAdapter:
    from langchain_openai import ChatOpenAI

    chat_model = ChatOpenAI(
        model=model_name,
        api_key=api_key,
        base_url=OPENROUTER_BASE_URL,
        streaming=True
    )
    return BaseLangChainAdapter(
        provider="openrouter",
        model_name=model_name,
        full_model=full_model,
        chat_model=chat_model,
    )
