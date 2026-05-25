# Plugin Development Guide

Python plugins extend the strategy registry without changing the built-in review pipeline. The loader accepts `.py` files from a plugin directory and calls either `register(registry)` or `get_plugin()`.

## Minimal Plugin

```python
from agent_code_review.plugins import Plugin


def register(registry):
    registry.register(
        Plugin(
            name="example-security",
            description="Example security strategy",
            source="example",
            strategy_factory=lambda: MySecurityStrategy(),
        )
    )
```

An example lives at `examples/plugins/security_strategy_plugin.py`.

## Run With A Plugin

```bash
uv run agent-code-review . --plugins-dir ./examples/plugins --strategy example-security
```

Expected input:

- A plugin directory.
- Optional `--strategy` name.

Expected output:

- If the plugin exists, the named strategy is used.
- If the plugin is missing, Python falls back to the default strategy and emits a warning.
- If plugin loading fails, the warning is sanitized so local paths and API keys are not exposed.

## TypeScript Parity

The TypeScript implementation uses `PluginManager` and `StrategyFactory` to prefer explicit plugin strategies and fall back to defaults. Python mirrors that behavior with `aicode_review.plugins` and `aicode_review.strategies.factory`.
