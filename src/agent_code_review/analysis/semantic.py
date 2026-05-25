"""TreeSitter-friendly semantic chunking with graceful fallback."""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, Field

from ..discovery import DiscoveredFile

from .chunking import ReviewChunk, ReviewUnit, pack_review_units
from .tokens import count_tokens


class Declaration(BaseModel):
    """A top-level declaration discovered in source code."""

    type: str
    name: str
    start_line: int
    end_line: int
    dependencies: list[str] = Field(default_factory=list)
    cyclomatic_complexity: int = 1
    export_status: str = "internal"
    documentation: str | None = None


class ImportRelationship(BaseModel):
    """Import relationship extracted from source code."""

    imported: str
    from_module: str
    import_type: str = "named"
    line: int = 1


class SemanticAnalysis(BaseModel):
    """Semantic analysis for one file."""

    language: str
    file_path: str
    total_lines: int
    declarations: list[Declaration] = Field(default_factory=list)
    imports: list[ImportRelationship] = Field(default_factory=list)
    complexity: dict[str, int] = Field(default_factory=dict)
    parser: str = "unknown"
    parser_available: bool = False
    fallback_reason: str | None = None


class SemanticChunkingResult(BaseModel):
    """Integrated semantic chunking result."""

    chunks: list[ReviewChunk]
    analyses: list[SemanticAnalysis] = Field(default_factory=list)
    method: str
    fallback_used: bool = False
    errors: list[str] = Field(default_factory=list)
    summary: dict[str, Any] = Field(default_factory=dict)


SUPPORTED_LANGUAGES = {"python", "typescript", "javascript", "ruby", "php"}


@dataclass(frozen=True)
class SemanticOptions:
    """Semantic chunking options."""

    review_type: str = "quick-fixes"
    model_name: str = "openai:gpt-4o"
    max_tokens_per_chunk: int = 4_000
    max_file_size: int = 1_000_000


def analyze_semantic_chunks(
    files: list[DiscoveredFile],
    *,
    review_type: str,
    model_name: str = "openai:gpt-4o",
    max_tokens_per_chunk: int = 4_000,
) -> SemanticChunkingResult:
    options = SemanticOptions(
        review_type=review_type,
        model_name=model_name,
        max_tokens_per_chunk=max_tokens_per_chunk,
    )
    analyses: list[SemanticAnalysis] = []
    units: list[ReviewUnit] = []
    errors: list[str] = []

    for file in files:
        language = _normalize_language(file.language, file.relative_path)
        if language not in SUPPORTED_LANGUAGES:
            errors.append(f"Unsupported language for semantic chunking: {file.relative_path}")
            continue
        if len(file.content.encode("utf-8")) > options.max_file_size:
            errors.append(f"File too large for semantic chunking: {file.relative_path}")
            continue
        try:
            analysis = _analyze_file(file, language)
        except Exception as exc:
            errors.append(f"Semantic analysis failed for {file.relative_path}: {exc}")
            continue
        analyses.append(analysis)
        units.extend(_units_from_analysis(file, analysis, options))

    if not units:
        return SemanticChunkingResult(
            chunks=_traditional_file_chunks(files, options),
            analyses=analyses,
            method="traditional",
            fallback_used=True,
            errors=errors or ["No semantic units could be generated"],
            summary={"semanticFiles": len(analyses), "semanticUnits": 0},
        )

    chunks = pack_review_units(units, max_chunk_size=max_tokens_per_chunk)
    return SemanticChunkingResult(
        chunks=chunks,
        analyses=analyses,
        method="semantic",
        fallback_used=False,
        errors=errors,
        summary={
            "semanticFiles": len(analyses),
            "semanticUnits": len(units),
            "chunks": len(chunks),
            "declarations": sum(len(analysis.declarations) for analysis in analyses),
        },
    )


def _analyze_file(file: DiscoveredFile, language: str) -> SemanticAnalysis:
    tree_sitter_analysis = _try_tree_sitter_analysis(file, language)
    if tree_sitter_analysis is not None:
        return tree_sitter_analysis
    if language == "python":
        return _analyze_python(file)
    return _analyze_with_regex(file, language)


