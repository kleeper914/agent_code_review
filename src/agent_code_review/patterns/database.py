"""JSON-backed pattern database for extract-patterns results."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class PatternEntry(BaseModel):
    """Stored pattern extraction payload plus searchable metadata."""

    model_config = ConfigDict(populate_by_name=True)

    id: str
    project_name: str = Field(alias="projectName")
    project_type: str = Field(alias="projectType")
    language: str
    patterns: dict[str, Any]
    tags: list[str] = Field(default_factory=list)
    source_info: dict[str, Any] = Field(default_factory=dict, alias="sourceInfo")
    extracted_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        alias="extractedAt",
    )
    evaluation: dict[str, Any] | None = None


class PatternDatabase:
    """Small durable database compatible with the TypeScript pattern library concept."""

    def __init__(self, db_directory: str | Path = "pattern-database") -> None:
        self.db_path = Path(db_directory)
        self.index_path = self.db_path / "index.json"

    def initialize(self) -> None:
        self.db_path.mkdir(parents=True, exist_ok=True)
        if not self.index_path.exists():
            self._save_index([])

    def store(self, entry: PatternEntry) -> None:
        self.initialize()
        entry_path = self.db_path / f"{entry.id}.json"
        entry_path.write_text(entry.model_dump_json(by_alias=True, indent=2), encoding="utf-8")
        index = self._load_index()
        index_entry = {
            "id": entry.id,
            "projectName": entry.project_name,
            "projectType": entry.project_type,
            "language": entry.language,
            "extractedAt": entry.extracted_at,
            "tags": entry.tags,
            "qualityScore": _quality_score(entry),
            "patternCount": len(entry.patterns.get("architecturalPatterns", [])),
        }
        existing = next((idx for idx, item in enumerate(index) if item.get("id") == entry.id), None)
        if existing is None:
            index.append(index_entry)
        else:
            index[existing] = index_entry
        self._save_index(index)

    def retrieve(self, entry_id: str) -> PatternEntry | None:
        path = self.db_path / f"{entry_id}.json"
        if not path.exists():
            return None
        return PatternEntry.model_validate_json(path.read_text(encoding="utf-8"))

    def search(
        self,
        *,
        project_type: str | None = None,
        language: str | None = None,
        tags: list[str] | None = None,
        architectural_patterns: list[str] | None = None,
        min_quality_score: float | None = None,
        max_results: int | None = None,
    ) -> list[PatternEntry]:
        self.initialize()
        index = self._load_index()
        filtered = list(index)
        if project_type:
            filtered = [item for item in filtered if item.get("projectType") == project_type]
        if language:
            filtered = [
                item
                for item in filtered
                if str(item.get("language", "")).lower() == language.lower()
            ]
        if tags:
            filtered = [
                item for item in filtered if any(tag in item.get("tags", []) for tag in tags)
            ]
        if min_quality_score is not None:
            filtered = [
                item
                for item in filtered
                if float(item.get("qualityScore") or 0) >= min_quality_score
            ]
        filtered.sort(key=lambda item: float(item.get("qualityScore") or 0), reverse=True)
        if max_results is not None:
            filtered = filtered[:max_results]

        entries = [entry for item in filtered if (entry := self.retrieve(str(item["id"])))]
        if architectural_patterns:
            entries = [
                entry
                for entry in entries
                if _matches_architectural_patterns(entry, architectural_patterns)
            ]
        return entries

    def statistics(self) -> dict[str, Any]:
        self.initialize()
        entries = [
            entry for item in self._load_index() if (entry := self.retrieve(str(item["id"])))
        ]
        language_distribution = Counter(entry.language for entry in entries)
        project_type_distribution = Counter(entry.project_type for entry in entries)
        pattern_counts: Counter[str] = Counter()
        for entry in entries:
            for pattern in entry.patterns.get("architecturalPatterns", []):
                pattern_counts[str(pattern.get("patternName", "unknown"))] += 1
        return {
            "totalEntries": len(entries),
            "languageDistribution": dict(language_distribution),
            "projectTypeDistribution": dict(project_type_distribution),
            "averageQualityScore": (
                sum(_quality_score(entry) for entry in entries) / len(entries) if entries else 0
            ),
            "topPatterns": [
                {"pattern": pattern, "count": count}
                for pattern, count in pattern_counts.most_common(10)
            ],
        }

    def _load_index(self) -> list[dict[str, Any]]:
        if not self.index_path.exists():
            return []
        return list(__import__("json").loads(self.index_path.read_text(encoding="utf-8")))

    def _save_index(self, index: list[dict[str, Any]]) -> None:
        import json

        self.index_path.write_text(json.dumps(index, indent=2), encoding="utf-8")


def _quality_score(entry: PatternEntry) -> float:
    if not entry.evaluation:
        return 0
    return float(entry.evaluation.get("overallScore") or entry.evaluation.get("overall") or 0)


def _matches_architectural_patterns(entry: PatternEntry, patterns: list[str]) -> bool:
    names = [
        str(pattern.get("patternName", "")).lower()
        for pattern in entry.patterns.get("architecturalPatterns", [])
    ]
    return any(expected.lower() in name for expected in patterns for name in names)
