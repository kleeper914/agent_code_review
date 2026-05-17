"""Anthropic provider adapter."""

from __future__ import annotations

from .base import BaseLangChainAdapter


def create_anthropic_adapter(
    *,
    model_name: str,
    full_model: str,
    api_key: str,
    base_url: str | None = None
) -> BaseLangChainAdapter:
    from langchain_anthropic import ChatAnthropic

    if base_url is not None:
        chat_model = ChatAnthropic(
            model_name=model_name,
            api_key=api_key,
            base_url=base_url,
            streaming=True,
        )
    else:
        chat_model = ChatAnthropic(
            model_name=model_name,
            api_key=api_key,
            streaming=True,
        )
    return BaseLangChainAdapter(
        provider="anthropic",
        model_name=model_name,
        full_model=full_model,
        chat_model=chat_model,
    )
