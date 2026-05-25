"""Deterministic AI-assistance detection for coding-test submissions."""

from __future__ import annotations

import hashlib
import math
import re
import subprocess
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from ..discovery import ProjectContext
from ..observability import get_observability

EvidenceType = Literal["git", "documentation", "structural", "statistical", "linguistic"]
Confidence = Literal["high", "medium", "low"]


class PatternEvidence(BaseModel):
    type: EvidenceType
    data: dict[str, Any] = Field(default_factory=dict)
    context: str | None = None


class DetectedPattern(BaseModel):
    id: str
    name: str
    confidence: Confidence
    score: float
    evidence: PatternEvidence
    description: str


class DetectionMetadata(BaseModel):
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    engine_version: str = "2.0.0"
    enabled_analyzers: list[str] = Field(default_factory=list)
    total_analysis_time_ms: float = 0
    warnings: list[str] = Field(default_factory=list)
    cache_info: dict[str, Any] = Field(default_factory=lambda: {"hit": False})


class DetectionResult(BaseModel):
    enabled: bool = True
    is_ai_generated: bool = False
    confidence_score: float = 0
    detected_patterns: list[DetectedPattern] = Field(default_factory=list)
    analysis_breakdown: dict[str, Any] = Field(default_factory=dict)
    recommendations: list[str] = Field(default_factory=list)
    metadata: DetectionMetadata = Field(default_factory=DetectionMetadata)

    def to_report_dict(self, *, fail_on_detection: bool = False) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "isAIGenerated": self.is_ai_generated,
            "confidenceScore": self.confidence_score,
            "riskLevel": risk_level(self.confidence_score),
            "detectedPatterns": [
                pattern.model_dump(mode="json", by_alias=True)
                for pattern in self.detected_patterns
            ],
            "analysisBreakdown": self.analysis_breakdown,
            "recommendations": self.recommendations,
            "metadata": self.metadata.model_dump(mode="json"),
            "failOnDetection": fail_on_detection,
        }


class DetectionConfig(BaseModel):
    enabled: bool = True
    detection_threshold: float = 0.7
    enabled_analyzers: list[str] = Field(default_factory=lambda: ["git", "documentation"])
    max_analysis_time_ms: int = 8000
    enable_caching: bool = False
    include_evidence: bool = True
    generate_recommendations: bool = True
    pattern_weights: dict[str, float] = Field(
        default_factory=lambda: {"high": 1.0, "medium": 0.65, "low": 0.35}
    )


class GitCommit(BaseModel):
    hash: str
    message: str
    changed_files: list[str] = Field(default_factory=list)
    timestamp: datetime
    author_name: str | None = None
    author_email: str | None = None


class GitRepository(BaseModel):
    commits: list[GitCommit] = Field(default_factory=list)
    root_path: str | None = None


class CodeFile(BaseModel):
    path: str
    content: str
    language: str
    size: int


class ParsedCodebase(BaseModel):
    files: list[CodeFile] = Field(default_factory=list)
    statistics: dict[str, Any] = Field(default_factory=dict)


class DocumentationSet(BaseModel):
    readme: str | None = None
    code_files: list[CodeFile] = Field(default_factory=list)
    other_docs: dict[str, str] = Field(default_factory=dict)


class CodeSubmission(BaseModel):
    repository: GitRepository = Field(default_factory=GitRepository)
    codebase: ParsedCodebase = Field(default_factory=ParsedCodebase)
    documentation: DocumentationSet = Field(default_factory=DocumentationSet)


