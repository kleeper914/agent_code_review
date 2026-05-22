from __future__ import annotations

import json
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel, Field


class MemoryEntry(BaseModel):
    """A reusable project memory item."""

    category: str
    content: str
    metadata: dict[str, str] = Field(default_factory=dict)


class MemoryStore(Protocol):
    """Minimal memory store contract for context enhancers."""

    def recall(self, query: str, *, limit: int = 5) -> list[MemoryEntry]:
        """Return memories relevant to a query."""

    def learn(self, entry: MemoryEntry) -> None:
        """Persist a new memory entry."""


class NullMemoryStore:
    """Default no-op store used until memory is explicitly enabled."""

    def recall(self, query: str, *, limit: int = 5) -> list[MemoryEntry]:
        return []

    def learn(self, entry: MemoryEntry) -> None:
        return None


class FileMemoryStore:
    """JSONL-backed memory store used only when --use-memory is enabled."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def recall(self, query: str, *, limit: int = 5) -> list[MemoryEntry]:
        if not self.path.exists():
            return []
        terms = [term.lower() for term in query.split() if term.strip()]
        results: list[tuple[int, MemoryEntry]] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                entry = MemoryEntry.model_validate(json.loads(line))
            except Exception:
                continue
            haystack = f"{entry.category} {entry.content} {' '.join(entry.metadata.values())}".lower()
            score = sum(1 for term in terms if term in haystack)
            if score > 0 or not terms:
                results.append((score, entry))
        results.sort(key=lambda item: item[0], reverse=True)
        return [entry for _, entry in results[:limit]]

    def learn(self, entry: MemoryEntry) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(entry.model_dump_json() + "\n")
