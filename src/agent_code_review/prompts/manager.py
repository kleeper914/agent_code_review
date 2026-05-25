"""Resource-backed prompt manager for Phase 8 prompt migration."""

from __future__ import annotations

import json
import re
from importlib import resources
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from ..discovery import DiscoveredFile, ProjectContext
from ..orchestration.types import PromptFragment, ReviewOptions
from ..strategies.base import EnhancedReviewContext, ReviewIntent


PromptTemplateSource = Literal["custom", "framework", "language", "generic", "common", "fallback"]


class PromptTemplateResource(BaseModel):
    """A loaded prompt template and its source metadata."""

    content: str
    source: PromptTemplateSource
    path: str


class RenderedPrompt(BaseModel):
    """Rendered prompt text plus provenance metadata."""

    prompt: str
    metadata: dict[str, Any] = Field(default_factory=dict)


TEMPLATE_FILE_BY_REVIEW_TYPE: dict[str, str] = {
    "quick-fixes": "quick-fixes-review.hbs",
    "architectural": "architectural-review.hbs",
    "security": "security-review.hbs",
    "performance": "performance-review.hbs",
    "unused-code": "unused-code-review.hbs",
    "focused-unused-code": "focused-unused-code-review.hbs",
    "code-tracing-unused-code": "code-tracing-unused-code-review.hbs",
    "consolidated": "consolidated-review.hbs",
    "best-practices": "best-practices.hbs",
    "evaluation": "evaluation.hbs",
    "extract-patterns": "extract-patterns-review.hbs",
    "coding-test": "coding-test.hbs",
    "ai-integration": "ai-integration-review.hbs",
    "cloud-native": "cloud-native-review.hbs",
    "developer-experience": "developer-experience-review.hbs",
    "comprehensive": "comprehensive-review.hbs",
}

SCHEMA_BY_REVIEW_TYPE: dict[str, str] = {
    "quick-fixes": "quick-fixes-schema.md",
    "architectural": "architectural-schema.md",
    "security": "security-schema.md",
    "performance": "performance-schema.md",
    "unused-code": "unused-code-schema.md",
    "focused-unused-code": "focused-unused-code-schema.md",
    "code-tracing-unused-code": "code-tracing-unused-code-schema.md",
    "consolidated": "consolidated-review-schema.md",
    "best-practices": "best-practices-schema.md",
    "evaluation": "evaluation-schema.md",
    "extract-patterns": "extract-patterns-schema.md",
    "coding-test": "coding-test-schema.md",
    "ai-integration": "ai-integration-schema.md",
    "cloud-native": "cloud-native-schema.md",
    "developer-experience": "developer-experience-schema.md",
    "comprehensive": "consolidated-review-schema.md",
}


