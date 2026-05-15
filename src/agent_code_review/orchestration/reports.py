"""Review result formatting and persistence."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from .types import ReviewResult


def format_review_result(result: ReviewResult, output_format: str) -> str:
    if output_format == "json":
        return json.dumps(_result_to_payload(result), indent=2, ensure_ascii=False)
    return _format_markdown(result)


def save_review_result(result: ReviewResult, output_dir: Path, output_format: str) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    extension = "json" if output_format == "json" else "md"
    base_name = f"{result.review_type}-review-{timestamp}.{extension}"
    output_path = _unique_path(output_dir / base_name)
    output_path.write_text(format_review_result(result, output_format), encoding="utf-8")
    return output_path


def _result_to_payload(result: ReviewResult) -> dict[str, Any]:
    return {
        "content": result.content,
        "filePath": result.file_path,
        "reviewType": result.review_type,
        "timestamp": result.timestamp,
        "modelUsed": result.model_used,
        "files": [
            {
                "path": str(file.path),
                "relativePath": file.relative_path,
                "language": file.language,
            }
            for file in result.files
        ],
        "metadata": result.metadata,
    }


def _format_markdown(result: ReviewResult) -> str:
    files = "\n".join(f"- `{file.relative_path}`" for file in result.files) or "- No files"
    return f"""# {result.review_type.title()} Review

**Model:** `{result.model_used}`  
**Target:** `{result.file_path}`  
**Generated:** {result.timestamp}

## Review

{result.content}

## Files Analyzed

{files}
"""


def _unique_path(path: Path) -> Path:
    if not path.exists():
        return path

    counter = 1
    while True:
        candidate = path.with_name(f"{path.stem}-{counter}{path.suffix}")
        if not candidate.exists():
            return candidate
        counter += 1