class SubmissionConverter:
    """Convert discovery output into analyzer input."""

    @classmethod
    def from_project_context(cls, context: ProjectContext) -> CodeSubmission:
        files = [
            CodeFile(
                path=file.relative_path,
                content=file.content,
                language=file.language,
                size=len(file.content.encode("utf-8")),
            )
            for file in context.files
        ]
        return CodeSubmission(
            repository=cls._git_repository(context.project_root),
            codebase=ParsedCodebase(
                files=files,
                statistics={
                    "totalFiles": len(files),
                    "totalLines": sum(len(file.content.splitlines()) for file in files),
                    "languages": sorted({file.language for file in files}),
                },
            ),
            documentation=DocumentationSet(
                readme=context.docs.get("README.md") or context.docs.get("readme.md"),
                code_files=files,
                other_docs=dict(context.docs),
            ),
        )

    @staticmethod
    def _git_repository(project_root: Path) -> GitRepository:
        probe = subprocess.run(
            ["git", "rev-parse", "--git-dir"],
            cwd=project_root,
            capture_output=True,
            text=True,
            timeout=8,
            check=False,
            shell=False,
        )
        if probe.returncode != 0:
            return GitRepository(commits=[], root_path=str(project_root))

        log = subprocess.run(
            ["git", "log", "--pretty=format:%H%x1f%s%x1f%ai%x1f%an%x1f%ae", "-n", "50", "--name-only"],
            cwd=project_root,
            capture_output=True,
            text=True,
            timeout=8,
            check=False,
            shell=False,
        )
        if log.returncode != 0:
            return GitRepository(commits=[], root_path=str(project_root))
        return GitRepository(commits=_parse_git_log(log.stdout), root_path=str(project_root))


class BaseAnalyzer:
    name: EvidenceType

    def __init__(self, config: DetectionConfig) -> None:
        self.config = config

    def analyze(self, submission: CodeSubmission) -> dict[str, Any]:
        raise NotImplementedError

    def pattern(
        self,
        pattern_id: str,
        name: str,
        confidence: Confidence,
        score: float,
        description: str,
        data: dict[str, Any],
    ) -> DetectedPattern:
        return DetectedPattern(
            id=pattern_id,
            name=name,
            confidence=confidence,
            score=max(0.0, min(1.0, round(score, 3))),
            evidence=PatternEvidence(type=self.name, data=data, context=f"Detected by {self.name}"),
            description=description,
        )


class GitAnalyzer(BaseAnalyzer):
    name = "git"

    def analyze(self, submission: CodeSubmission) -> dict[str, Any]:
        commits = submission.repository.commits
        patterns: list[DetectedPattern] = []
        if not commits:
            return {"analyzer": self.name, "patterns": patterns, "metadata": {"totalCommits": 0}}

        initial = commits[0]
        if len(initial.changed_files) > 8:
            patterns.append(
                self.pattern(
                    "H1.1",
                    "Simultaneous File Creation",
                    "high",
                    min(0.95, 0.55 + len(initial.changed_files) * 0.025),
                    "Initial commit contains an unusually large complete file set.",
                    {"fileCount": len(initial.changed_files), "commit": initial.hash[:8]},
                )
            )
        ai_messages = [
            commit
            for commit in commits
            if re.search(r"\b(implement|add|create).*(comprehensive|complete|support|functionality)", commit.message, re.I)
            or re.match(r"^(feat|fix|docs|test|chore)(\(.+\))?: .{20,}", commit.message)
        ]
        if len(commits) >= 3 and len(ai_messages) / len(commits) >= 0.66:
            patterns.append(
                self.pattern(
                    "H1.2",
                    "AI-Style Commit Messages",
                    "high",
                    0.82,
                    "Commit messages are unusually formal and template-like.",
                    {"matchingCommits": len(ai_messages), "totalCommits": len(commits)},
                )
            )
        human_markers = re.compile(r"\b(wip|debug|oops|typo|try|attempt|fixme|todo)\b", re.I)
        human_like = [commit for commit in commits if human_markers.search(commit.message)]
        if len(commits) >= 3 and not human_like:
            patterns.append(
                self.pattern(
                    "H1.3",
                    "Missing Developer Workflow",
                    "medium",
                    0.68,
                    "History lacks normal iteration, debugging, or work-in-progress commits.",
                    {"totalCommits": len(commits)},
                )
            )
        return {"analyzer": self.name, "patterns": patterns, "metadata": {"totalCommits": len(commits)}}