def _analyze_python(file: DiscoveredFile) -> SemanticAnalysis:
    tree = ast.parse(file.content)
    declarations: list[Declaration] = []
    imports: list[ImportRelationship] = []
    lines = file.content.splitlines() or [""]

    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                imports.append(
                    ImportRelationship(
                        imported=alias.name,
                        from_module=getattr(node, "module", None) or alias.name,
                        import_type="named",
                        line=getattr(node, "lineno", 1),
                    )
                )
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            declarations.append(_python_declaration(node, lines))

    return SemanticAnalysis(
        language="python",
        file_path=file.relative_path,
        total_lines=len(lines),
        declarations=declarations,
        imports=imports,
        complexity={
            "cyclomaticComplexity": sum(item.cyclomatic_complexity for item in declarations),
            "functionCount": sum(1 for item in declarations if item.type == "function"),
            "classCount": sum(1 for item in declarations if item.type == "class"),
            "totalDeclarations": len(declarations),
        },
        parser="python_ast",
        parser_available=True,
        fallback_reason="tree_sitter_unavailable",
    )


def _python_declaration(node: ast.AST, lines: list[str]) -> Declaration:
    end_line = getattr(node, "end_lineno", getattr(node, "lineno", 1))
    name = getattr(node, "name", "anonymous")
    node_type = "class" if isinstance(node, ast.ClassDef) else "function"
    dependencies = sorted(
        {
            child.id
            for child in ast.walk(node)
            if isinstance(child, ast.Name) and child.id != name
        }
    )[:20]
    doc = ast.get_docstring(node)
    return Declaration(
        type=node_type,
        name=name,
        start_line=getattr(node, "lineno", 1),
        end_line=end_line,
        dependencies=dependencies,
        cyclomatic_complexity=_python_complexity(node),
        export_status="internal" if name.startswith("_") else "exported",
        documentation=doc,
    )


def _python_complexity(node: ast.AST) -> int:
    branches = (ast.If, ast.For, ast.While, ast.Try, ast.ExceptHandler, ast.BoolOp, ast.IfExp)
    return 1 + sum(1 for child in ast.walk(node) if isinstance(child, branches))


def _analyze_with_regex(file: DiscoveredFile, language: str) -> SemanticAnalysis:
    lines = file.content.splitlines() or [""]
    declarations: list[Declaration] = []
    imports: list[ImportRelationship] = []
    declaration_patterns = [
        ("class", re.compile(r"^\s*(?:export\s+)?class\s+([A-Za-z_$][\w$]*)")),
        ("interface", re.compile(r"^\s*(?:export\s+)?interface\s+([A-Za-z_$][\w$]*)")),
        ("function", re.compile(r"^\s*(?:export\s+)?(?:async\s+)?function\s+([A-Za-z_$][\w$]*)")),
        ("function", re.compile(r"^\s*(?:export\s+)?const\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?\(")),
        ("function", re.compile(r"^\s*def\s+([A-Za-z_][\w]*)")),
    ]
    import_pattern = re.compile(
        r"^\s*(?:import\s+.+?\s+from\s+['\"]([^'\"]+)['\"]|"
        r"import\s+['\"]([^'\"]+)['\"]|"
        r"from\s+([A-Za-z0-9_.]+)\s+import|"
        r"import\s+([A-Za-z0-9_.]+)|"
        r"require\s+['\"]([^'\"]+)['\"]|"
        r"use\s+([^;]+);)"
    )

    for index, line in enumerate(lines, start=1):
        if match := import_pattern.search(line):
            module = next((group for group in match.groups() if group), match.group(0))
            imports.append(
                ImportRelationship(
                    imported=module.strip()[:80],
                    from_module=module.strip()[:80],
                    line=index,
                )
            )
        for decl_type, pattern in declaration_patterns:
            match = pattern.search(line)
            if not match:
                continue
            end_line = _find_block_end(lines, index)
            declarations.append(
                Declaration(
                    type=decl_type,
                    name=match.group(1),
                    start_line=index,
                    end_line=end_line,
                    dependencies=[],
                    cyclomatic_complexity=_line_range_complexity(lines[index - 1 : end_line]),
                    export_status="exported" if "export " in line else "internal",
                )
            )
            break

    return SemanticAnalysis(
        language=language,
        file_path=file.relative_path,
        total_lines=len(lines),
        declarations=declarations,
        imports=imports,
        complexity={
            "cyclomaticComplexity": sum(item.cyclomatic_complexity for item in declarations),
            "functionCount": sum(1 for item in declarations if item.type == "function"),
            "classCount": sum(1 for item in declarations if item.type == "class"),
            "totalDeclarations": len(declarations),
        },
        parser="regex",
        parser_available=False,
        fallback_reason="tree_sitter_unavailable",
    )


