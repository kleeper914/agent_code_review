"""OpenAI provider adapter."""

from __future__ import annotations

from .base import BaseLangChainAdapter


def create_openai_adapter(
    *,
    model_name: str,
    full_model: str,
    api_key: str,
    base_url: str | None = None,
) -> BaseLangChainAdapter:
    from langchain_openai import ChatOpenAI

    if base_url is not None:
        chat_model = ChatOpenAI(
            model=model_name,
            api_key=api_key,
            base_url=base_url,
            streaming=True
        )
    else:
        chat_model = ChatOpenAI(
            model=model_name,
            api_key=api_key,
            streaming=True
        )
    return BaseLangChainAdapter(
        provider="openai",
        model_name=model_name,
        full_model=full_model,
        chat_model=chat_model
    )