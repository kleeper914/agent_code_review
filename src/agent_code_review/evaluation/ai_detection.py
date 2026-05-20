"""Lightweight provider-neutral AI detection context for coding test reviews."""

from __future__ import annotations

import subprocess
from typing import Any

from ..discovery import ProjectContext
from ..orchestration.types import ReviewOptions


def build_ai_detection_summary(
    context: ProjectContext,
    options: ReviewOptions
) -> dict[str, Any]:
    """
    Return deterministic context signals for AI-assistance review prompts.
    """

    analyzers = options.ai_detection_analyzers or ["git", "documentation"]
    result: dict[str, Any] = {
        "enabled": options.enable_ai_detection,
        "threshold": options.ai_detection_threshold,
        "analyzers": analyzers,
        "signals": {},
        "includeInReport": options.ai_detection_include_in_report,
        "failOnDetection": options.ai_detection_fail_on_detection,
    }
    if not options.enable_ai_detection:
        return result
    
    if "git" in analyzers:
        result["signals"]["git"] = _git_signal(context)

    if "documentation" in analyzers:
        result["signals"]["documentation"] = {
            "docCount": len(context.docs),
            "docNames": sorted(context.docs),
            "commentDensityHint": "Ask the reviewer to compare documentation volume to code size."
        }

    unsupported = [
        analyzer
        for analyzer in analyzers
        if analyzer not in {"git", "documentation", "structural", "statistical", "linguistic"}
    ]
    if unsupported:
        result["unsupportedAnalyzers"] = unsupported

    placeholders = [
        analyzer
        for analyzer in analyzers
        if analyzer in {"structural", "statistical", "linguistic"}
    ]
    if placeholders:
        result["placeholdersAnalyzers"] = placeholders

    return result


def _git_signal(context: ProjectContext) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            ["git", "log", "--online", "-n", "12"],
            cwd=context.project_root,
            capture_output=True,
            text=True,
            timeout=8,
            check=False,
        )
    except Exception as exc:    # pragma: no cover - defensive local environment guard
        return {"status": "error", "reason": str(exc)}

    if completed.returncode != 0:
        return {
            "status": "skipped",
            "reason": completed.stderr.strip() or "No git history available.",
        }
    commits = [line for line in completed.stdout.splitlines() if line.strip()]
    return {
        "status": "completed",
        "commitCountSample": len(commits),
        "recentCommits": commits
    }