class PromptManager:
    """Load, render, and compose bundled prompt templates."""

    def build_prompt(
        self,
        options: ReviewOptions,
        context: ProjectContext,
        intent: ReviewIntent,
        enhanced_context: EnhancedReviewContext,
        *,
        files_override: list[DiscoveredFile] | None = None,
    ) -> RenderedPrompt:
        language = self._selected_language(options, context)
        framework = self._selected_framework(options, context)
        schema_resource = self.schema_resource_name(options.review_type, intent.schema_name)
        schema_instructions = self.read_schema_resource(schema_resource)
        template = self.get_template(
            review_type=options.review_type,
            language=language,
            framework=framework,
            prompt_file=options.prompt_file,
        )
        values = self._template_values(
            options,
            context,
            intent,
            enhanced_context,
            schema_instructions=schema_instructions,
            language=language,
            framework=framework,
            files_override=files_override,
        )
        if template.source == "fallback":
            rendered = self._fallback_prompt(values)
        else:
            rendered = self.render_template(template.content, values)
        base_prompt = self._append_review_inputs(rendered, values)
        fragments = [
            fragment
            if isinstance(fragment, PromptFragment)
            else PromptFragment.model_validate(fragment)
            for fragment in options.prompt_fragments
        ]
        prompt = self.compose_fragments(base_prompt, fragments)
        return RenderedPrompt(
            prompt=prompt,
            metadata={
                "template_source": template.source,
                "template_path": template.path,
                "schema_resource": schema_resource,
                "fragment_count": len(fragments),
                "language": language,
                "framework": framework,
            },
        )

    def get_template(
        self,
        *,
        review_type: str,
        language: str,
        framework: str | None = None,
        prompt_file: str | None = None,
    ) -> PromptTemplateResource:
        if prompt_file:
            path = Path(prompt_file).expanduser()
            return PromptTemplateResource(
                content=path.read_text(encoding="utf-8"),
                source="custom",
                path=str(path),
            )

        filename = TEMPLATE_FILE_BY_REVIEW_TYPE[review_type]
        alternatives = self._template_name_alternatives(filename)
        candidates: list[tuple[PromptTemplateSource, str]] = []
        if framework:
            candidates.extend(
                ("framework", f"frameworks/{framework}/{candidate}") for candidate in alternatives
            )
        if language:
            candidates.extend(
                ("language", f"languages/{language}/{candidate}") for candidate in alternatives
            )
        candidates.extend(
            ("generic", f"languages/generic/{candidate}") for candidate in alternatives
        )
        candidates.extend(("common", f"common/{candidate}") for candidate in alternatives)

        for source, relative_path in candidates:
            if self.template_resource_exists(relative_path):
                return PromptTemplateResource(
                    content=self.read_template_resource(relative_path),
                    source=source,
                    path=f"templates/{relative_path}",
                )

        return PromptTemplateResource(
            content="",
            source="fallback",
            path="fallback",
        )

    def render_template(self, template: str, values: dict[str, Any]) -> str:
        text = self._strip_frontmatter(template)
        previous = None
        while previous != text:
            previous = text
            text = self._render_partials(text, values)
            text = self._render_each_blocks(text, values)
            text = self._render_eq_blocks(text, values)
            text = self._render_if_blocks(text, values)
            text = self._render_unless_blocks(text, values)
        text = self._render_variables(text, values)
        return self._strip_unresolved_placeholders(text).strip()

    def compose_fragments(self, prompt: str, fragments: list[PromptFragment]) -> str:
        if not fragments:
            return prompt
        components = [
            PromptFragment(content=prompt, position="middle", priority=10),
            *fragments,
        ]
        ordered: list[str] = []
        for position in ("start", "middle", "end"):
            ordered.extend(
                item.content
                for item in sorted(
                    (fragment for fragment in components if fragment.position == position),
                    key=lambda fragment: fragment.priority,
                    reverse=True,
                )
                if item.content.strip()
            )
        return "\n\n".join(ordered)

    def read_template_resource(self, relative_path: str) -> str:
        return self._template_root().joinpath(relative_path).read_text(encoding="utf-8")

    def read_template_json(self, relative_path: str) -> dict[str, Any]:
        return json.loads(self.read_template_resource(relative_path))

    def template_resource_exists(self, relative_path: str) -> bool:
        return self._template_root().joinpath(relative_path).is_file()

    def read_schema_resource(self, name: str) -> str:
        return self._schema_root().joinpath(name).read_text(encoding="utf-8")

    def list_schema_resources(self) -> list[str]:
        return sorted(
            item.name for item in self._schema_root().iterdir() if item.name.endswith(".md")
        )

    def schema_resource_name(self, review_type: str, schema_name: str | None = None) -> str:
        resource_name = SCHEMA_BY_REVIEW_TYPE.get(review_type, "standard-review-schema.md")
        if self._schema_root().joinpath(resource_name).is_file():
            return resource_name
        if schema_name:
            schema_candidate = f"{schema_name}.md"
            if self._schema_root().joinpath(schema_candidate).is_file():
                return schema_candidate
        return "standard-review-schema.md"

    def _template_root(self):
        return resources.files("agent_code_review.prompts").joinpath("templates")

    def _schema_root(self):
        return resources.files("agent_code_review.prompts").joinpath("schemas")

    def _template_values(
        self,
        options: ReviewOptions,
        context: ProjectContext,
        intent: ReviewIntent,
        enhanced_context: EnhancedReviewContext,
        *,
        schema_instructions: str,
        language: str,
        framework: str | None,
        files_override: list[DiscoveredFile] | None,
    ) -> dict[str, Any]:
        framework_versions = self.read_template_json("common/variables/framework-versions.json")
        css_frameworks = self.read_template_json("common/variables/css-frameworks.json")
        language_instructions = self._language_instructions(language, framework)
        return {
            **framework_versions,
            **css_frameworks,
            "review_type": options.review_type,
            "reviewType": options.review_type,
            "project_name": context.project_name,
            "projectName": context.project_name,
            "title": intent.title,
            "instructions": intent.instructions,
            "focus_areas": intent.focus_areas,
            "output_expectations": intent.output_expectations,
            "focus_areas_block": self._bullet_list(intent.focus_areas),
            "output_expectations_block": self._bullet_list(intent.output_expectations),
            "context_block": self._context_block(enhanced_context),
            "docs_block": self._docs_block(context),
            "files_block": self._files_block(context, files_override=files_override),
            "schemaInstructions": schema_instructions,
            "SCHEMA_INSTRUCTIONS": schema_instructions,
            "schema_instructions": schema_instructions,
            "languageInstructions": language_instructions,
            "LANGUAGE_INSTRUCTIONS": language_instructions,
            "language_instructions": language_instructions,
            "language": language.upper(),
            "framework": framework.upper() if framework else "",
            "framework_name": framework or "",
            "CI_DATA": "",
            "ciData": "",
        }

    def _append_review_inputs(self, rendered_template: str, values: dict[str, Any]) -> str:
        return "\n\n".join(
            part.strip()
            for part in [
                rendered_template,
                "## Review Intent\n"
                f"Review type: {values['review_type']}\n\n"
                f"{values['instructions']}\n\n"
                "### Focus Areas\n"
                f"{values['focus_areas_block']}\n\n"
                "### Output Expectations\n"
                f"{values['output_expectations_block']}",
                "## Enhanced Context\n" + values["context_block"],
                "## Project Documentation\n" + values["docs_block"],
                "## Files To Review\n" + values["files_block"],
                "If no relevant issues are found, say so clearly and explain the evidence considered.",
            ]
            if part.strip()
        )

    def _fallback_prompt(self, values: dict[str, Any]) -> str:
        return (
            f"# {values['title']} for {values['project_name']}\n\n"
            "IMPORTANT: Do not repeat these instructions. Return only actionable review findings.\n\n"
            f"{values['schemaInstructions']}"
        )

    def _selected_language(self, options: ReviewOptions, context: ProjectContext) -> str:
        if options.language:
            return options.language.lower()
        if context.detection.language != "unknown":
            return context.detection.language.lower()
        languages = [file.language for file in context.files if file.language]
        if not languages:
            return "generic"
        return sorted(set(languages), key=languages.count, reverse=True)[0].lower()

    def _selected_framework(self, options: ReviewOptions, context: ProjectContext) -> str | None:
        if options.framework:
            return options.framework.lower()
        if context.detection.framework and context.detection.framework != "none":
            return context.detection.framework.lower()
        return None

    def _language_instructions(self, language: str, framework: str | None) -> str:
        normalized_language = language.upper() if language else "GENERIC"
        if framework:
            return (
                f"This code is written in {normalized_language}. It uses the "
                f"{framework.upper()} framework. Provide framework-specific advice."
            )
        return f"This code is written in {normalized_language}. Provide language-specific advice."

    def _template_name_alternatives(self, filename: str) -> list[str]:
        alternatives = [filename]
        if filename.endswith("-review.hbs"):
            alternatives.append(filename.replace("-review.hbs", ".hbs"))
        return list(dict.fromkeys(alternatives))

    def _strip_frontmatter(self, text: str) -> str:
        return re.sub(r"\A---\s*\n.*?\n---\s*\n", "", text, count=1, flags=re.DOTALL)

    def _render_partials(self, text: str, values: dict[str, Any]) -> str:
        pattern = re.compile(r"{{>\s*([A-Za-z0-9_./-]+)([^}]*)}}")

        def replace(match: re.Match[str]) -> str:
            partial_path = match.group(1)
            params = self._parse_partial_params(match.group(2))
            context = {**values, **params}
            try:
                partial = self.read_template_resource(f"{partial_path}.hbs")
            except FileNotFoundError:
                return ""
            return self.render_template(partial, context)

        return pattern.sub(replace, text)

    def _render_each_blocks(self, text: str, values: dict[str, Any]) -> str:
        pattern = re.compile(r"{{#each\s+([^}]+)}}(.*?){{/each}}", re.DOTALL)

        def replace(match: re.Match[str]) -> str:
            collection = self._resolve(match.group(1).strip(), values)
            if not isinstance(collection, list):
                return ""
            parts = []
            for index, item in enumerate(collection):
                item_context = {**values, "this": item, "@last": index == len(collection) - 1}
                body = self._render_unless_blocks(match.group(2), item_context)
                parts.append(self._render_variables(body, item_context))
            return "".join(parts)

        return pattern.sub(replace, text)

    def _render_eq_blocks(self, text: str, values: dict[str, Any]) -> str:
        pattern = re.compile(r"{{#eq\s+([^\s}]+)\s+([^}]+)}}(.*?){{/eq}}", re.DOTALL)

        def replace(match: re.Match[str]) -> str:
            left = self._resolve(match.group(1).strip(), values)
            right = self._literal_or_resolved(match.group(2).strip(), values)
            return match.group(3) if str(left).lower() == str(right).lower() else ""

        return pattern.sub(replace, text)

    def _render_if_blocks(self, text: str, values: dict[str, Any]) -> str:
        pattern = re.compile(r"{{#if\s+([^}]+)}}(.*?){{/if}}", re.DOTALL)

        def replace(match: re.Match[str]) -> str:
            body = match.group(2)
            truthy, falsey = self._split_else(body)
            return truthy if self._is_truthy(self._resolve(match.group(1).strip(), values)) else falsey

        return pattern.sub(replace, text)

    def _render_unless_blocks(self, text: str, values: dict[str, Any]) -> str:
        pattern = re.compile(r"{{#unless\s+([^}]+)}}(.*?){{/unless}}", re.DOTALL)

        def replace(match: re.Match[str]) -> str:
            return "" if self._is_truthy(self._resolve(match.group(1).strip(), values)) else match.group(2)

        return pattern.sub(replace, text)

    def _render_variables(self, text: str, values: dict[str, Any]) -> str:
        pattern = re.compile(r"{{{?\s*([^{}#/>][^{}]*?)\s*}?}}")

        def replace(match: re.Match[str]) -> str:
            value = self._resolve(match.group(1).strip(), values)
            if value is None:
                return ""
            if isinstance(value, list):
                return ", ".join(str(item) for item in value)
            return str(value)

        return pattern.sub(replace, text)

    def _strip_unresolved_placeholders(self, text: str) -> str:
        return re.sub(r"{{[^{}]+}}", "", text)

    def _parse_partial_params(self, raw: str) -> dict[str, Any]:
        params: dict[str, Any] = {}
        for key, quoted, bare in re.findall(r"([A-Za-z_][A-Za-z0-9_]*)=(?:\"([^\"]*)\"|(\S+))", raw):
            value = quoted if quoted else bare
            if value == "true":
                params[key] = True
            elif value == "false":
                params[key] = False
            else:
                params[key] = value
        return params

    def _split_else(self, body: str) -> tuple[str, str]:
        marker = "{{else}}"
        if marker not in body:
            return body, ""
        before, after = body.split(marker, 1)
        return before, after

    def _literal_or_resolved(self, raw: str, values: dict[str, Any]) -> Any:
        if (raw.startswith('"') and raw.endswith('"')) or (raw.startswith("'") and raw.endswith("'")):
            return raw[1:-1]
        return self._resolve(raw, values)

    def _resolve(self, path: str, values: dict[str, Any]) -> Any:
        if path in values:
            return values[path]
        current: Any = values
        for part in path.split("."):
            if part == "":
                continue
            index_match = re.fullmatch(r"\[(\d+)]", part)
            if index_match:
                if isinstance(current, list):
                    current = current[int(index_match.group(1))]
                    continue
                return None
            if isinstance(current, dict):
                current = current.get(part)
            elif isinstance(current, list) and part.isdigit():
                current = current[int(part)]
            else:
                current = getattr(current, part, None)
            if current is None:
                return None
        return current

    def _is_truthy(self, value: Any) -> bool:
        if value in (None, "", False, [], {}):
            return False
        return True

    def _bullet_list(self, items: list[str]) -> str:
        return "\n".join(f"- {item}" for item in items) or "- None"

    def _context_block(self, enhanced_context: EnhancedReviewContext) -> str:
        if not enhanced_context.context_sections:
            return "No enhanced context sections were provided."
        return "\n\n".join(
            f"### {section.title}\n{section.content}"
            for section in enhanced_context.context_sections
        )

    def _docs_block(self, context: ProjectContext) -> str:
        if not context.docs:
            return "No project documentation was included."
        return "\n\n".join(f"### {name}\n{content}" for name, content in context.docs.items())

    def _files_block(
        self,
        context: ProjectContext,
        *,
        files_override: list[DiscoveredFile] | None = None,
    ) -> str:
        files = files_override if files_override is not None else context.files
        sections = [
            f"### {file.relative_path}\n```{file.language}\n{file.content}\n```"
            for file in files
        ]
        return "\n\n".join(sections) or "No files were included."


__all__ = [
    "PromptFragment",
    "PromptManager",
    "PromptTemplateResource",
    "RenderedPrompt",
]
