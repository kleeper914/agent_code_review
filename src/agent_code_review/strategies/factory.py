"""Factory for phase 3 provider-neutral review strategies."""

from __future__ import annotations

import warnings

from ..orchestration.types import PUBLIC_REVIEW_TYPES
from ..orchestration.types import ReviewOptions, ReviewType
from ..plugins import create_default_registry, load_plugins_from_directory

from .architectural import ArchitecturalReviewStrategy
from .base import ReviewStrategy
from .coding_test import CodingTestReviewStrategy
from .compatibility import CompatibilityReviewStrategy
from .extract_patterns import ExtractPatternsReviewStrategy
from .performance import PerformanceReviewStrategy
from .quick_fixes import QuickFixesReviewStrategy
from .security import SecurityReviewStrategy
from .unused_code import (
    CodeTracingUnusedCodeReviewStrategy,
    FocusedUnusedCodeReviewStrategy,
    UnusedCodeReviewStrategy,
)


def get_strategy(review_type: str, options: ReviewOptions | None = None) -> ReviewStrategy:
    if options and options.strategy:
        registry = create_default_registry()
        load_plugins_from_directory(options.plugins_dir, registry)
        plugin = registry.get(options.strategy)
        if plugin is not None:
            return plugin.strategy
        warnings.warn(
            (
                f'Custom strategy "{options.strategy}" not found. '
                "Falling back to the default strategy."
            ),
            RuntimeWarning,
            stacklevel=2,
        )

    if review_type == "unused-code" and options:
        if options.trace_code:
            return CodeTracingUnusedCodeReviewStrategy("unused-code")
        if options.focused:
            return FocusedUnusedCodeReviewStrategy("unused-code")

    strategies = _strategy_map()
    try:
        return strategies[review_type]
    except KeyError as exc:
        raise ValueError(f"Unsupported review type: {review_type}") from exc


def supported_review_types() -> tuple[ReviewType, ...]:
    return PUBLIC_REVIEW_TYPES  # type: ignore[return-value]


def _strategy_map() -> dict[str, ReviewStrategy]:
    return {
        "quick-fixes": QuickFixesReviewStrategy(),
        "security": SecurityReviewStrategy(),
        "architectural": ArchitecturalReviewStrategy(),
        "performance": PerformanceReviewStrategy(),
        "coding-test": CodingTestReviewStrategy(),
        "unused-code": UnusedCodeReviewStrategy(),
        "focused-unused-code": FocusedUnusedCodeReviewStrategy("focused-unused-code"),
        "code-tracing-unused-code": CodeTracingUnusedCodeReviewStrategy("code-tracing-unused-code"),
        "comprehensive": CompatibilityReviewStrategy("comprehensive"),
        "best-practices": CompatibilityReviewStrategy("best-practices"),
        "evaluation": CompatibilityReviewStrategy("evaluation"),
        "extract-patterns": ExtractPatternsReviewStrategy(),
        "ai-integration": CompatibilityReviewStrategy("ai-integration"),
        "cloud-native": CompatibilityReviewStrategy("cloud-native"),
        "developer-experience": CompatibilityReviewStrategy("developer-experience"),
        "consolidated": CompatibilityReviewStrategy("consolidated"),
    }
