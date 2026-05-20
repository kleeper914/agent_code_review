from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel, Field


class MemoryEntry(BaseModel):
    """
    A reusable project memory item
    """

    category: str
    content: str
    metadata: dict[str, str] = Field(default_factory=dict)


class MemoryStore(Protocol):
    """
    Minimal memory store contract for context enhancers.
    """

    def recall(self, query: str, *, limit: int = 5) -> list[MemoryEntry]:
        """
        Return memories relevant to a query.
        """

    def learn(self, entry: MemoryEntry) -> None:
        """
        Persist a new memory entry.
        """


class NullMemoryStore:
    """Default no-op store used until memory is explicitly enabled."""

    def recall(self, query: str, *, limit: int = 5) -> list[MemoryEntry]:
        return []

    def learn(self, entry: MemoryEntry) -> None:
        return None
