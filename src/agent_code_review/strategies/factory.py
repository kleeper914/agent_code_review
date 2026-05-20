from __future__ import annotations

from ..orchestration.types import ReviewType

from .architectural import ArchitecturalReviewStrategy
from .base import ReviewStrategy
from .coding_test import CodingTestReviewStrategy
from .performance import PerformanceReviewStrategy
from .quick_fixes import QuickFixesReviewStrategy
from .security import SecurityReviewStrategy
from .unused_code import UnusedCodeReviewStrategy


def get_strategy(review_type: str) -> ReviewStrategy:
    strategies = _strategy_map()
    try:
        return strategies[review_type]
    except KeyError as exc:
        raise ValueError(f"Unsupported review type: {review_type}") from exc


def supported_review_types() -> tuple[ReviewType, ...]:
    return tuple(_strategy_map().keys())  # type: ignore[return-value]


def _strategy_map() -> dict[str, ReviewStrategy]:
    return {
        "quick-fixes": QuickFixesReviewStrategy(),
        "security": SecurityReviewStrategy(),
        "architectural": ArchitecturalReviewStrategy(),
        "performance": PerformanceReviewStrategy(),
        "coding-test": CodingTestReviewStrategy(),
        "unused-code": UnusedCodeReviewStrategy(),
    }
