"""Terminal display consumer for runtime events."""

from __future__ import annotations

import sys
from typing import TextIO

from .events import RunEvent, RunLevel


PHASE_LABELS = {
    "config": "Config",
    "discovery": "Discovery",
    "prompt": "Prompt",
    "model": "Model",
    "report": "Report",
    "test_model": "Test",
    "models": "Models"
}


class RuntimeDisplay:
    """Render runtime events for users."""

    def __init__(
        self,
        *,
        stream: TextIO | None = None,
        verbose: bool = False,
        quiet: bool = False,
        debug: bool = False,
        log_level: str = "info"
    ) -> None:
        self.stream = stream or sys.stderr
        self.verbose = verbose
        self.quiet = quiet
        self.debug = debug
        self.log_level = log_level
        self._stream_active = False

    def handle(self, event: RunEvent) -> None:
        level = RunLevel(event.level)
        if not self._allows_level(level):
            return
        if self.quiet and level is not RunLevel.ERROR:
            return
        if level is RunLevel.DEBUG and not (self.verbose or self.debug):
            return
        
        line = self._format_event(event)
        if line:
            self.stream.write(f"{line}\n")
            self.stream.flush()
    
    def stream_chunk(self, text: str) -> None:
        if not text or self.quiet or self.log_level == "none":
            return
        self.stream.write(text)
        self.stream.flush()
        self._stream_active = True
    
    def finish_stream(self) -> None:
        if not self._stream_active:
            return
        self.stream.write("\n")
        self.stream.flush()
        self._stream_active = False

    def _format_event(self, event: RunEvent) -> str:
        level = RunLevel(event.level)
        prefix = "!" if level is RunLevel.ERROR else "-" if level is RunLevel.WARNING else ">"
        phase = PHASE_LABELS.get(str(event.phase), str(event.phase).title())
        message = f"{prefix} {phase}: {event.message}"

        if self.verbose or self.debug:
            safe_items = [
                f"{key}={value}" for key, value in event.metadata.items() if value is not None
            ]
            if event.duration_ms is not None:
                safe_items.append(f"durationMs={event.duration_ms:.1f}")
            if safe_items:
                message = f"{message} ({', '.join(safe_items)})"
        
        return message

    def _allows_level(self, level: RunLevel) -> bool:
        order = {
            "debug": 0,
            "info": 1,
            "warning": 2,
            "error": 3,
            "none": 4
        }
        current = order.get(self.log_level, 1)
        return order[level.value] >= current