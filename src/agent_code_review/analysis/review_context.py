"""State carried across multi-pass reviews."""

from __future__ import annotations

from pydantic import BaseModel, Field

from ..discovery import DiscoveredFile

from .findings import FindingsExtractor


class CodeElement(BaseModel):
    """Important code element tracked across passes."""

    type: str
    name: str
    file: str
    signature: str | None = None
    importance: int = 1


class ReviewFinding(BaseModel):
    """Finding extracted from a previous pass."""

    type: str
    description: str
    file: str | None = None
    severity: int
    pass_number: int


class FileSummary(BaseModel):
    """Short summary for a file already reviewed."""

    path: str
    type: str
    description: str
    key_elements: list[str] = Field(default_factory=list)
    pass_number: int


class ReviewContext(BaseModel):
    """Context maintenance object for multi-pass reviews."""

    project_name: str
    review_type: str
    all_files: list[str]
    current_pass: int = 0
    code_elements: dict[str, CodeElement] = Field(default_factory=dict)
    findings: list[ReviewFinding] = Field(default_factory=list)
    file_summaries: dict[str, FileSummary] = Field(default_factory=dict)
    general_notes: list[str] = Field(default_factory=list)

    @classmethod
    def create(cls, project_name: str, review_type: str, files: list[DiscoveredFile]) -> "ReviewContext":
        return cls(
            project_name=project_name,
            review_type=review_type,
            all_files=[file.relative_path for file in files],
        )

    def start_pass(self) -> int:
        self.current_pass += 1
        return self.current_pass

    def add_code_element(self, element: CodeElement) -> None:
        key = f"{element.type}:{element.file}:{element.name}"
        self.code_elements[key] = element

    def add_finding(self, finding: ReviewFinding) -> None:
        self.findings.append(finding)

    def add_file_summary(self, summary: FileSummary) -> None:
        self.file_summaries[summary.path] = summary

    def add_general_note(self, note: str) -> None:
        self.general_notes.append(note)

    def update_from_review(self, content: str, files: list[DiscoveredFile]) -> None:
        for file in files:
            extension = file.path.suffix.lstrip(".") or "unknown"
            self.add_file_summary(
                FileSummary(
                    path=file.relative_path,
                    type=extension,
                    description=f"{extension.upper()} file with {len(file.content)} characters",
                    key_elements=[],
                    pass_number=self.current_pass,
                )
            )

        extractor = FindingsExtractor()
        for issue in extractor.extract_issue_texts(content):
            lower = issue.lower()
            severity = 9 if any(k in lower for k in extractor.high_keywords) else 6
            issue_type = "security" if "security" in lower or "vulnerability" in lower else "finding"
            mentioned_file = next(
                (
                    file.relative_path
                    for file in files
                    if file.relative_path in issue or file.path.name in issue
                ),
                None,
            )
            self.add_finding(
                ReviewFinding(
                    type=issue_type,
                    description=issue[:160],
                    file=mentioned_file,
                    severity=severity,
                    pass_number=self.current_pass,
                )
            )

        self.add_general_note(
            f"Pass {self.current_pass} reviewed {len(files)} files and produced {len(content)} characters."
        )

    def generate_next_pass_context(
        self,
        files: list[str],
        *,
        max_context_tokens: int = 500,
    ) -> str:
        max_chars = max(400, max_context_tokens * 4)
        lines = [
            f"### Review Context (Pass {self.current_pass})",
            "",
            f"Project: {self.project_name}",
            f"Review Type: {self.review_type}",
            f"Files in this pass: {len(files)} / {len(self.all_files)}",
            "",
        ]

        important = sorted(self.findings, key=lambda item: item.severity, reverse=True)[:5]
        if important:
            lines.extend(["#### Key Findings from Previous Passes", ""])
            for finding in important:
                suffix = f" (in {finding.file})" if finding.file else ""
                lines.append(f"- [{finding.type.upper()}] {finding.description}{suffix}")
            lines.append("")

        related = [
            summary
            for summary in self.file_summaries.values()
            if summary.path not in files
        ][:5]
        if related:
            lines.extend(["#### Related Files (Not in This Pass)", ""])
            for summary in related:
                lines.append(f"- {summary.path}: {summary.description}")
            lines.append("")

        elements = sorted(
            self.code_elements.values(),
            key=lambda item: item.importance,
            reverse=True,
        )[:10]
        if elements:
            lines.extend(["#### Important Code Elements", ""])
            for element in elements:
                signature = f": {element.signature}" if element.signature else ""
                lines.append(f"- {element.type} `{element.name}`{signature} (in {element.file})")
            lines.append("")

        if self.general_notes:
            lines.extend(["#### General Notes", ""])
            lines.extend(f"- {note}" for note in self.general_notes[-3:])
            lines.append("")

        context = "\n".join(lines)
        if len(context) > max_chars:
            return context[: max_chars - 3] + "..."
        return context
