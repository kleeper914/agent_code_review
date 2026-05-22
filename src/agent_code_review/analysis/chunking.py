"""
Token-aware bin packing for review chunks.

含义：
这是一个“根据 token 数进行代码审查分块”的模块。

Token-aware：
表示分块时考虑 token 数，而不是只考虑文件数量。

bin packing：
装箱问题，即把多个不同大小的文件放入若干 chunk 中，
每个 chunk 的 token 总量不超过 max_chunk_size。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from .tokens import FileTokenAnalysis


@dataclass
class ReviewUnit:
    """A semantic or file-level unit that can be reviewed in a pass."""

    id: str
    files: list[str]
    estimated_tokens: int
    kind: str = "file"
    content: str | None = None
    declarations: list[Any] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


class ReviewChunk(BaseModel):
    """A group of files or semantic units that fits one review pass."""

    files: list[str]
    estimated_token_count: int
    priority: int = 1
    oversized: bool = False
    review_units: list[ReviewUnit] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    model_config = {"arbitrary_types_allowed": True}

    @property
    def review_unit(self) -> ReviewUnit:
        """Return the primary semantic unit for callers that expect one unit per chunk."""

        return self.review_units[0] if self.review_units else ReviewUnit(
            id="file-group",
            files=self.files,
            estimated_tokens=self.estimated_token_count,
        )


def pack_file_analyses(
    file_analyses: list[FileTokenAnalysis],
    *,
    max_chunk_size: int,
) -> list[ReviewChunk]:
    """
    把多个文件的 token 分析结果打包成多个 ReviewChunk。
    目标是：
        1. 减少 LLM 审查次数
        2. 避免 chunk 太满
        3. 尽量让 chunk 大小均衡
        4. 对大文件、小文件分别处理

    Params:
        file_analyses: 每个文件的token分析结果列表
        max_chunk_size: 每个chunk允许的最大token数
    """

    if max_chunk_size <= 0:
        raise ValueError("max_chunk_size must be positive")

    sorted_files = sorted(file_analyses, key=lambda item: item.token_count, reverse=True)
    oversized, large, medium, small = _categorize(sorted_files, max_chunk_size)

    chunks: list[ReviewChunk] = []
    for file in oversized:
        chunks.append(
            ReviewChunk(
                files=[file.path],
                estimated_token_count=file.token_count,
                priority=len(chunks) + 1,
                oversized=True,
            )
        )

    total_tokens = sum(file.token_count for file in sorted_files)
    min_chunks_needed = max(1, _ceil_div(total_tokens, max_chunk_size))
    target_chunk_size = max(1, total_tokens // min_chunks_needed)

    _process_large_files(large, chunks, max_chunk_size, target_chunk_size)
    _process_medium_files(medium, chunks, max_chunk_size)
    _process_small_files(small, chunks, max_chunk_size)
    balanced = _balance_chunks(chunks, sorted_files, max_chunk_size)
    return _assign_priorities(balanced)


def pack_review_units(units: list[ReviewUnit], *, max_chunk_size: int) -> list[ReviewChunk]:
    """Pack semantic review units while preserving their metadata."""

    from .tokens import FileTokenAnalysis

    synthetic = [
        FileTokenAnalysis(
            path=unit.id,
            relative_path=unit.id,
            token_count=max(1, unit.estimated_tokens),
            size_in_bytes=max(1, (unit.estimated_tokens or 1) * 4),
            tokens_per_byte=0.25,
        )
        for unit in units
    ]
    unit_by_id = {unit.id: unit for unit in units}
    chunks = pack_file_analyses(synthetic, max_chunk_size=max_chunk_size)
    for chunk in chunks:
        chunk.review_units = [unit_by_id[file_id] for file_id in chunk.files if file_id in unit_by_id]
        real_files: list[str] = []
        for unit in chunk.review_units:
            for file in unit.files:
                if file not in real_files:
                    real_files.append(file)
        if real_files:
            chunk.files = real_files
    return chunks


def _categorize(
    sorted_files: list[FileTokenAnalysis],
    max_chunk_size: int,
) -> tuple[list[FileTokenAnalysis], list[FileTokenAnalysis], list[FileTokenAnalysis], list[FileTokenAnalysis]]:
    oversized: list[FileTokenAnalysis] = []
    large: list[FileTokenAnalysis] = []
    medium: list[FileTokenAnalysis] = []
    small: list[FileTokenAnalysis] = []

    for file in sorted_files:
        if file.token_count > max_chunk_size:
            oversized.append(file)
        elif file.token_count > max_chunk_size * 0.5:
            large.append(file)
        elif file.token_count > max_chunk_size * 0.2:
            medium.append(file)
        else:
            small.append(file)
    return oversized, large, medium, small


def _process_large_files(
    files: list[FileTokenAnalysis],
    chunks: list[ReviewChunk],
    max_chunk_size: int,
    target_chunk_size: int,
) -> None:
    for file in files:
        placed = False
        for chunk in chunks:
            remaining = max_chunk_size - chunk.estimated_token_count
            if (
                not chunk.oversized
                and remaining >= file.token_count
                and chunk.estimated_token_count + file.token_count >= target_chunk_size * 0.8
            ):
                chunk.files.append(file.path)
                chunk.estimated_token_count += file.token_count
                placed = True
                break
        if not placed:
            chunks.append(
                ReviewChunk(
                    files=[file.path],
                    estimated_token_count=file.token_count,
                    priority=len(chunks) + 1,
                )
            )


def _process_medium_files(
    files: list[FileTokenAnalysis],
    chunks: list[ReviewChunk],
    max_chunk_size: int,
) -> None:
    for file in files:
        placed = False
        for chunk in chunks:
            if chunk.oversized:
                continue
            if max_chunk_size - chunk.estimated_token_count >= file.token_count:
                chunk.files.append(file.path)
                chunk.estimated_token_count += file.token_count
                placed = True
                break
        if not placed:
            chunks.append(
                ReviewChunk(
                    files=[file.path],
                    estimated_token_count=file.token_count,
                    priority=len(chunks) + 1,
                )
            )


def _process_small_files(
    files: list[FileTokenAnalysis],
    chunks: list[ReviewChunk],
    max_chunk_size: int,
) -> None:
    for file in sorted(files, key=lambda item: item.token_count, reverse=True):
        best_index = -1
        best_fullness = -1.0
        for index, chunk in enumerate(chunks):
            if chunk.oversized:
                continue
            remaining = max_chunk_size - chunk.estimated_token_count
            fullness = chunk.estimated_token_count / max_chunk_size
            if remaining >= file.token_count and fullness > best_fullness:
                best_index = index
                best_fullness = fullness
        if best_index >= 0:
            chunk = chunks[best_index]
            chunk.files.append(file.path)
            chunk.estimated_token_count += file.token_count
        else:
            chunks.append(
                ReviewChunk(
                    files=[file.path],
                    estimated_token_count=file.token_count,
                    priority=len(chunks) + 1,
                )
            )


def _balance_chunks(
    chunks: list[ReviewChunk],
    file_analyses: list[FileTokenAnalysis],
    max_chunk_size: int,
) -> list[ReviewChunk]:
    file_map = {file.path: file for file in file_analyses}

    # 先合并最小 chunk：这一步能显著减少“只装了一两个小文件”的低效 pass。
    merge_candidates = sorted([chunk for chunk in chunks if not chunk.oversized], key=lambda item: item.estimated_token_count)
    oversized_chunks = [chunk for chunk in chunks if chunk.oversized]
    merged: list[ReviewChunk] = []
    used: set[int] = set()
    for i, chunk in enumerate(merge_candidates):
        if i in used:
            continue
        current = chunk.model_copy(deep=True)
        used.add(i)
        for j in range(i + 1, len(merge_candidates)):
            if j in used:
                continue
            other = merge_candidates[j]
            if current.estimated_token_count + other.estimated_token_count <= max_chunk_size:
                current.files.extend(other.files)
                current.estimated_token_count += other.estimated_token_count
                used.add(j)
        merged.append(current)

    balanced = oversized_chunks + merged

    # 再做有限次迁移平衡：从最满 chunk 移一个最合适的文件到最空 chunk。
    for _ in range(20):
        movable = [chunk for chunk in balanced if not chunk.oversized and chunk.files]
        if len(movable) < 2:
            break
        movable.sort(key=lambda item: item.estimated_token_count)
        small = movable[0]
        large = movable[-1]
        if large.estimated_token_count - small.estimated_token_count < max(500, max_chunk_size * 0.05):
            break

        best_file: str | None = None
        best_improvement = 0
        for file_path in large.files:
            file = file_map.get(file_path)
            if not file:
                continue
            new_small = small.estimated_token_count + file.token_count
            new_large = large.estimated_token_count - file.token_count
            if new_small <= max_chunk_size and new_large > 0:
                current_diff = large.estimated_token_count - small.estimated_token_count
                new_diff = abs(new_large - new_small)
                improvement = current_diff - new_diff
                if improvement > best_improvement:
                    best_file = file_path
                    best_improvement = improvement
        if best_file is None or best_improvement <= 100:
            break

        file = file_map[best_file]
        large.files.remove(best_file)
        large.estimated_token_count -= file.token_count
        small.files.append(best_file)
        small.estimated_token_count += file.token_count

    return [chunk for chunk in balanced if chunk.files]


def _assign_priorities(chunks: list[ReviewChunk]) -> list[ReviewChunk]:
    ordered = sorted(chunks, key=lambda item: item.estimated_token_count, reverse=True)
    for index, chunk in enumerate(ordered, start=1):
        chunk.priority = index
    return ordered


def _ceil_div(value: int, divisor: int) -> int:
    return -(-value // divisor)
