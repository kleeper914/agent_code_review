from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from ..discovery import DiscoveredFile

ReviewType = Literal["quick-fixes", "security"]
OutputFormat = Literal["markdown", "json"]


class ReviewOptions(BaseModel):
    """Normalized review options from the CLI."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    target: str = "."
    review_type: ReviewType = "quick-fixes"
    output: OutputFormat = "markdown"
    model: str | None = None
    output_dir: str | None = None
    include_tests: bool = False
    include_project_docs: bool = True
    debug: bool = False
    verbose: bool = False
    quiet: bool = False
    log_level: str | None = None
    skip_key_check: bool = False
    api_keys: dict[str, str] = Field(default_factory=dict)


class ReviewResult(BaseModel):
    """Standard review result consumed by Markdown and JSON formatters."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    content: str
    file_path: str
    review_type: str
    timestamp: str
    model_used: str
    files: list[DiscoveredFile] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    output_path: Path | None = None