class DocumentationAnalyzer(BaseAnalyzer):
    name = "documentation"

    def analyze(self, submission: CodeSubmission) -> dict[str, Any]:
        patterns: list[DetectedPattern] = []
        readme = submission.documentation.readme or ""
        sections = re.findall(r"^#+\s+(.+)$", readme, flags=re.M)
        standard = {
            "installation",
            "usage",
            "api",
            "examples",
            "features",
            "configuration",
            "contributing",
        }
        matched = [section for section in sections if section.strip().lower() in standard]
        if len(sections) >= 5 and len(matched) / max(len(standard), 1) >= 0.55:
            patterns.append(
                self.pattern(
                    "H2.1",
                    "Template README Structure",
                    "high",
                    0.84,
                    "README follows a broad generated-template structure.",
                    {"matchedSections": matched, "sectionCount": len(sections)},
                )
            )
        densities = [_comment_density(file.content) for file in submission.documentation.code_files]
        avg_density = sum(densities) / len(densities) if densities else 0
        uniformity = _uniformity(densities)
        if len(densities) >= 3 and avg_density > 0.25 and uniformity > 0.75:
            patterns.append(
                self.pattern(
                    "H2.2",
                    "Uniform Comment Density",
                    "high",
                    min(0.9, 0.45 + avg_density + uniformity * 0.2),
                    "Comments are unusually dense and uniform across files.",
                    {"averageDensity": avg_density, "uniformity": uniformity},
                )
            )
        generic_count = len(
            re.findall(r"(this project provides|easy to use|comprehensive solution|powerful and flexible)", readme, re.I)
        )
        if generic_count >= 2:
            patterns.append(
                self.pattern(
                    "H2.3",
                    "AI-Style Documentation Phrases",
                    "medium",
                    0.7,
                    "Documentation uses repeated generic generated-documentation phrasing.",
                    {"genericPhraseCount": generic_count},
                )
            )
        return {
            "analyzer": self.name,
            "patterns": patterns,
            "metadata": {"filesAnalyzed": len(densities), "hasReadme": bool(readme), "avgCommentDensity": avg_density},
        }


class StructuralAnalyzer(BaseAnalyzer):
    name = "structural"

    def analyze(self, submission: CodeSubmission) -> dict[str, Any]:
        files = submission.codebase.files
        line_counts = [len(file.content.splitlines()) for file in files]
        function_names = re.findall(r"def\s+([a-zA-Z_][a-zA-Z0-9_]*)", "\n".join(file.content for file in files))
        patterns: list[DetectedPattern] = []
        if len(files) >= 4 and _uniformity(line_counts) > 0.85:
            patterns.append(
                self.pattern(
                    "S3.1",
                    "Uniform File Structure",
                    "medium",
                    0.72,
                    "Files have highly uniform shape, suggesting templated generation.",
                    {"fileCount": len(files), "lineCounts": line_counts[:10]},
                )
            )
        if function_names and len(set(function_names)) / len(function_names) <= 0.5:
            patterns.append(
                self.pattern(
                    "S3.2",
                    "Repeated Function Naming",
                    "medium",
                    0.68,
                    "Function names repeat with low variation across files.",
                    {"functionNames": function_names[:10]},
                )
            )
        return {"analyzer": self.name, "patterns": patterns, "metadata": {"filesAnalyzed": len(files)}}


class StatisticalAnalyzer(BaseAnalyzer):
    name = "statistical"

    def analyze(self, submission: CodeSubmission) -> dict[str, Any]:
        tokens = re.findall(r"[A-Za-z_][A-Za-z0-9_]*", "\n".join(file.content for file in submission.codebase.files))
        unique = len(set(tokens))
        diversity = unique / len(tokens) if tokens else 1
        entropy = _entropy(tokens)
        patterns: list[DetectedPattern] = []
        if tokens and diversity < 0.45:
            patterns.append(
                self.pattern(
                    "T4.1",
                    "Low Token Diversity",
                    "medium",
                    min(0.82, 0.75 - diversity),
                    "Token distribution is repetitive across the submission.",
                    {"totalTokens": len(tokens), "uniqueTokens": unique, "diversity": diversity, "entropy": entropy},
                )
            )
        return {"analyzer": self.name, "patterns": patterns, "metadata": {"totalTokens": len(tokens), "uniqueTokens": unique, "entropy": entropy}}


