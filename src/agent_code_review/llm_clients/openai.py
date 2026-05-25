"""OpenAI provider adapter."""

from __future__ import annotations

from .base import BaseLangChainAdapter
from .registry import ProviderFeatures


def create_openai_adapter(
    *,
    model_name: str,
    full_model: str,
    api_key: str,
    streaming: bool = True,
    provider_features: ProviderFeatures | None = None,
    model_warnings: list[str] | None = None,
) -> BaseLangChainAdapter:
    from langchain_openai import ChatOpenAI

    chat_model = ChatOpenAI(model=model_name, api_key=api_key, streaming=streaming)  # type: ignore[arg-type]
    return BaseLangChainAdapter(
        provider="openai",
        model_name=model_name,
        full_model=full_model,
        chat_model=chat_model,
        provider_features=provider_features,
        model_warnings=model_warnings,
    )
