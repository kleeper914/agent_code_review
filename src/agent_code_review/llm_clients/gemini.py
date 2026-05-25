"""Gemini provider adapter."""

from __future__ import annotations

from .base import BaseLangChainAdapter
from .registry import ProviderFeatures


def create_gemini_adapter(
    *,
    model_name: str,
    full_model: str,
    api_key: str,
    streaming: bool = True,
    provider_features: ProviderFeatures | None = None,
    model_warnings: list[str] | None = None,
) -> BaseLangChainAdapter:
    from langchain_google_genai import ChatGoogleGenerativeAI

    chat_model = ChatGoogleGenerativeAI(
        model=model_name,
        google_api_key=api_key,
        streaming=streaming,
    )
    return BaseLangChainAdapter(
        provider="gemini",
        model_name=model_name,
        full_model=full_model,
        chat_model=chat_model,
        provider_features=provider_features,
        model_warnings=model_warnings,
    )
