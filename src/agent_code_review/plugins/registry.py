"""Plugin registry for custom review strategies."""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path
from typing import Any
import warnings

from pydantic import BaseModel, ConfigDict

from ..strategies.base import ReviewStrategy


class PluginRegistration(BaseModel):
    """Registered plugin metadata and executable strategy."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str
    description: str
    strategy: Any
    version: str = "0.1.0"
    author: str | None = None
    source: str = "builtin"


class PluginRegistry:
    """In-memory registry for built-in and local strategies."""

    def __init__(self) -> None:
        self._plugins: dict[str, PluginRegistration] = {}

    def register(self, registration: PluginRegistration) -> None:
        # 中文注释：插件名是用户可见路由键，后注册者覆盖前者，便于本地插件替换内置策略。
        self._plugins[registration.name] = registration

    def get(self, name: str) -> PluginRegistration | None:
        return self._plugins.get(name)

    def get_strategy(self, name: str) -> ReviewStrategy:
        plugin = self.get(name)
        if plugin is None:
            raise ValueError(f"Plugin strategy not found: {name}")
        return plugin.strategy

    def list_plugins(self) -> list[PluginRegistration]:
        return sorted(self._plugins.values(), key=lambda item: item.name)


def create_default_registry() -> PluginRegistry:
    from ..strategies.architectural import ArchitecturalReviewStrategy
    from ..strategies.coding_test import CodingTestReviewStrategy
    from ..strategies.compatibility import CompatibilityReviewStrategy
    from ..strategies.extract_patterns import ExtractPatternsReviewStrategy
    from ..strategies.performance import PerformanceReviewStrategy
    from ..strategies.quick_fixes import QuickFixesReviewStrategy
    from ..strategies.security import SecurityReviewStrategy
    from ..strategies.unused_code import (
        CodeTracingUnusedCodeReviewStrategy,
        FocusedUnusedCodeReviewStrategy,
        UnusedCodeReviewStrategy,
    )

    registry = PluginRegistry()
    for name, description, strategy in [
        ("quick-fixes", "Built-in quick fixes review", QuickFixesReviewStrategy()),
        ("security", "Built-in security review", SecurityReviewStrategy()),
        ("architectural", "Built-in architectural review", ArchitecturalReviewStrategy()),
        ("performance", "Built-in performance review", PerformanceReviewStrategy()),
        ("coding-test", "Built-in coding-test assessment", CodingTestReviewStrategy()),
        ("unused-code", "Built-in unused-code review", UnusedCodeReviewStrategy()),
        (
            "focused-unused-code",
            "Built-in focused unused-code review",
            FocusedUnusedCodeReviewStrategy("focused-unused-code"),
        ),
        (
            "code-tracing-unused-code",
            "Built-in code-tracing unused-code review",
            CodeTracingUnusedCodeReviewStrategy("code-tracing-unused-code"),
        ),
        (
            "comprehensive",
            "Phase 7 comprehensive review",
            CompatibilityReviewStrategy("comprehensive"),
        ),
        (
            "best-practices",
            "Phase 7 best-practices review",
            CompatibilityReviewStrategy("best-practices"),
        ),
        ("evaluation", "Phase 7 evaluation review", CompatibilityReviewStrategy("evaluation")),
        ("extract-patterns", "Built-in extract-patterns review", ExtractPatternsReviewStrategy()),
        (
            "ai-integration",
            "Phase 7 AI integration review",
            CompatibilityReviewStrategy("ai-integration"),
        ),
        (
            "cloud-native",
            "Phase 7 cloud-native review",
            CompatibilityReviewStrategy("cloud-native"),
        ),
        (
            "developer-experience",
            "Phase 7 developer-experience review",
            CompatibilityReviewStrategy("developer-experience"),
        ),
        (
            "consolidated",
            "Phase 7 consolidated review",
            CompatibilityReviewStrategy("consolidated"),
        ),
    ]:
        registry.register(
            PluginRegistration(
                name=name,
                description=description,
                strategy=strategy,
                source="builtin",
            )
        )
    return registry


def load_plugins_from_directory(
    plugins_dir: str | Path | None,
    registry: PluginRegistry,
    *,
    warnings_list: list[str] | None = None,
) -> list[str]:
    if not plugins_dir:
        return []
    directory = Path(plugins_dir).expanduser()
    if not directory.exists():
        return []
    loaded: list[str] = []
    for path in sorted(directory.glob("*.py")):
        before = {plugin.name for plugin in registry.list_plugins()}
        try:
            load_plugin_from_module(path, registry)
        except Exception as exc:
            message = _redact_plugin_error(str(exc), path)
            if warnings_list is not None:
                warnings_list.append(message)
            warnings.warn(message, RuntimeWarning, stacklevel=2)
            continue
        after = {plugin.name for plugin in registry.list_plugins()}
        loaded.extend(sorted(after - before))
    return loaded


def load_plugin_from_module(path: str | Path, registry: PluginRegistry) -> None:
    module_path = Path(path).expanduser().resolve()
    module_name = f"aicode_review_local_plugin_{module_path.stem}_{abs(hash(module_path))}"
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise ValueError(f"Unable to load plugin module: {module_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)

    register = getattr(module, "register", None)
    if callable(register):
        register(registry)
        return

    get_plugin = getattr(module, "get_plugin", None)
    if callable(get_plugin):
        plugin = get_plugin()
        if isinstance(plugin, PluginRegistration):
            registry.register(plugin)
            return
        if isinstance(plugin, dict):
            registry.register(PluginRegistration(**plugin))
            return

    raise ValueError(f"Plugin module must expose register(registry) or get_plugin(): {module_path}")


def plugin_to_row(plugin: PluginRegistration) -> dict[str, Any]:
    return {
        "name": plugin.name,
        "description": plugin.description,
        "source": plugin.source,
        "version": plugin.version,
    }


def _redact_plugin_error(message: str, plugin_path: Path) -> str:
    """Remove local filesystem and secret material before surfacing plugin failures."""

    safe = message
    for part in [plugin_path, *plugin_path.parents]:
        safe = safe.replace(str(part), "[PATH]")
    safe = re.sub(
        r"(?i)((?:api[_-]?key|token|secret|password|credential)\s*=\s*)\S+",
        r"\1[REDACTED]",
        safe,
    )
    safe = re.sub(r"(?i)sk-[A-Za-z0-9_-]+", "[REDACTED]", safe)
    return f"Plugin load failed for [PATH]: {safe}"
