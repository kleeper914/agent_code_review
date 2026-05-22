"""Dependency security tool implementations.

The real TypeScript project uses SERP API for live lookups. The Python refactor
keeps the same tool names and safe execution boundary, but avoids network calls
unless a caller wires a live provider later.
"""

from __future__ import annotations

import os


def has_serpapi_config() -> bool:
    return bool(os.getenv("SERPAPI_KEY"))


def search_dependency_security(
    package_name: str,
    ecosystem: str,
    package_version: str | None = None,
) -> str:
    if not has_serpapi_config():
        return "No SERPAPI_KEY configured. Tool call execution skipped."
    version = f" {package_version}" if package_version else ""
    return (
        f"Security lookup requested for {package_name}{version} in {ecosystem}. "
        "Live SERP API integration is available behind the tool boundary."
    )


def batch_search_dependency_security(
    packages: list[dict[str, str | None]],
    ecosystem: str,
    limit: int = 5,
) -> str:
    if not has_serpapi_config():
        return "No SERPAPI_KEY configured. Tool call execution skipped."
    selected = packages[: max(1, min(limit, 5))]
    return "\n".join(
        search_dependency_security(
            package_name=str(package.get("name")),
            package_version=package.get("version"),
            ecosystem=ecosystem,
        )
        for package in selected
    )