def _try_tree_sitter_analysis(file: DiscoveredFile, language: str) -> SemanticAnalysis | None:
    parser_info = _tree_sitter_parser(language)
    if parser_info is None:
        return None
    parser, parser_name = parser_info
    source = file.content.encode("utf-8")
    tree = parser.parse(source)
    root = tree.root_node
    lines = file.content.splitlines() or [""]
    declarations: list[Declaration] = []
    imports: list[ImportRelationship] = []

    def visit(node: Any, depth: int = 0) -> None:
        node_type = getattr(node, "type", "")
        if node_type in _tree_sitter_declaration_types(language):
            declaration = _declaration_from_tree_sitter_node(node, source, lines, language)
            if declaration is not None:
                declarations.append(declaration)
        if node_type in _tree_sitter_import_types(language):
            import_ = _import_from_tree_sitter_node(node, source)
            if import_ is not None:
                imports.append(import_)
        for child in getattr(node, "children", []):
            visit(child, depth + 1)

    visit(root)
    return SemanticAnalysis(
        language=language,
        file_path=file.relative_path,
        total_lines=len(lines),
        declarations=declarations,
        imports=imports,
        complexity={
            "cyclomaticComplexity": sum(item.cyclomatic_complexity for item in declarations),
            "functionCount": sum(1 for item in declarations if item.type == "function"),
            "classCount": sum(1 for item in declarations if item.type == "class"),
            "totalDeclarations": len(declarations),
        },
        parser=parser_name,
        parser_available=True,
        fallback_reason="parse_error" if getattr(root, "has_error", False) else None,
    )


def _tree_sitter_parser(language: str) -> tuple[Any, str] | None:
    try:
        from tree_sitter import Language, Parser
    except Exception:
        return None

    try:
        grammar = _tree_sitter_language(language)
        if grammar is None:
            return None
        ts_language = Language(grammar) if not isinstance(grammar, Language) else grammar
        parser = Parser()
        if hasattr(parser, "set_language"):
            parser.set_language(ts_language)
        else:
            parser.language = ts_language
        return parser, "tree_sitter"
    except Exception:
        return None


def _tree_sitter_language(language: str) -> Any | None:
    if language == "python":
        import tree_sitter_python

        return tree_sitter_python.language()
    if language in {"javascript", "typescript"}:
        import tree_sitter_typescript

        if language == "javascript" and hasattr(tree_sitter_typescript, "language_tsx"):
            return tree_sitter_typescript.language_tsx()
        if hasattr(tree_sitter_typescript, "language_typescript"):
            return tree_sitter_typescript.language_typescript()
        return tree_sitter_typescript.language()
    if language == "ruby":
        import tree_sitter_ruby

        return tree_sitter_ruby.language()
    if language == "php":
        import tree_sitter_php

        return tree_sitter_php.language()
    return None


def _tree_sitter_declaration_types(language: str) -> set[str]:
    return {
        "typescript": {
            "function_declaration",
            "class_declaration",
            "interface_declaration",
            "type_alias_declaration",
            "lexical_declaration",
        },
        "javascript": {"function_declaration", "class_declaration", "lexical_declaration"},
        "python": {"function_definition", "class_definition"},
        "ruby": {"method", "class", "module"},
        "php": {"function_definition", "method_declaration", "class_declaration", "interface_declaration"},
    }.get(language, set())


def _tree_sitter_import_types(language: str) -> set[str]:
    return {
        "typescript": {"import_statement"},
        "javascript": {"import_statement"},
        "python": {"import_statement", "import_from_statement"},
        "ruby": {"call"},
        "php": {"namespace_use_declaration", "use_declaration"},
    }.get(language, set())


def _declaration_from_tree_sitter_node(
    node: Any,
    source: bytes,
    lines: list[str],
    language: str,
) -> Declaration | None:
    text = source[node.start_byte : node.end_byte].decode("utf-8", errors="replace")
    name = _extract_name_from_text(text, language) or _named_child_text(node, source)
    if not name:
        return None
    start = node.start_point[0] + 1
    end = node.end_point[0] + 1
    kind = _declaration_kind(getattr(node, "type", ""))
    return Declaration(
        type=kind,
        name=name,
        start_line=start,
        end_line=end,
        dependencies=_identifier_dependencies(text, name),
        cyclomatic_complexity=_line_range_complexity(lines[start - 1 : end]),
        export_status="exported" if re.search(r"\bexport\b", text) else "internal",
    )


def _import_from_tree_sitter_node(node: Any, source: bytes) -> ImportRelationship | None:
    text = source[node.start_byte : node.end_byte].decode("utf-8", errors="replace")
    module = _extract_import_module(text)
    if not module:
        return None
    return ImportRelationship(
        imported=module,
        from_module=module,
        import_type="named" if "{" in text or " import " in text else "default",
        line=node.start_point[0] + 1,
    )


