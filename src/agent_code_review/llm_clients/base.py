"""
Base classes and helpers for LangChain-backed provider adapters.

含义：
这是一个用于 LangChain 模型适配器的基础模块。
它定义了一套统一接口，以及一个基础适配器类，
用于把 LangChain ChatModel 的输出统一整理成项目内部标准格式。
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Iterator
from typing import Any, Protocol

from .types import GenerationOptions, LLMResponse, TokenUsage


class ProviderAdapter(Protocol):
    """
    Unified interface consumed by orchestration and strategy code.

    这是一个协议类，用来规定所有模型适配器必须具备哪些属性和方法。

    Protocol 的作用：
    - 不要求子类显式继承它
    - 只要某个类拥有相同的属性和方法，就被认为符合这个协议
    - 适合做“接口约束”
    """

    provider: str
    model_name: str

    @property
    def model(self) -> str:
        """
        model 是一个只读属性。

        作用：
        返回完整模型名称。
        例如：
        - provider = "openai"
        - model_name = "gpt-5.5"
        - model 可能返回 "openai:gpt-5.5"
        """
        ...

    def generate_review(
        self,
        prompt: str,
        options: GenerationOptions | None = None,
    ) -> LLMResponse:
        """
        同步非流式生成方法。

        参数：
        - prompt：输入给大模型的提示词
        - options：生成过程的额外配置，可以为空

        返回：
        - LLMResponse：项目内部统一封装后的响应对象
        """
        ...

    def stream_review(
        self,
        prompt: str,
        options: GenerationOptions | None = None,
    ) -> Iterator[str]:
        """
        同步流式生成方法。

        返回：
        - Iterator[str]：一个普通迭代器，每次 yield 一个文本片段
        """
        ...

    async def agenerate_review(
        self,
        prompt: str,
        options: GenerationOptions | None = None,
    ) -> LLMResponse:
        """
        异步非流式生成方法。

        async 表示这是异步函数，需要 await 调用。

        返回：
        - LLMResponse：统一响应对象
        """
        ...

    def astream_review(
        self,
        prompt: str,
        options: GenerationOptions | None = None,
    ) -> AsyncIterator[str]:
        """
        异步流式生成方法。

        返回：
        - AsyncIterator[str]：异步迭代器，需要使用 async for 消费
        """
        ...


class BaseLangChainAdapter:
    """
    Adapter that normalizes LangChain chat model responses.

    这是一个基础适配器类。

    它的主要作用：
    - 包装 LangChain 的 chat_model
    - 屏蔽不同模型返回格式的差异
    - 把结果统一转换成 LLMResponse
    - 同时支持同步、异步、流式、非流式四种调用方式
    """

    def __init__(
        self,
        *,
        provider: str,
        model_name: str,
        full_model: str,
        chat_model: Any,
    ) -> None:
        """
        构造函数，用于初始化适配器对象。

        参数解释：
        - provider：模型服务商，例如 openai、anthropic
        - model_name：模型名称，例如 gpt-5.5
        - full_model：完整模型标识，例如 openai:gpt-5.5
        - chat_model：实际的 LangChain ChatModel 对象

        注意：
        参数列表中的 * 表示后面的参数必须用关键字传入。
        例如：
        BaseLangChainAdapter(
            provider="openai",
            model_name="gpt-5.5",
            full_model="openai:gpt-5.5",
            chat_model=model
        )
        """
        self.provider = provider
        self.model_name = model_name
        self._full_model = full_model
        self._chat_model = chat_model

    @property
    def model(self) -> str:
        return self._full_model

    def generate_review(
        self,
        prompt: str,
        options: GenerationOptions | None = None,
    ) -> LLMResponse:
        parts: list[str] = []
        raw_chunks: list[Any] = []
        usage = TokenUsage()
        for raw, text in self._stream_raw_chunks(prompt):
            raw_chunks.append(raw)
            extracted_usage = _extract_usage(raw)
            if _has_usage(extracted_usage):
                usage = extracted_usage
            if not text:
                continue
            parts.append(text)
            _emit_chunk(options, text)
        return LLMResponse(
            content="".join(parts),
            usage=usage,
            raw=raw_chunks,
            model=self.model,
        )

    def stream_review(
        self,
        prompt: str,
        options: GenerationOptions | None = None,
    ) -> Iterator[str]:
        for _raw, text in self._stream_raw_chunks(prompt):
            if not text:
                continue
            _emit_chunk(options, text)
            yield text

    async def agenerate_review(
        self,
        prompt: str,
        options: GenerationOptions | None = None,
    ) -> LLMResponse:
        parts: list[str] = []
        raw_chunks: list[Any] = []
        usage = TokenUsage()
        async for raw, text in self._astream_raw_chunks(prompt):
            raw_chunks.append(raw)
            extracted_usage = _extract_usage(raw)
            if _has_usage(extracted_usage):
                usage = extracted_usage
            if not text:
                continue
            parts.append(text)
            _emit_chunk(options, text)
        return LLMResponse(
            content="".join(parts),
            usage=usage,
            raw=raw_chunks,
            model=self.model,
        )

    async def astream_review(
        self,
        prompt: str,
        options: GenerationOptions | None = None,
    ) -> AsyncIterator[str]:
        async for _raw, text in self._astream_raw_chunks(prompt):
            if not text:
                continue
            _emit_chunk(options, text)
            yield text

    def _to_response(self, raw: Any) -> LLMResponse:
        """
        把一个原始 LangChain 响应对象转换成 LLMResponse。

        raw 可能是：
        - LangChain 的 AIMessage
        - 普通字符串
        - 带 content 字段的对象
        """
        content = _normalize_content(getattr(raw, "content", raw))
        return LLMResponse(
            content=content,
            usage=_extract_usage(raw),
            raw=raw,
            model=self.model,
        )

    def _stream_raw_chunks(self, prompt: str) -> Iterator[tuple[Any, str]]:
        """
        同步获取原始 chunk。

        这个方法是整个同步调用链的核心。

        它会优先尝试使用 chat_model.stream(prompt)。
        如果底层模型不支持 stream，
        就退化为 chat_model.invoke(prompt)。
        """
        stream = getattr(self._chat_model, "stream", None)
        if callable(stream):
            for raw in stream(prompt):
                yield raw, _normalize_content(getattr(raw, "content", raw))
            return

        message = self._chat_model.invoke(prompt)
        yield message, _normalize_content(getattr(message, "content", message))

    async def _astream_raw_chunks(self, prompt: str) -> AsyncIterator[tuple[Any, str]]:
        """
        异步获取原始 chunk。

        优先使用 chat_model.astream(prompt)。
        如果底层模型不支持 astream，
        就把同步流式逻辑放到线程中执行。
        """
        astream = getattr(self._chat_model, "astream", None)
        if callable(astream):
            async for raw in astream(prompt):
                yield raw, _normalize_content(getattr(raw, "content", raw))
            return

        for raw, text in await asyncio.to_thread(lambda: list(self._stream_raw_chunks(prompt))):
            yield raw, text


def _normalize_content(content: Any) -> str:
    if isinstance(content, list):
        return "\n".join(_normalize_content_part(item) for item in content)
    return str(content)


def _normalize_content_part(item: Any) -> str:
    if isinstance(item, dict):
        if "text" in item:
            return str(item["text"])
        if "content" in item:
            return str(item["content"])
    return str(item)


def _extract_usage(raw: Any) -> TokenUsage:
    usage_metadata = getattr(raw, "usage_metadata", None)
    if isinstance(usage_metadata, dict) and usage_metadata:
        return TokenUsage(
            input_tokens=_to_int(usage_metadata.get("input_tokens")),
            output_tokens=_to_int(usage_metadata.get("output_tokens")),
            total_tokens=_to_int(usage_metadata.get("total_tokens")),
        )

    response_metadata = getattr(raw, "response_metadata", None)
    if not isinstance(response_metadata, dict):
        return TokenUsage()

    token_usage = response_metadata.get("token_usage") or response_metadata.get("usage")
    if not isinstance(token_usage, dict):
        return TokenUsage()

    input_tokens = token_usage.get("input_tokens", token_usage.get("prompt_tokens"))
    output_tokens = token_usage.get("output_tokens", token_usage.get("completion_tokens"))
    total_tokens = token_usage.get("total_tokens")
    return TokenUsage(
        input_tokens=_to_int(input_tokens),
        output_tokens=_to_int(output_tokens),
        total_tokens=_to_int(total_tokens),
    )


def _to_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _has_usage(usage: TokenUsage) -> bool:
    return any(
        value is not None
        for value in (usage.input_tokens, usage.output_tokens, usage.total_tokens)
    )


def _emit_chunk(options: GenerationOptions | None, text: str) -> None:
    if options and options.on_chunk:
        options.on_chunk(text)
