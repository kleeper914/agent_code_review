"""Prompt feedback storage and optimization helpers."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel, Field

from ..config import ResolvedConfig
from ..llm_clients import create_llm_client
from ..observability import get_observability


class PromptFeedback(BaseModel):
    review_type: str
    prompt: str
    rating: int = Field(ge=1, le=5)
    comments: str | None = None
    positive_aspects: list[str] = Field(default_factory=list)
    negative_aspects: list[str] = Field(default_factory=list)
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class CachedPromptCandidate(PromptFeedback):
    usage_count: int = 0


class PromptFeedbackStore:
    """Append-only project-local prompt feedback store."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).expanduser()

    @classmethod
    def for_project(cls, project_root: Path) -> "PromptFeedbackStore":
        return cls(project_root / ".ai-code-review" / "prompt-feedback.jsonl")

    def add(self, feedback: PromptFeedback) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        safe_payload = _redact_feedback(feedback).model_dump(mode="json")
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(safe_payload, ensure_ascii=False) + "\n")

    def list(self, review_type: str | None = None) -> list[CachedPromptCandidate]:
        if not self.path.exists():
            return []
        entries: list[CachedPromptCandidate] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            entry = CachedPromptCandidate.model_validate_json(line)
            if review_type is None or entry.review_type == review_type:
                entries.append(entry)
        return entries

    def best(self, review_type: str) -> CachedPromptCandidate | None:
        candidates = self.list(review_type)
        if not candidates:
            return None
        return sorted(candidates, key=lambda item: (item.rating, item.timestamp), reverse=True)[0]


class PromptOptimizer:
    def __init__(self, store: PromptFeedbackStore) -> None:
        self.store = store

    def optimize(
        self,
        *,
        review_type: str,
        original_prompt: str,
        review_result: str,
        config: ResolvedConfig,
    ) -> str:
        feedback = self.store.list(review_type)
        feedback_text = "\n".join(_feedback_line(item) for item in feedback) or "No feedback yet."
        meta_template = """You are improving a code review prompt.

Review type: {review_type}

Original prompt:
{original_prompt}

Review result produced by that prompt:
{review_result}

User feedback:
{feedback_text}

Return only the revised prompt text.
"""
        try:
            from langchain_core.prompts import PromptTemplate

            meta_prompt = PromptTemplate.from_template(meta_template).format(
                review_type=review_type,
                original_prompt=original_prompt,
                review_result=review_result,
                feedback_text=feedback_text,
            )
        except Exception:
            meta_prompt = meta_template.format(
                review_type=review_type,
                original_prompt=original_prompt,
                review_result=review_result,
                feedback_text=feedback_text,
            )
        client = create_llm_client(config)
        with get_observability().start_span(
            "prompt_feedback.optimize",
            {"review_type": review_type, "model": config.selected_model},
        ):
            response = client.generate_review(meta_prompt)
        return response.content.strip()


def _feedback_line(feedback: CachedPromptCandidate | PromptFeedback) -> str:
    parts = [f"rating={feedback.rating}"]
    if feedback.comments:
        parts.append(f"comments={feedback.comments}")
    if feedback.positive_aspects:
        parts.append(f"positive={', '.join(feedback.positive_aspects)}")
    if feedback.negative_aspects:
        parts.append(f"negative={', '.join(feedback.negative_aspects)}")
    return "- " + "; ".join(parts)


def _redact_feedback(feedback: PromptFeedback) -> PromptFeedback:
    payload = feedback.model_dump()
    for key in ("prompt", "comments"):
        if payload.get(key):
            payload[key] = redact_text(str(payload[key]))
    payload["positive_aspects"] = [redact_text(item) for item in payload["positive_aspects"]]
    payload["negative_aspects"] = [redact_text(item) for item in payload["negative_aspects"]]
    return PromptFeedback.model_validate(payload)


def redact_text(text: str) -> str:
    # 中文注释：feedback 会长期留在项目目录，写入前先清理常见 key/token 片段。
    text = re.sub(
        r"(?i)((?:api[_-]?key|token|secret|password|credential)\s*[=:]\s*)\S+",
        r"\1[REDACTED]",
        text,
    )
    text = re.sub(r"\bsk-[A-Za-z0-9_-]+\b", "[REDACTED]", text)
    return text
