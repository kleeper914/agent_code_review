"""OpenTelemetry-friendly tracing facade with sanitized attributes."""

from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from typing import Any

from .runtime.events import redact_metadata


@dataclass
class _RecordedSpan:
    name: str
    attributes: dict[str, Any] = field(default_factory=dict)


class SpanHandle(AbstractContextManager["SpanHandle"]):
    def __init__(self, observability: "Observability", name: str, attributes: dict[str, Any]) -> None:
        self._observability = observability
        self._record = _RecordedSpan(name=name, attributes=redact_metadata(attributes))
        self._otel_context: Any = None
        self._otel_span: Any = None

    def __enter__(self) -> "SpanHandle":
        if self._observability.enabled:
            self._otel_context = self._observability._start_otel_span(self._record.name)
            if self._otel_context is not None:
                self._otel_span = self._otel_context.__enter__()
            for key, value in self._record.attributes.items():
                self._set_otel_attribute(key, value)
        return self

    def __exit__(self, exc_type, exc, traceback) -> bool:
        if exc is not None:
            self.set_attribute("error", str(exc))
        if self._observability.enabled:
            self._observability._record_span(self._record)
        if self._otel_context is not None:
            self._otel_context.__exit__(exc_type, exc, traceback)
        return False

    def set_attribute(self, key: str, value: Any) -> None:
        safe = redact_metadata({key: value})[key]
        self._record.attributes[key] = safe
        self._set_otel_attribute(key, safe)

    def _set_otel_attribute(self, key: str, value: Any) -> None:
        span = self._current_otel_span()
        if span is not None:
            span.set_attribute(key, _otel_value(value))

    def _current_otel_span(self) -> Any | None:
        return self._otel_span


class Observability:
    def __init__(
        self,
        *,
        enabled: bool = False,
        endpoint: str | None = None,
        service_name: str = "agent-code-review",
        console: bool = False,
    ) -> None:
        self.enabled = enabled
        self.endpoint = endpoint
        self.service_name = service_name
        self.console = console
        self._spans: list[_RecordedSpan] = []
        self._tracer: Any = None
        if enabled:
            self._configure_otel()

    def start_span(self, name: str, attributes: dict[str, Any] | None = None) -> SpanHandle:
        return SpanHandle(self, name, attributes or {})

    def exported_spans(self) -> list[dict[str, Any]]:
        return [
            {"name": span.name, "attributes": dict(span.attributes)}
            for span in self._spans
        ]

    def _record_span(self, span: _RecordedSpan) -> None:
        self._spans.append(span)

    def _configure_otel(self) -> None:
        try:
            from opentelemetry import trace
            from opentelemetry.sdk.resources import Resource
            from opentelemetry.sdk.trace import TracerProvider
            from opentelemetry.sdk.trace.export import BatchSpanProcessor

            resource = Resource.create({"service.name": self.service_name})
            provider = TracerProvider(resource=resource)
            if self.endpoint:
                try:
                    from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
                        OTLPSpanExporter,
                    )

                    provider.add_span_processor(
                        BatchSpanProcessor(OTLPSpanExporter(endpoint=self.endpoint))
                    )
                except Exception:
                    pass
            trace.set_tracer_provider(provider)
            self._tracer = trace.get_tracer(self.service_name)
        except Exception:
            self._tracer = None

    def _start_otel_span(self, name: str) -> Any | None:
        if self._tracer is None:
            return None
        return self._tracer.start_as_current_span(name)


_OBSERVABILITY = Observability(enabled=False)


def configure_observability(
    *,
    enabled: bool,
    endpoint: str | None = None,
    service_name: str = "agent-code-review",
    console: bool = False,
) -> Observability:
    global _OBSERVABILITY
    _OBSERVABILITY = Observability(
        enabled=enabled,
        endpoint=endpoint,
        service_name=service_name,
        console=console,
    )
    return _OBSERVABILITY


def get_observability() -> Observability:
    return _OBSERVABILITY


def _otel_value(value: Any) -> str | bool | int | float:
    if isinstance(value, (str, bool, int, float)):
        return value
    return str(value)
