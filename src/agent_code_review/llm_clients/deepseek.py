"""DeepSeek provider adapter."""

from __future__ import annotations

from .base import BaseLangChainAdapter


DEEPSEEK_BASE_URL = "https://api.deepseek.com"


def create_deepseek_adapter(
    *,
    model_name: str,
    full_model: str,
    api_key: str,
) -> BaseLangChainAdapter:
    from langchain_deepseek import ChatDeepSeek

    chat_model = ChatDeepSeek(
        model=model_name, 
        api_key=api_key, 
        api_base=DEEPSEEK_BASE_URL,
        streaming=True,
    )
    return BaseLangChainAdapter(
        provider="deepseek",
        model_name=model_name,
        full_model=full_model,
        chat_model=chat_model,
    )
