"""Shared types for unified LLM provider adapters."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class TokenUsage(BaseModel):
    """Provider-neutral token usage summary."""

    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None


class GenerationOptions(BaseModel):
    """Optional generation controls shared by provider adapters."""

    temperature: float | None = None
    max_tokens: int | None = None
    on_chunk: Callable[[str], None] | None = None
    tools: list[Any] = Field(default_factory=list)
    tool_executor: Callable[[Any], str] | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class LLMResponse(BaseModel):
    """Provider-neutral response returned to orchestration and strategies."""
    
    model_config = ConfigDict(arbitrary_types_allowed=True)

    content: str
    usage: TokenUsage = Field(default_factory=TokenUsage)
    raw: Any = None
    model: str