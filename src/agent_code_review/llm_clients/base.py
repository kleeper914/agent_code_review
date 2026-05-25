"""Base classes and helpers for LangChain-backed provider adapters."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Iterator
from typing import Any, Protocol

from .costs import estimate_cost_from_usage
from .registry import ProviderFeatures
from .resilience import (
    GLOBAL_RATE_LIMITER,
    RetryPolicy,
    StreamFailureError,
    classify_error,
    run_with_retry,
)
from .types import GenerationOptions, LLMResponse, TokenUsage


class ProviderAdapter(Protocol):
    """Unified interface consumed by orchestration and strategy code."""

    provider: str
    model_name: str

    @property
    def model(self) -> str:
        ...

    def generate_review(
        self,
        prompt: str,
        options: GenerationOptions | None = None,
    ) -> LLMResponse:
        ...

    def stream_review(
        self,
        prompt: str,
        options: GenerationOptions | None = None,
    ) -> Iterator[str]:
        ...

    async def agenerate_review(
        self,
        prompt: str,
        options: GenerationOptions | None = None,
    ) -> LLMResponse:
        ...

    def astream_review(
        self,
        prompt: str,
        options: GenerationOptions | None = None,
    ) -> AsyncIterator[str]:
        ...


class BaseLangChainAdapter:
    """Adapter that normalizes LangChain chat model responses."""

    def __init__(
        self,
        *,
        provider: str,
        model_name: str,
        full_model: str,
        chat_model: Any,
        provider_features: ProviderFeatures | None = None,
        model_warnings: list[str] | None = None,
        retry_policy: RetryPolicy | None = None,
        rate_limiter: Any | None = None,
    ) -> None:
        self.provider = provider
        self.model_name = model_name
        self._full_model = full_model
        self._chat_model = chat_model
        self._provider_features = provider_features or ProviderFeatures()
        self._model_warnings = model_warnings or []
        self._retry_policy = retry_policy or RetryPolicy()
        self._rate_limiter = rate_limiter if rate_limiter is not None else GLOBAL_RATE_LIMITER

    @property
    def model(self) -> str:
        return self._full_model

    def generate_review(
        self,
        prompt: str,
        options: GenerationOptions | None = None,
    ) -> LLMResponse:
        if options and options.tools and callable(getattr(self._chat_model, "bind_tools", None)):
            response, attempts = run_with_retry(
                lambda: self._generate_with_tools(prompt, options),
                provider=self.provider,
                model=self.model,
                retry_policy=self._retry_policy,
                rate_limiter=self._rate_limiter,
            )
            response.metadata.update(self._response_metadata(response.usage, attempts=attempts))
            return response

        try:
            (raw_chunks, parts, usage), attempts = run_with_retry(
                lambda: self._collect_raw_chunks(
                    prompt,
                    emit_options=options,
                    allow_stream=self._provider_features.supports_streaming,
                ),
                provider=self.provider,
                model=self.model,
                retry_policy=self._retry_policy,
                rate_limiter=self._rate_limiter,
            )
            resilience_metadata = {"attempts": attempts}
        except BaseException as exc:
            classified = classify_error(exc, self.provider)
            if self._provider_features.supports_streaming and classified.retryable:
                response, attempts = run_with_retry(
                    lambda: self._to_response(self._chat_model.invoke(prompt)),
                    provider=self.provider,
                    model=self.model,
                    retry_policy=self._retry_policy,
                    rate_limiter=self._rate_limiter,
                )
                response.metadata.update(
                    self._response_metadata(
                        response.usage,
                        attempts=attempts,
                        stream_fallback=True,
                    )
                )
                return response
            raise

        return LLMResponse(
            content="".join(parts),
            usage=usage,
            raw=raw_chunks,
            model=self.model,
            metadata=self._response_metadata(usage, **resilience_metadata),
        )

    def stream_review(
        self,
        prompt: str,
        options: GenerationOptions | None = None,
    ) -> Iterator[str]:
        for _raw, text in self._stream_raw_chunks(
            prompt,
            allow_stream=self._provider_features.supports_streaming,
        ):
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
        async for raw, text in self._astream_raw_chunks(
            prompt,
            allow_stream=self._provider_features.supports_streaming,
        ):
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
            metadata=self._response_metadata(usage),
        )

    async def astream_review(
        self,
        prompt: str,
        options: GenerationOptions | None = None,
    ) -> AsyncIterator[str]:
        async for _raw, text in self._astream_raw_chunks(
            prompt,
            allow_stream=self._provider_features.supports_streaming,
        ):
            if not text:
                continue
            _emit_chunk(options, text)
            yield text

    def _to_response(self, raw: Any) -> LLMResponse:
        content = _normalize_content(getattr(raw, "content", raw))
        usage = _extract_usage(raw)
        return LLMResponse(
            content=content,
            usage=usage,
            raw=raw,
            model=self.model,
            metadata=self._response_metadata(usage),
        )

    def _generate_with_tools(self, prompt: str, options: GenerationOptions) -> LLMResponse:
        """Run one provider-native tool-calling turn through LangChain when available."""

        try:
            from langchain_core.messages import HumanMessage, ToolMessage
        except Exception:
            return self._to_response(self._chat_model.invoke(prompt))

        bound_model = self._chat_model.bind_tools(options.tools)
        initial = bound_model.invoke(prompt)
        tool_calls = getattr(initial, "tool_calls", None) or []
        if not tool_calls:
            return self._to_response(initial)

        messages: list[Any] = [HumanMessage(content=prompt), initial]
        for index, call in enumerate(tool_calls):
            try:
                result = options.tool_executor(call) if options.tool_executor else "No tool executor configured."
            except Exception as exc:
                result = f"Tool execution failed: {exc}"
            tool_call_id = _tool_call_id(call, index)
            messages.append(ToolMessage(content=str(result), tool_call_id=tool_call_id))

        final = self._chat_model.invoke(messages)
        return self._to_response(final)

    def _collect_raw_chunks(
        self,
        prompt: str,
        *,
        emit_options: GenerationOptions | None,
        allow_stream: bool,
    ) -> tuple[list[Any], list[str], TokenUsage]:
        parts: list[str] = []
        raw_chunks: list[Any] = []
        usage = TokenUsage()
        try:
            for raw, text in self._stream_raw_chunks(prompt, allow_stream=allow_stream):
                raw_chunks.append(raw)
                extracted_usage = _extract_usage(raw)
                if _has_usage(extracted_usage):
                    usage = extracted_usage
                if not text:
                    continue
                parts.append(text)
                _emit_chunk(emit_options, text)
        except BaseException as exc:
            if parts:
                raise StreamFailureError(
                    f"{self.provider} stream failed after partial output: {exc}"
                ) from exc
            raise
        return raw_chunks, parts, usage

    def _stream_raw_chunks(self, prompt: str, *, allow_stream: bool = True) -> Iterator[tuple[Any, str]]:
        stream = getattr(self._chat_model, "stream", None)
        if allow_stream and callable(stream):
            for raw in stream(prompt):
                yield raw, _normalize_content(getattr(raw, "content", raw))
            return

        message = self._chat_model.invoke(prompt)
        yield message, _normalize_content(getattr(message, "content", message))

    async def _astream_raw_chunks(
        self,
        prompt: str,
        *,
        allow_stream: bool = True,
    ) -> AsyncIterator[tuple[Any, str]]:
        astream = getattr(self._chat_model, "astream", None)
        if allow_stream and callable(astream):
            async for raw in astream(prompt):
                yield raw, _normalize_content(getattr(raw, "content", raw))
            return

        for raw, text in await asyncio.to_thread(
            lambda: list(self._stream_raw_chunks(prompt, allow_stream=allow_stream))
        ):
            yield raw, text

    def _response_metadata(
        self,
        usage: TokenUsage,
        *,
        attempts: int | None = None,
        stream_fallback: bool = False,
    ) -> dict[str, Any]:
        metadata: dict[str, Any] = {}
        cost = estimate_cost_from_usage(usage, self.model)
        if cost is not None:
            metadata["cost"] = cost.to_metadata()
        if self._model_warnings:
            metadata["modelWarnings"] = self._model_warnings
        if attempts is not None or stream_fallback:
            metadata["resilience"] = {
                "attempts": attempts or 1,
                "streamFallback": stream_fallback,
            }
        return metadata


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


def _tool_call_id(call: Any, index: int) -> str:
    if isinstance(call, dict):
        return str(call.get("id") or f"tool_call_{index}")
    return str(getattr(call, "id", "") or f"tool_call_{index}")
