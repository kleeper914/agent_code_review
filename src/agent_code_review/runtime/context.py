"""Runtime event bus and context manager helpers."""

from __future__ import annotations

import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, TextIO

from .display import RuntimeDisplay
from .events import RunEvent, RunLevel, RunPhase, redact_metadata
from .logger import RuntimeLogger


class RunEventBus:
    """Record and publish runtime events to consumers."""

    def __init__(self) -> None:
        self.events: list[RunEvent] = []
        self._subscribers: list[Any] = []

    def subscribe(self, subscriber: Any) -> None:
        self._subscribers.append(subscriber)

    def emit(
        self,
        phase: RunPhase,
        message: str,
        *,
        level: RunLevel = RunLevel.INFO,
        metadata: dict[str, Any] | None = None,
        duration_ms: float | None = None
    ) -> RunEvent:
        event = RunEvent(
            phase=phase,
            level=level,
            message=message,
            metadata=redact_metadata(metadata),
            duration_ms=duration_ms
        )
        self.events.append(event)
        for subscriber in self._subscribers:
            subscriber.handle(event)
        return event
    

class RuntimeContext:
    """Application-facing runtime context."""

    def __init__(
        self,
        *,
        output_dir: Path,
        verbose: bool = False,
        quiet: bool = False,
        debug: bool = False,
        log_level: str = "info",
        stream: TextIO | None = None,
    ) -> None:
        self.output_dir = output_dir
        self.verbose = verbose
        self.quiet = quiet
        self.debug = debug
        self.log_level = log_level
        self.bus = RunEventBus()
        self.display = RuntimeDisplay(
            stream=stream,
            verbose=verbose,
            quiet=quiet,
            debug=debug,
            log_level=log_level
        )
        self.logger = RuntimeLogger(
            output_dir=output_dir,
            enabled=debug
        )
        self.bus.subscribe(self.display)
        self.bus.subscribe(self.logger)
    
    @property
    def events(self) -> list[RunEvent]:
        return self.bus.events
    
    def emit(
        self,
        phase: RunPhase,
        message: str,
        *,
        level: RunLevel = RunLevel.INFO,
        metadata: dict[str, Any] | None = None,
        duration_ms: float | None = None
    ) -> RunEvent:
        return self.bus.emit(
            phase,
            message,
            level=level,
            metadata=metadata,
            duration_ms=duration_ms
        )
    
    @contextmanager
    def wrap_phase(
        self,
        phase: RunPhase,
        message: str,
        *,
        metadata: dict[str, Any] | None = None
    ) -> Iterator[None]:
        started = time.perf_counter()
        self.emit(phase, message, metadata=metadata)
        try:
            yield
        except Exception as exc:
            duration_ms = (time.perf_counter() - started) * 1000
            self.emit(
                phase,
                f"{message} failed: {exc}",
                level=RunLevel.ERROR,
                metadata=metadata,
                duration_ms=duration_ms
            )
            raise
        duration_ms = (time.perf_counter() - started) * 1000
        self.emit(
            phase,
            f"{message} completed",
            metadata=metadata,
            duration_ms=duration_ms
        )

    

def create_runtime(
    config: Any | None = None,
    options: Any | None = None,
    *,
    output_dir: Path | None = None,
    verbose: bool | None = None,
    quiet: bool | None = None,
    debug: bool | None = None,
    log_level: bool | None = None,
    stream: TextIO | None = None
) -> RuntimeContext:
    """Create a runtime context from config/options or explicit values."""

    resolved_output_dir = output_dir or getattr(config, "output_dir", None) or Path.cwd()
    resolved_verbose = bool(verbose if verbose is not None else getattr(options, "verbose", False))
    resolved_quiet = bool(quiet if quiet is not None else getattr(options, "quiet", False))
    resolved_debug = bool(
        debug
        if debug is not None
        else getattr(options, "debug", False) or getattr(config, "debug", False)
    )
    resolved_log_level = (
        log_level
        or getattr(options, "log_level", None)
        or getattr(config, "log_level", None)
        or ("debug" if resolved_debug else "info")
    )
    return RuntimeContext(
        output_dir=Path(resolved_output_dir),
        verbose=resolved_verbose,
        quiet=resolved_quiet,
        debug=resolved_debug,
        log_level=resolved_log_level,
        stream=stream,
    )