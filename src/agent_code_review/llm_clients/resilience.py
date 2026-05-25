"""Retry, rate-limit, and stream-failure helpers for LLM adapters."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Literal, TypeVar

ErrorCategory = Literal[
    "auth",
    "quota",
    "model_access",
    "token_limit",
    "rate_limit",
    "server",
    "network",
    "unknown",
]

T = TypeVar("T")


class StreamFailureError(RuntimeError):
    """Raised when a streaming response fails after partial output was emitted."""


@dataclass(frozen=True)
class ClassifiedError:
    """Provider-neutral error classification."""

    category: ErrorCategory
    retryable: bool
    status_code: int | None = None
    retry_after_seconds: float | None = None
    message: str = ""


@dataclass(frozen=True)
class RetryPolicy:
    """Bounded exponential backoff policy."""

    max_attempts: int = 3
    initial_delay_seconds: float = 0.25
    max_delay_seconds: float = 4.0
    backoff_multiplier: float = 2.0

    def delay_for_attempt(self, attempt_number: int, classified: ClassifiedError) -> float:
        if classified.retry_after_seconds is not None:
            return classified.retry_after_seconds
        delay = self.initial_delay_seconds * (self.backoff_multiplier ** max(attempt_number - 1, 0))
        return min(delay, self.max_delay_seconds)


@dataclass
class _Bucket:
    tokens: float
    last_refill: float


@dataclass
class ProviderRateLimiter:
    """Tiny synchronous token-bucket limiter keyed by provider and model."""

    bucket_size: int = 10
    tokens_per_second: float = 2.0
    _buckets: dict[tuple[str, str], _Bucket] = field(default_factory=dict)

    def acquire(self, provider: str, model: str) -> None:
        key = (provider, model)
        bucket = self._buckets.get(key)
        now = time.monotonic()
        if bucket is None:
            self._buckets[key] = _Bucket(tokens=self.bucket_size - 1, last_refill=now)
            return

        elapsed = now - bucket.last_refill
        bucket.tokens = min(self.bucket_size, bucket.tokens + elapsed * self.tokens_per_second)
        bucket.last_refill = now
        if bucket.tokens >= 1:
            bucket.tokens -= 1
            return

        # Keep the limiter deterministic and simple; no queue is needed for the CLI use case.
        wait_seconds = (1 - bucket.tokens) / self.tokens_per_second
        time.sleep(wait_seconds)
        bucket.tokens = 0
        bucket.last_refill = time.monotonic()


GLOBAL_RATE_LIMITER = ProviderRateLimiter()


def classify_error(error: BaseException, provider: str) -> ClassifiedError:
    status_code = _status_code(error)
    message = str(error)
    lower = message.lower()
    retry_after = _retry_after(error)

    if status_code in {401, 403} or any(
        phrase in lower for phrase in ("api key", "unauthorized", "authentication", "permission")
    ):
        return ClassifiedError("auth", False, status_code, retry_after, message)
    if "quota" in lower or "billing" in lower or "insufficient_quota" in lower:
        return ClassifiedError("quota", False, status_code, retry_after, message)
    if status_code == 404 or any(
        phrase in lower
        for phrase in ("model not found", "does not exist", "not supported", "model access")
    ):
        return ClassifiedError("model_access", False, status_code, retry_after, message)
    if any(
        phrase in lower
        for phrase in ("context length", "maximum context", "token limit", "too many tokens")
    ):
        return ClassifiedError("token_limit", False, status_code, retry_after, message)
    if status_code == 429 or "rate limit" in lower:
        return ClassifiedError("rate_limit", True, status_code, retry_after, message)
    if status_code is not None and status_code >= 500:
        return ClassifiedError("server", True, status_code, retry_after, message)
    if isinstance(error, (ConnectionError, TimeoutError, OSError)):
        return ClassifiedError("network", True, status_code, retry_after, message)

    # Provider is kept in the signature so future provider-specific exceptions can be added
    # without changing BaseLangChainAdapter's call site.
    _ = provider
    return ClassifiedError("unknown", False, status_code, retry_after, message)


def run_with_retry(
    operation: Callable[[], T],
    *,
    provider: str,
    model: str,
    retry_policy: RetryPolicy,
    rate_limiter: Any | None,
    on_retry: Callable[[int, ClassifiedError], None] | None = None,
) -> tuple[T, int]:
    last_error: BaseException | None = None
    for attempt in range(1, retry_policy.max_attempts + 1):
        if rate_limiter is not None:
            rate_limiter.acquire(provider, model)
        try:
            return operation(), attempt
        except BaseException as exc:
            classified = classify_error(exc, provider)
            last_error = exc
            if (
                not classified.retryable
                or attempt >= retry_policy.max_attempts
                or isinstance(exc, StreamFailureError)
            ):
                raise
            if on_retry:
                on_retry(attempt, classified)
            delay = retry_policy.delay_for_attempt(attempt, classified)
            if delay > 0:
                time.sleep(delay)
    if last_error is not None:
        raise last_error
    raise RuntimeError("Retry loop exited without running operation")


def _status_code(error: BaseException) -> int | None:
    for attr in ("status_code", "status", "code"):
        value = getattr(error, attr, None)
        if isinstance(value, int):
            return value
    response = getattr(error, "response", None)
    value = getattr(response, "status_code", None)
    return value if isinstance(value, int) else None


def _retry_after(error: BaseException) -> float | None:
    value = getattr(error, "retry_after", None)
    if isinstance(value, (int, float)):
        return float(value)
    response = getattr(error, "response", None)
    headers = getattr(response, "headers", None)
    if isinstance(headers, dict):
        raw = headers.get("retry-after") or headers.get("Retry-After")
        try:
            return float(raw) if raw is not None else None
        except (TypeError, ValueError):
            return None
    return None
