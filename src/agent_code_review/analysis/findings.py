"""Finding extraction used by multi-pass context maintenance."""

from __future__ import annotations

import re
from pydantic import BaseModel, Field


class CategorizedFindings(BaseModel):
    """Findings grouped by severity."""

    high: set[str] = Field(default_factory=set)
    medium: set[str] = Field(default_factory=set)
    low: set[str] = Field(default_factory=set)


class FindingsExtractor:
    """Extract and classify review findings from Markdown text."""

    high_keywords = (
        "security",
        "vulnerability",
        "critical",
        "error",
        "bug",
        "crash",
        "memory leak",
        "sql injection",
        "xss",
        "csrf",
        "injection",
        "authentication",
        "authorization",
        "password",
        "token",
    )
    medium_keywords = (
        "warning",
        "deprecated",
        "inefficient",
        "refactor",
        "improve",
        "optimization",
        "maintainability",
        "readability",
        "complexity",
        "duplication",
        "architecture",
        "documentation",
        "test coverage",
        "error handling",
    )

    def extract_findings_from_passes(self, passes: list[dict[str, str]]) -> CategorizedFindings:
        findings = CategorizedFindings()
        for review_pass in passes:
            for issue in self.extract_issue_texts(review_pass.get("content", "")):
                self.add_issue(findings, issue)
        return findings

    def extract_issue_texts(self, content: str) -> list[str]:
        issues: list[str] = []
        for pattern in (r"^[\s]*[-*•]\s+(.+)$", r"^[\s]*\d+\.\s+(.+)$"):
            for match in re.finditer(pattern, content, flags=re.MULTILINE):
                issue = match.group(1).strip()
                if len(issue) > 10:
                    issues.append(issue)
        return list(dict.fromkeys(issues))

    def add_issue(self, findings: CategorizedFindings, issue: str) -> None:
        lower = issue.lower()
        if any(keyword in lower for keyword in self.high_keywords):
            findings.high.add(issue)
        elif any(keyword in lower for keyword in self.medium_keywords):
            findings.medium.add(issue)
        else:
            findings.low.add(issue)

    def calculate_overall_grade(self, findings: CategorizedFindings) -> str:
        total = len(findings.high) + len(findings.medium) + len(findings.low)
        if len(findings.high) > 5:
            return "D"
        if len(findings.high) > 2:
            return "C"
        if len(findings.high) > 0:
            return "C+"
        if len(findings.medium) > 10:
            return "C+"
        if len(findings.medium) > 5:
            return "B"
        if total > 5:
            return "A-"
        if total > 0:
            return "A"
        return "A+"
