"""Minimal plugin example for Python AI Code Review.

Copy this file into a local plugins directory and pass
``--plugins-dir path/to/plugins --strategy example-security`` to route a review
through the custom strategy.
"""

from __future__ import annotations

from agent_code_review.plugins import PluginRegistration
from agent_code_review.strategies.security import SecurityReviewStrategy


def register(registry) -> None:
    """Register an example strategy that reuses the built-in security review."""

    registry.register(
        PluginRegistration(
            name="example-security",
            description="Example plugin that routes to the built-in security strategy",
            strategy=SecurityReviewStrategy(),
            version="0.1.0",
            author="AI Code Review Python refactor",
            source="example-plugin",
        )
    )
