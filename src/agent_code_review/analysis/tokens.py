"""Provider-aware token analysis and context-window mapping."""

from __future__ import annotations

import math
from typing import Literal

from pydantic import BaseModel, Field

from ..discovery import DiscoveredFile
from ..llm_clients.registry import resolve_model_info

from .chunking import ReviewChunk, pack_file_analyses


class FileTokenAnalysis(BaseModel):
    """Token count for one file."""

    path: str
    relative_path: str | None = None
    token_count: int
    size_in_bytes: int
    tokens_per_byte: float


class ChunkingRecommendation(BaseModel):
    """Recommendation for single-pass or multi-pass review."""

    chunking_recommended: bool
    recommended_chunks: list[ReviewChunk] = Field(default_factory=list)
    reason: str


class TokenAnalysisResult(BaseModel):
    """Complete token and chunking analysis for a review input."""

    files: list[FileTokenAnalysis]
    total_tokens: int
    total_size_in_bytes: int
    average_tokens_per_byte: float
    file_count: int
    prompt_overhead_tokens: int
    estimated_total_tokens: int
    context_window_size: int
    effective_context_window: int
    chunk_token_limit: int
    exceeds_context_window: bool
    estimated_passes_needed: int
    chunking_recommendation: ChunkingRecommendation


class TokenAnalysisOptions(BaseModel):
    """Options matching the TypeScript TokenAnalyzer surface."""

    review_type: str
    model_name: str
    optimize_for_speed: bool = False
    additional_prompt_overhead: int | None = None
    context_maintenance_factor: float = 0.08
    safety_margin_factor: float = 0.10
    force_single_pass: bool = False
    batch_token_limit: int | None = None


DEFAULT_PROMPT_OVERHEAD = 1500
DEFAULT_CONTEXT_WINDOW = 100_000


def analyze_files(
    files: list[DiscoveredFile],
    options: TokenAnalysisOptions,
) -> TokenAnalysisResult:
    context_window = context_window_for_model(options.model_name)
    prompt_overhead = options.additional_prompt_overhead or DEFAULT_PROMPT_OVERHEAD
    effective_context = math.floor(context_window * (1 - options.safety_margin_factor))

    file_analyses = [analyze_file(file, options.model_name) for file in files]
    total_tokens = sum(file.token_count for file in file_analyses)
    total_size = sum(file.size_in_bytes for file in file_analyses)
    estimated_total = total_tokens + prompt_overhead
    average = total_tokens / total_size if total_size else 0
    recommendation, chunk_limit = generate_chunking_recommendation(
        file_analyses,
        estimated_total_tokens=estimated_total,
        effective_context_window=effective_context,
        context_maintenance_factor=options.context_maintenance_factor,
        force_single_pass=options.force_single_pass,
        batch_token_limit=options.batch_token_limit,
    )

    return TokenAnalysisResult(
        files=file_analyses,
        total_tokens=total_tokens,
        total_size_in_bytes=total_size,
        average_tokens_per_byte=average,
        file_count=len(files),
        prompt_overhead_tokens=prompt_overhead,
        estimated_total_tokens=estimated_total,
        context_window_size=context_window,
        effective_context_window=effective_context,
        chunk_token_limit=chunk_limit,
        exceeds_context_window=estimated_total > effective_context,
        estimated_passes_needed=len(recommendation.recommended_chunks),
        chunking_recommendation=recommendation,
    )


def analyze_file(file: DiscoveredFile, model_name: str) -> FileTokenAnalysis:
    size = len(file.content.encode("utf-8"))
    token_count = count_tokens(file.content, model_name)
    return FileTokenAnalysis(
        path=file.relative_path,
        relative_path=file.relative_path,
        token_count=token_count,
        size_in_bytes=size,
        tokens_per_byte=token_count / size if size else 0,
    )


def generate_chunking_recommendation(
    file_analyses: list[FileTokenAnalysis],
    *,
    estimated_total_tokens: int,
    effective_context_window: int,
    context_maintenance_factor: float,
    force_single_pass: bool = False,
    batch_token_limit: int | None = None,
) -> tuple[ChunkingRecommendation, int]:
    chunk_limit = max(1, math.floor(effective_context_window * (1 - context_maintenance_factor)))
    if force_single_pass:
        return (
            ChunkingRecommendation(
                chunking_recommended=False,
                recommended_chunks=[
                    ReviewChunk(
                        files=[file.path for file in file_analyses],
                        estimated_token_count=estimated_total_tokens,
                        priority=1,
                    )
                ],
                reason="Single-pass mode forced by configuration",
            ),
            chunk_limit,
        )

    effective_limit = effective_context_window
    if batch_token_limit and batch_token_limit > 0:
        effective_limit = min(batch_token_limit, effective_context_window)
        chunk_limit = min(chunk_limit, effective_limit)

    if estimated_total_tokens <= effective_limit:
        return (
            ChunkingRecommendation(
                chunking_recommended=False,
                recommended_chunks=[
                    ReviewChunk(
                        files=[file.path for file in file_analyses],
                        estimated_token_count=estimated_total_tokens,
                        priority=1,
                    )
                ],
                reason=(
                    "Content fits within batch token limit"
                    if batch_token_limit
                    else "Content fits within model context window"
                ),
            ),
            chunk_limit,
        )

    # 多轮场景需要预留上下文维护空间；这个空间越大，每个 chunk 装的代码越少。
    chunk_limit = max(1, math.floor(effective_limit * (1 - context_maintenance_factor)))
    chunks = pack_file_analyses(file_analyses, max_chunk_size=chunk_limit)
    reason = (
        f"Batch token limit forcing smaller batches (limit: {batch_token_limit} tokens)"
        if batch_token_limit and batch_token_limit < effective_context_window
        else f"Content exceeds effective limit ({estimated_total_tokens} > {effective_limit} tokens)"
    )
    return (
        ChunkingRecommendation(
            chunking_recommended=True,
            recommended_chunks=chunks,
            reason=reason,
        ),
        chunk_limit,
    )


def count_tokens(text: str, model_name: str) -> int:
    family = model_family(model_name)
    if family == "openai":
        try:
            import tiktoken

            encoding = tiktoken.encoding_for_model("gpt-5.4")
            return len(encoding.encode(text))
        except Exception:
            return _approximate_token_count(text, ratio=4)
    if family == "anthropic":
        return _approximate_token_count(text, ratio=3.8)
    if family in {"gemini", "deepseek", "openrouter"}:
        return _approximate_token_count(text, ratio=4)
    return _approximate_token_count(text, ratio=4)


def context_window_for_model(model_name: str) -> int:
    resolution = resolve_model_info(model_name)
    return resolution.info.context_window or DEFAULT_CONTEXT_WINDOW


def model_family(model_name: str) -> Literal["openai", "anthropic", "gemini", "openrouter", "deepseek", "unknown"]:
    provider = model_name.split(":", 1)[0].lower() if ":" in model_name else "gemini"
    if provider in {"openai", "anthropic", "gemini", "openrouter", "deepseek"}:
        return provider  # type: ignore[return-value]
    lower = model_name.lower()
    if "gpt" in lower:
        return "openai"
    if "claude" in lower:
        return "anthropic"
    if "gemini" in lower:
        return "gemini"
    if "deepseek" in lower:
        return "deepseek"
    return "unknown"


def _approximate_token_count(text: str, *, ratio: float) -> int:
    return max(1, math.ceil(len(text) / ratio))