def _named_child_text(node: Any, source: bytes) -> str | None:
    for child in getattr(node, "children", []):
        if getattr(child, "type", "") in {"identifier", "constant", "name"}:
            return source[child.start_byte : child.end_byte].decode("utf-8", errors="replace")
    return None


def _extract_name_from_text(text: str, language: str) -> str | None:
    patterns = [
        r"\b(?:class|interface|function|def|module)\s+([A-Za-z_$][\w$]*)",
        r"\bconst\s+([A-Za-z_$][\w$]*)\s*=",
        r"\btype\s+([A-Za-z_$][\w$]*)\s*=",
    ]
    if language == "php":
        patterns.insert(0, r"\b(?:class|interface|function)\s+([A-Za-z_][\w]*)")
    for pattern in patterns:
        if match := re.search(pattern, text):
            return match.group(1)
    return None


def _extract_import_module(text: str) -> str | None:
    patterns = [
        r"from\s+['\"]([^'\"]+)['\"]",
        r"import\s+['\"]([^'\"]+)['\"]",
        r"from\s+([A-Za-z0-9_.]+)\s+import",
        r"import\s+([A-Za-z0-9_.]+)",
        r"require\s+['\"]([^'\"]+)['\"]",
        r"use\s+([^;]+);",
    ]
    for pattern in patterns:
        if match := re.search(pattern, text):
            return match.group(1).strip()
    return None


def _declaration_kind(node_type: str) -> str:
    if "class" in node_type:
        return "class"
    if "interface" in node_type:
        return "interface"
    if "type_alias" in node_type:
        return "type"
    return "function"


def _identifier_dependencies(text: str, name: str) -> list[str]:
    identifiers = set(re.findall(r"\b[A-Za-z_][A-Za-z0-9_]*\b", text))
    return sorted(identifier for identifier in identifiers if identifier != name)[:20]


def _units_from_analysis(
    file: DiscoveredFile,
    analysis: SemanticAnalysis,
    options: SemanticOptions,
) -> list[ReviewUnit]:
    units: list[ReviewUnit] = []
    lines = file.content.splitlines()
    for index, declaration in enumerate(analysis.declarations, start=1):
        start = max(1, declaration.start_line)
        end = max(start, declaration.end_line)
        content = "\n".join(lines[start - 1 : end])
        tokens = count_tokens(content or file.content, options.model_name)
        units.append(
            ReviewUnit(
                id=f"{file.relative_path}::{declaration.name}::{index}",
                files=[file.relative_path],
                estimated_tokens=tokens,
                kind=declaration.type,
                content=content,
                declarations=[declaration],
                metadata={
                    "lineRange": [start, end],
                    "reviewType": options.review_type,
                    "language": analysis.language,
                },
            )
        )
    if not units:
        units.append(
            ReviewUnit(
                id=f"{file.relative_path}::module",
                files=[file.relative_path],
                estimated_tokens=count_tokens(file.content, options.model_name),
                kind="module",
                content=file.content,
                declarations=[],
                metadata={"lineRange": [1, len(lines) or 1], "language": analysis.language},
            )
        )
    return units


def _traditional_file_chunks(files: list[DiscoveredFile], options: SemanticOptions) -> list[ReviewChunk]:
    units = [
        ReviewUnit(
            id=file.relative_path,
            files=[file.relative_path],
            estimated_tokens=count_tokens(file.content, options.model_name),
            kind="file",
            content=file.content,
            declarations=[],
            metadata={"fallback": True},
        )
        for file in files
    ]
    return pack_review_units(units, max_chunk_size=options.max_tokens_per_chunk)


def _normalize_language(language: str, relative_path: str) -> str:
    if language in {"typescript", "javascript", "python", "ruby", "php"}:
        return language
    suffix = relative_path.rsplit(".", 1)[-1].lower() if "." in relative_path else ""
    return {
        "ts": "typescript",
        "tsx": "typescript",
        "js": "javascript",
        "jsx": "javascript",
        "py": "python",
        "rb": "ruby",
        "php": "php",
    }.get(suffix, language)


def _find_block_end(lines: list[str], start_line: int) -> int:
    start_index = start_line - 1
    start_indent = len(lines[start_index]) - len(lines[start_index].lstrip())
    for index in range(start_index + 1, len(lines)):
        line = lines[index]
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip())
        if indent <= start_indent and re.match(r"^\s*(?:export\s+)?(?:class|interface|function|const|def)\b", line):
            return index
    return len(lines)


def _line_range_complexity(lines: list[str]) -> int:
    text = "\n".join(lines)
    return 1 + len(re.findall(r"\b(if|for|while|catch|case|&&|\|\|)\b", text))
