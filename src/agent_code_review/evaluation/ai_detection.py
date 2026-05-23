"""Compatibility wrapper for coding-test AI detection summaries."""

from __future__ import annotations

from typing import Any

from ..discovery import ProjectContext
from ..orchestration.types import ReviewOptions

from .detection import build_ai_detection_result


def build_ai_detection_summary(
    context: ProjectContext,
    options: ReviewOptions,
) -> dict[str, Any]:
    """Return report-shaped deterministic AI-assistance signals."""

    analyzers = options.ai_detection_analyzers or ["git", "documentation"]
    if not options.enable_ai_detection:
        return {
            "enabled": False,
            "threshold": options.ai_detection_threshold,
            "analyzers": analyzers,
            "includeInReport": options.ai_detection_include_in_report,
            "failOnDetection": options.ai_detection_fail_on_detection,
        }

    detection = build_ai_detection_result(
        context,
        threshold=options.ai_detection_threshold,
        analyzers=analyzers,
        enabled=options.enable_ai_detection,
        fail_on_detection=options.ai_detection_fail_on_detection,
    )
    payload = detection.to_report_dict(
        fail_on_detection=options.ai_detection_fail_on_detection
    )
    payload["threshold"] = options.ai_detection_threshold
    payload["analyzers"] = analyzers
    payload["includeInReport"] = options.ai_detection_include_in_report
    return payload
