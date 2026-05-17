"""Model registry for unified provider adapters."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelInfo:
    key: str
    providr: str
    display_name: str
    context_window: int


MODEL_REGISTRY = [
    # --- Google ---
    ModelInfo("gemini:gemini-3.1-pro-preview", "google", "Gemini 3.1 Pro", 1_048_576),
    ModelInfo("gemini:gemini-3-flash-preview", "google", "Gemini 3 Flash", 1_048_576),

    # --- Anthropic ---
    ModelInfo("anthropic:claude-opus-4-7", "anthropic", "Claude Opus 4.7", 1_000_000),
    ModelInfo("anthropic:claude-sonnet-4-6", "anthropic", "Claude Sonnet 4.6", 1_000_000),
    ModelInfo("anthropic:claude-haiku-4-5-20251001", "anthropic", "Claude Haiku 4.5 20251001", 200_000),

    # --- OpenAI ---
    ModelInfo("openai:gpt-5.5", "openai", "GPT 5.5", 1_000_000),
    ModelInfo("openai:gpt-5.4", "openai", "GPT 5.4", 1_000_000),
    ModelInfo("openai:gpt-5.4-mini", "openai", "GPT 5.4 mini", 400_000),

    # --- DeepSeek ---
    ModelInfo("deepseek:deepseek-v4-pro", "deepseek", "DeepSeek V4 Pro", 1_000_000),
    ModelInfo("deepseek:deepseek-v4-flash", "deepseek", "DeepSeek V4 Flash", 1_000_000),

    # --- xAI ---
    ModelInfo("xai:grok-4.3", "xai", "Grok 4.3", 1_000_000),

    # --- Alibaba Cloud ---
    ModelInfo("alibaba:qwen3.6-plus", "alibaba", "Qwen3.6-Plus", 1_000_000),
    ModelInfo("alibaba:qwen3.6-max-preview", "alibaba", "Qwen3.6-Max-Preview", 262_144),
    ModelInfo("alibaba:qwen3.6-flash", "alibaba", "Qwen3.6-Flash", 1_000_000),

    # --- Mistral AI ---
    ModelInfo("mistral:mistral-large-2512", "mistral", "Mistral Large 3", 256_000),
    ModelInfo("mistral:mistral-medium-3-5", "mistral", "Mistral Medium 3.5", 256_000),
    ModelInfo("mistral:mistral-small-2603", "mistral", "Mistral Small 4", 256_000),


]


def list_supported_models() -> list[ModelInfo]:
    return MODEL_REGISTRY