"""Debug log file consumer for runtime events."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from .events import RunEvent


class RuntimeLogger:
    """Write text and JSONL debug logs."""

    def __init__(self, *, output_dir: Path, enabled: bool = False) -> None:
        self.enabled = enabled
        self.text_path: Path | None = None
        self.jsonl_path: Path | None = None

        if enabled:
            log_dir = output_dir / "logs"
            log_dir.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            self.text_path = self._unique_path(log_dir / f"run-{stamp}.log")
            self.jsonl_path = self._unique_path(log_dir / f"run-{stamp}.jsonl")

    def handle(self, event: RunEvent) -> None:
        if not self.enabled or not self.text_path or not self.jsonl_path:
            return
        
        payload = event.to_jsonable()
        text_line = (
            f"{payload["timestamp"]} {str(payload["level"]).upper()}"
            f"[{payload['phase']}] {payload['message']}"
        )
        if payload.get("duration_ms") is not None:
            text_line += f" durationMs={payload['duration_ms']:.1f}"
        if payload.get("metadata"):
            text_line += f" metadata={payload['metadata']}"
        
        with self.text_path.open("a", encoding="utf-8") as handle:
            handle.write(f"{text_line}\n")
        with self.jsonl_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
    
    @staticmethod
    def _unique_path(path: Path) -> Path:
        if not path.exists():
            return path
        counter = 1
        while True:
            candidate = path.with_name(f"{path.stem}-{counter}{path.suffix}")
            if not candidate.exists():
                return candidate
            counter += 1