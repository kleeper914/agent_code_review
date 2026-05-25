"""Predefined review memory patterns.

These helpers mirror the TypeScript memory pattern catalog at a smaller Python
surface. They produce normal ``MemoryEntry`` objects so stores do not need a
second persistence format.
"""

from __future__ import annotations

from .base import MemoryEntry


class CodeReviewMemoryPatterns:
    """Factory methods for common platform memory entries."""

    @staticmethod
    def get_common_error_patterns() -> list[MemoryEntry]:
        return [
            MemoryEntry(
                category="security",
                review_type="security",
                content=(
                    "Command Injection: never build shell command strings from user input; "
                    "prefer argv lists and subprocess shell=False."
                ),
                finding_metadata={
                    "severity": "high",
                    "category": "injection",
                    "mitigation": "Use parameterized process execution and validate git URLs.",
                },
                tags=["security", "command-injection"],
            ),
            MemoryEntry(
                category="performance",
                review_type="performance",
                content=(
                    "Resource Leak: long-running listeners, streams, and temporary files need "
                    "explicit cleanup paths."
                ),
                finding_metadata={
                    "severity": "medium",
                    "category": "resource-management",
                    "mitigation": "Use context managers or explicit close/abort operations.",
                },
                tags=["performance", "resource-leak"],
            ),
        ]

    @staticmethod
    def get_team_patterns() -> list[MemoryEntry]:
        return [
            MemoryEntry(
                category="team",
                review_type="best-practices",
                content=(
                    "Python refactor work should keep provider-specific behavior behind "
                    "adapter boundaries and expose provider-neutral orchestration metadata."
                ),
                finding_metadata={"category": "architecture", "enforcement": "recommended"},
                tags=["architecture", "provider-neutral"],
            )
        ]
