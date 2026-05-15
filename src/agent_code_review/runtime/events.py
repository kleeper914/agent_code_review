"""Runtime event models and redaction helpers."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any
from pydantic import BaseModel, ConfigDict, Field


class RunPhase(str, Enum):
    CONFIG = "config"
    DISCOVERY = "discovery"
    PROMPT = "prompt"
    MODEL = "model"
    REPORT = "report"
    TEST_MODEL = "test_model"
    MODELS = "models"


class RunLevel(str, Enum):
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class RunEvent(BaseModel):
    """A single sanitized runtime event."""

    model_config = ConfigDict(use_enum_values=True)

    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    level: RunLevel = RunLevel.INFO
    phase: RunPhase
    message: str
    duration_ms: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    def to_jsonable(self) -> dict[str, Any]:
        payload = self.model_dump(mode="json")
        return payload
    

SENSITIVE_KEY_PARTS = ("key", "secret", "token", "password", "credential")
SENSITIVE_EXACT_KEYS = ("prompt", "raw_prompt", "rawPrompt", "content")


def redact_metadata(metadata: dict[str, Any] | None) -> dict[str, Any]:
    if not metadata:
        return {}
    return {key: _redact_value(key, value) for key, value in metadata.items()}


def _redact_value(key: str, value: Any) -> Any:
    """
    递归脱敏
    """
    normalized = key.lower()
    # 1. 精确匹配敏感词
    if normalized in {item.lower() for item in SENSITIVE_EXACT_KEYS}:
        return "[REDACTED]"
    # 2. 部分匹配敏感关键字
    if any(part in normalized for part in SENSITIVE_KEY_PARTS):
        return "[REDACTED]" if value else value
    # 3. 递归处理嵌套字典
    if isinstance(value, dict):
        return redact_metadata(value)
    # 4. 递归处理列表
    if isinstance(value, list):
        return [_redact_value(key, item) for item in value]
    # 5. 非敏感直接返回
    return value