class LinguisticAnalyzer(BaseAnalyzer):
    name = "linguistic"

    def analyze(self, submission: CodeSubmission) -> dict[str, Any]:
        text = "\n".join([submission.documentation.readme or "", *[file.content for file in submission.codebase.files]])
        patterns: list[DetectedPattern] = []
        generic = re.findall(r"(process(?:es|ing)? the input data|comprehensive solution|easy to use|powerful and flexible)", text, re.I)
        snake_names = re.findall(r"\b[a-z]+(?:_[a-z]+){2,}\b", text)
        if len(generic) >= 3 or len(snake_names) >= 4:
            patterns.append(
                self.pattern(
                    "L5.1",
                    "Generic Linguistic Patterns",
                    "low",
                    0.62,
                    "Comments, docs, or identifiers contain repeated generic language patterns.",
                    {"genericPhrases": len(generic), "longSnakeCaseNames": len(snake_names)},
                )
            )
        return {"analyzer": self.name, "patterns": patterns, "metadata": {"textChars": len(text)}}


class DetectionEngine:
    def __init__(self, config: DetectionConfig | None = None) -> None:
        self.config = config or DetectionConfig()
        self._cache: dict[str, DetectionResult] = {}

    def analyze(self, submission: CodeSubmission) -> DetectionResult:
        if not self.config.enabled:
            return DetectionResult(enabled=False, metadata=DetectionMetadata(enabled_analyzers=[]))

        cache_key = self._cache_key(submission)
        if self.config.enable_caching and cache_key in self._cache:
            cached = self._cache[cache_key].model_copy(deep=True)
            cached.metadata.cache_info = {"hit": True, "key": cache_key}
            return cached

        started = time.perf_counter()
        warnings: list[str] = []
        breakdown: dict[str, Any] = {}
        patterns: list[DetectedPattern] = []
        for analyzer in self._enabled_analyzers():
            try:
                with get_observability().start_span(
                    "ai_detection.analyzer",
                    {"analyzer": analyzer.name},
                ):
                    result = analyzer.analyze(submission)
            except Exception as exc:  # pragma: no cover - defensive analyzer boundary
                warnings.append(f"{analyzer.name} analyzer failed: {exc}")
                continue
            breakdown[analyzer.name] = result
            patterns.extend(result.get("patterns") or [])

        score = self._confidence_score(patterns)
        is_generated = score >= self.config.detection_threshold
        result = DetectionResult(
            enabled=True,
            is_ai_generated=is_generated,
            confidence_score=score,
            detected_patterns=patterns,
            analysis_breakdown=breakdown,
            recommendations=_recommendations(patterns, is_generated)
            if self.config.generate_recommendations
            else [],
            metadata=DetectionMetadata(
                enabled_analyzers=list(self.config.enabled_analyzers),
                total_analysis_time_ms=round((time.perf_counter() - started) * 1000, 3),
                warnings=warnings,
                cache_info={"hit": False, "key": cache_key},
            ),
        )
        if self.config.enable_caching:
            self._cache[cache_key] = result.model_copy(deep=True)
        return result

    def _enabled_analyzers(self) -> list[BaseAnalyzer]:
        analyzers: dict[str, BaseAnalyzer] = {
            "git": GitAnalyzer(self.config),
            "documentation": DocumentationAnalyzer(self.config),
            "structural": StructuralAnalyzer(self.config),
            "statistical": StatisticalAnalyzer(self.config),
            "linguistic": LinguisticAnalyzer(self.config),
        }
        return [
            analyzers[name]
            for name in self.config.enabled_analyzers
            if name in analyzers
        ]

    def _confidence_score(self, patterns: list[DetectedPattern]) -> float:
        if not patterns:
            return 0.0
        weighted_sum = 0.0
        total_weight = 0.0
        for pattern in patterns:
            weight = self.config.pattern_weights.get(pattern.confidence, 0.5)
            weighted_sum += pattern.score * weight
            total_weight += weight
        base = weighted_sum / total_weight if total_weight else 0.0
        count_bonus = min(0.1, len(patterns) * 0.02)
        high_bonus = min(0.15, len([p for p in patterns if p.confidence == "high"]) * 0.05)
        return round(min(1.0, base + count_bonus + high_bonus), 3)

    def _cache_key(self, submission: CodeSubmission) -> str:
        payload = repr(
            {
                "commits": [
                    {
                        "hash": commit.hash,
                        "message": commit.message,
                        "files": commit.changed_files,
                    }
                    for commit in submission.repository.commits
                ],
                "files": [
                    {
                        "path": file.path,
                        "content": file.content,
                        "language": file.language,
                    }
                    for file in submission.codebase.files
                ],
                "readme": submission.documentation.readme,
                "config": self.config.model_dump(),
            }
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]


def build_ai_detection_result(
    context: ProjectContext,
    *,
    threshold: float,
    analyzers: list[str],
    enabled: bool,
    fail_on_detection: bool = False,
) -> DetectionResult:
    if not enabled:
        return DetectionResult(enabled=False, metadata=DetectionMetadata(enabled_analyzers=[]))
    result = DetectionEngine(
        DetectionConfig(
            detection_threshold=threshold,
            enabled_analyzers=analyzers,
            enable_caching=False,
        )
    ).analyze(SubmissionConverter.from_project_context(context))
    result.analysis_breakdown["failOnDetection"] = fail_on_detection
    return result


def risk_level(score: float) -> str:
    if score >= 0.9:
        return "critical"
    if score >= 0.8:
        return "high"
    if score >= 0.6:
        return "medium"
    if score >= 0.4:
        return "low"
    return "minimal"


def _parse_git_log(output: str) -> list[GitCommit]:
    commits: list[GitCommit] = []
    current: dict[str, Any] | None = None
    for raw_line in output.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if "\x1f" in line:
            if current:
                commits.append(GitCommit(**current))
            parts = line.split("\x1f")
            if len(parts) >= 5:
                current = {
                    "hash": parts[0],
                    "message": parts[1],
                    "timestamp": datetime.fromisoformat(parts[2]),
                    "author_name": parts[3],
                    "author_email": parts[4],
                    "changed_files": [],
                }
            continue
        if current is not None:
            current["changed_files"].append(line)
    if current:
        commits.append(GitCommit(**current))
    return list(reversed(commits))


def _comment_density(content: str) -> float:
    lines = [line.strip() for line in content.splitlines() if line.strip()]
    if not lines:
        return 0.0
    comments = [
        line
        for line in lines
        if line.startswith(("#", "//", "/*", "*")) or line.endswith("*/")
    ]
    return len(comments) / len(lines)


def _uniformity(values: list[float] | list[int]) -> float:
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    if mean == 0:
        return 1.0
    variance = sum((value - mean) ** 2 for value in values) / len(values)
    return max(0.0, 1 - min(1.0, math.sqrt(variance) / mean))


def _entropy(tokens: list[str]) -> float:
    if not tokens:
        return 0.0
    counts = Counter(tokens)
    total = len(tokens)
    return round(-sum((count / total) * math.log2(count / total) for count in counts.values()), 4)


def _recommendations(patterns: list[DetectedPattern], is_generated: bool) -> list[str]:
    if is_generated:
        return [
            "This submission has AI-assistance indicators; use the evidence for a human follow-up.",
            "Ask the candidate to explain specific implementation decisions live.",
            "Prefer verification questions over automatic rejection.",
        ]
    if patterns:
        return ["Minor AI-assistance indicators were found below threshold."]
    return ["No significant AI-assistance indicators were detected."]
