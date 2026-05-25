"""LangGraph-backed minimal review orchestration."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, TypedDict

from ..analysis import ReviewContext, SemanticChunkingResult
from ..analysis.chunking import ReviewChunk
from ..analysis.tokens import TokenAnalysisOptions, TokenAnalysisResult, analyze_files
from ..analysis.semantic import analyze_semantic_chunks
from ..config import ResolvedConfig, resolve_config
from ..discovery import DiscoveredFile, ProjectContext, discover_project_context
from ..llm_clients import GenerationOptions, LLMResponse, create_llm_client
from ..llm_clients.costs import (
    CostInfo,
    aggregate_costs,
    estimate_cost_from_usage,
    usage_from_cost,
)
from ..memory import FileMemoryStore, MemoryEntry
from ..observability import get_observability
from ..prompts import PromptPackage, build_prompt_package
from ..runtime import RunLevel, RunPhase, RuntimeContext, create_runtime
from ..strategies import (
    EnhancedReviewContext,
    ReviewIntent,
    ReviewStrategy,
    get_strategy,
)
from ..tools import (
    DependencyToolContext,
    ToolCallSpec,
    execute_tool_call,
    prepare_dependency_tool_context,
)

from .output_manager import OutputManager
from .types import PassResult, ReviewOptions, ReviewResult


class ReviewState(TypedDict, total=False):
    options: ReviewOptions
    config: ResolvedConfig
    runtime: RuntimeContext
    context: ProjectContext
    strategy: ReviewStrategy
    intent: ReviewIntent
    enhanced_context: EnhancedReviewContext
    prompt_package: PromptPackage
    prompt: str
    response: LLMResponse
    postprocess_metadata: dict[str, Any]
    postprocessed_content: str
    token_analysis: TokenAnalysisResult
    semantic_result: SemanticChunkingResult
    review_chunks: list[ReviewChunk]
    memory_context: str
    dependency_tool_context: DependencyToolContext
    pass_results: list[PassResult]
    result: ReviewResult


def run_review(
    options: ReviewOptions,
    config: ResolvedConfig | None = None,
    runtime: RuntimeContext | None = None,
) -> ReviewResult:
    resolved_config = config or resolve_config(
        cli_model=options.model,
        cli_output_dir=options.output_dir,
        cli_output_format=options.output,
        cli_api_keys=options.api_keys,
        cli_log_level=options.log_level,
        debug=options.debug,
        skip_key_check=options.skip_key_check,
    )
    resolved_runtime = runtime or create_runtime(resolved_config, options)

    state: ReviewState = {
        "options": options,
        "config": resolved_config,
        "runtime": resolved_runtime,
    }
    final_state = _run_langgraph_workflow(state)
    result = final_state["result"]
    if options.stdout or options.return_only:
        result.metadata["stdout"] = True
        result.metadata["returnOnly"] = options.return_only
        resolved_runtime.emit(
            RunPhase.REPORT,
            "Report file skipped by output policy",
            metadata={
                "format": options.output,
                "stdout": options.stdout,
                "returnOnly": options.return_only,
            },
        )
        return result
    started = datetime.now(timezone.utc)
    with get_observability().start_span(
        "orchestration.save_report",
        {"format": options.output, "review_type": options.review_type},
    ):
        artifact = OutputManager(resolved_config.output_dir).save(result, options)
    duration_ms = (datetime.now(timezone.utc) - started).total_seconds() * 1000
    output_path = artifact.output_path
    if artifact.raw_data_path:
        result.metadata["rawDataPath"] = str(artifact.raw_data_path)
    if artifact.diagram_paths:
        result.metadata["diagramPaths"] = [str(path) for path in artifact.diagram_paths]
    if artifact.removal_script_path:
        result.metadata["removalScriptPath"] = str(artifact.removal_script_path)
    resolved_runtime.emit(
        RunPhase.REPORT,
        "Report saved",
        metadata={"outputPath": str(output_path), "format": options.output},
        duration_ms=duration_ms,
    )
    return result


def _run_langgraph_workflow(state: ReviewState) -> ReviewState:
    try:
        from langgraph.graph import END, START, StateGraph

        workflow = StateGraph(ReviewState)
        workflow.add_node("discover", _discover_context)
        workflow.add_node("analyze_context", _analyze_context)
        workflow.add_node("select_strategy", _select_strategy)
        workflow.add_node("enhance_context", _enhance_context)
        workflow.add_node("prompt", _build_prompt)
        workflow.add_node("invoke", _invoke_model)
        workflow.add_node("postprocess", _postprocess_response)
        workflow.add_node("result", _build_result)
        workflow.add_node("estimate_result", _build_estimate_result)
        workflow.add_node("multi_pass", _run_multi_pass)
        workflow.add_edge(START, "discover")
        workflow.add_edge("discover", "analyze_context")
        workflow.add_conditional_edges(
            "analyze_context",
            _route_after_analysis,
            {
                "estimate": "estimate_result",
                "single_pass": "select_strategy",
                "multi_pass": "select_strategy",
            },
        )
        workflow.add_edge("select_strategy", "enhance_context")
        workflow.add_conditional_edges(
            "enhance_context",
            _route_after_analysis,
            {
                "estimate": "estimate_result",
                "single_pass": "prompt",
                "multi_pass": "multi_pass",
            },
        )
        workflow.add_edge("prompt", "invoke")
        workflow.add_edge("invoke", "postprocess")
        workflow.add_edge("postprocess", "result")
        workflow.add_edge("result", END)
        workflow.add_edge("estimate_result", END)
        workflow.add_edge("multi_pass", END)
        return workflow.compile().invoke(state)
    except Exception as exc:
        if exc.__class__.__name__ not in {"ImportError", "ModuleNotFoundError"}:
            raise
        return _run_fallback_workflow(state)


def _run_fallback_workflow(state: ReviewState) -> ReviewState:
    state = _analyze_context(_discover_context(state))
    route = _route_after_analysis(state)
    if route == "estimate":
        return _build_estimate_result(state)
    state = _enhance_context(_select_strategy(state))
    if route == "multi_pass":
        return _run_multi_pass(state)
    return _build_result(_postprocess_response(_invoke_model(_build_prompt(state))))


def _discover_context(state: ReviewState) -> ReviewState:
    options = state["options"]
    config = state["config"]
    runtime = state["runtime"]
    started = datetime.now(timezone.utc)
    try:
        context = discover_project_context(
            target=options.target,
            project_root=config.project_root,
            include_tests=options.include_tests,
            include_project_docs=options.include_project_docs,
        )
    except Exception as exc:
        duration_ms = (datetime.now(timezone.utc) - started).total_seconds() * 1000
        runtime.emit(
            RunPhase.DISCOVERY,
            f"File discovery failed: {exc}",
            level=RunLevel.ERROR,
            metadata={"target": options.target, "remediation": "Verify the target path exists."},
            duration_ms=duration_ms,
        )
        raise
    if not context.files:
        message = f"No supported files found for review in {options.target}"
        runtime.emit(
            RunPhase.DISCOVERY,
            message,
            level=RunLevel.ERROR,
            metadata={
                "target": options.target,
                "remediation": (
                    "Use --include-tests or choose a directory with supported code files."
                ),
            },
        )
        raise ValueError(message)
    duration_ms = (datetime.now(timezone.utc) - started).total_seconds() * 1000
    runtime.emit(
        RunPhase.DISCOVERY,
        "Files discovered",
        metadata={
            "target": options.target,
            "fileCount": len(context.files),
            "docCount": len(context.docs),
            "language": context.detection.language,
            "framework": context.detection.framework,
        },
        duration_ms=duration_ms,
    )
    return {**state, "context": context}


def _analyze_context(state: ReviewState) -> ReviewState:
    options = state["options"]
    config = state["config"]
    context = state["context"]
    started = datetime.now(timezone.utc)
    token_analysis = analyze_files(
        context.files,
        TokenAnalysisOptions(
            review_type=options.review_type,
            model_name=config.selected_model,
            context_maintenance_factor=options.context_maintenance_factor,
            force_single_pass=options.force_single_pass,
            batch_token_limit=options.batch_token_limit,
        ),
    )
    semantic_result: SemanticChunkingResult | None = None
    if options.enable_semantic_chunking:
        semantic_result = analyze_semantic_chunks(
            context.files,
            review_type=options.review_type,
            model_name=config.selected_model,
            max_tokens_per_chunk=token_analysis.chunk_token_limit,
        )

    review_chunks = token_analysis.chunking_recommendation.recommended_chunks
    if (
        options.enable_semantic_chunking
        and semantic_result is not None
        and not semantic_result.fallback_used
        and semantic_result.chunks
    ):
        review_chunks = semantic_result.chunks

    duration_ms = (datetime.now(timezone.utc) - started).total_seconds() * 1000
    state["runtime"].emit(
        RunPhase.PROMPT,
        "Token and semantic context analyzed",
        metadata={
            "fileCount": token_analysis.file_count,
            "estimatedTokens": token_analysis.estimated_total_tokens,
            "chunks": len(review_chunks),
            "semantic": semantic_result.method if semantic_result else "disabled",
        },
        duration_ms=duration_ms,
    )
    next_state: ReviewState = {
        **state,
        "token_analysis": token_analysis,
        "review_chunks": review_chunks,
    }
    if semantic_result is not None:
        next_state["semantic_result"] = semantic_result
    return next_state


def _route_after_analysis(state: ReviewState) -> str:
    options = state["options"]
    if options.estimate:
        return "estimate"
    if options.force_single_pass:
        return "single_pass"
    recommendation = state["token_analysis"].chunking_recommendation
    if options.multi_pass or recommendation.chunking_recommended:
        return "multi_pass"
    return "single_pass"


def _select_strategy(state: ReviewState) -> ReviewState:
    options = state["options"]
    strategy = get_strategy(options.review_type, options=options)
    intent = strategy.describe_intent(options)
    return {**state, "strategy": strategy, "intent": intent}


def _enhance_context(state: ReviewState) -> ReviewState:
    started = datetime.now(timezone.utc)
    enhanced_context = state["strategy"].enhance_context(state["context"], state["options"])
    duration_ms = (datetime.now(timezone.utc) - started).total_seconds() * 1000
    state["runtime"].emit(
        RunPhase.PROMPT,
        "Context enhanced",
        metadata={
            "strategy": enhanced_context.metadata.get("strategy"),
            "sectionCount": len(enhanced_context.context_sections),
        },
        duration_ms=duration_ms,
    )
    return {**state, "enhanced_context": enhanced_context}


def _build_prompt(state: ReviewState) -> ReviewState:
    started = datetime.now(timezone.utc)
    memory_context = _recall_memory_context(state)
    dependency_context = _prepare_dependency_context(state)
    prompt_package = build_prompt_package(
        state["options"],
        state["context"],
        state["intent"],
        state["enhanced_context"],
        memory_context=memory_context,
        tool_context=_dependency_context_for_prompt(state["options"], dependency_context),
    )
    prompt = prompt_package.prompt
    duration_ms = (datetime.now(timezone.utc) - started).total_seconds() * 1000
    state["runtime"].emit(
        RunPhase.PROMPT,
        "Prompt prepared",
        metadata={"promptChars": len(prompt), "reviewType": state["options"].review_type},
        duration_ms=duration_ms,
    )
    return {
        **state,
        "prompt_package": prompt_package,
        "prompt": prompt,
        "memory_context": memory_context,
        "dependency_tool_context": dependency_context,
    }


def _invoke_model(state: ReviewState) -> ReviewState:
    started = datetime.now(timezone.utc)
    runtime = state["runtime"]
    config = state["config"]
    try:
        with get_observability().start_span(
            "orchestration.invoke_model",
            {"model": config.selected_model, "provider": config.provider},
        ):
            client = create_llm_client(config)
            dependency_context = state.get("dependency_tool_context")
            try:
                response = client.generate_review(
                    state["prompt"],
                    GenerationOptions(
                        on_chunk=runtime.stream_model_chunk,
                        metadata=state["prompt_package"].metadata,
                        tools=dependency_context.tool_schemas
                        if dependency_context and dependency_context.enabled
                        else [],
                        tool_executor=_execute_langchain_tool_call
                        if dependency_context and dependency_context.enabled
                        else None,
                    ),
                )
            finally:
                runtime.finish_model_stream()
    except Exception as exc:
        duration_ms = (datetime.now(timezone.utc) - started).total_seconds() * 1000
        runtime.emit(
            RunPhase.MODEL,
            f"Model step failed: {exc}",
            level=RunLevel.ERROR,
            metadata={
                "model": config.selected_model,
                "provider": config.provider,
                "remediation": "Check the selected model and provider API key.",
            },
            duration_ms=duration_ms,
        )
        raise
    _ensure_response_cost_metadata(response)
    duration_ms = (datetime.now(timezone.utc) - started).total_seconds() * 1000
    runtime.emit(
        RunPhase.MODEL,
        "Model invoked",
        metadata={
            "model": response.model,
            "provider": config.provider,
            "usage": response.usage.model_dump(exclude_none=True),
            "cost": response.metadata.get("cost"),
            "modelWarnings": response.metadata.get("modelWarnings", []),
            "resilience": response.metadata.get("resilience", {}),
        },
        duration_ms=duration_ms,
    )
    return {**state, "response": response}


def _postprocess_response(state: ReviewState) -> ReviewState:
    postprocessed = state["strategy"].postprocess_response(
        state["response"].content,
        state["context"],
        state["options"],
        state["enhanced_context"],
    )
    return {
        **state,
        "postprocessed_content": postprocessed.content,
        "postprocess_metadata": postprocessed.metadata,
    }


def _build_result(state: ReviewState) -> ReviewState:
    options = state["options"]
    config = state["config"]
    context = state["context"]
    response = state["response"]
    enhanced_context = state["enhanced_context"]
    prompt_package = state["prompt_package"]
    _learn_memory_from_content(state, state["postprocessed_content"])
    result = ReviewResult(
        content=state["postprocessed_content"],
        file_path=options.target,
        review_type=options.review_type,
        timestamp=datetime.now(timezone.utc).isoformat(),
        model_used=response.model,
        files=context.files,
        metadata={
            "projectName": context.project_name,
            "provider": config.provider,
            "model": response.model,
            "usage": response.usage.model_dump(exclude_none=True),
            "cost": response.metadata.get("cost"),
            "modelWarnings": response.metadata.get("modelWarnings", []),
            "fileCount": len(context.files),
            "docCount": len(context.docs),
            "language": options.language,
            "detectedLanguage": context.detection.language,
            "framework": options.framework,
            "detectedFramework": context.detection.framework,
            "detection": context.detection.model_dump(),
            "fileTree": context.file_tree,
            "discovery": context.discovery_metadata,
            "writerModel": options.writer_model,
            "interactive": options.interactive,
            "stdout": options.stdout,
            "strategy": enhanced_context.metadata.get("strategy"),
            "context_enhancers": [section.title for section in enhanced_context.context_sections],
            "prompt": prompt_package.metadata,
            "tokenAnalysis": _token_analysis_metadata(state.get("token_analysis")),
            "chunkPlan": _chunk_plan_metadata(state.get("review_chunks", [])),
            "semantic": _semantic_metadata(state.get("semantic_result")),
            "toolCalling": _tool_metadata(state.get("dependency_tool_context")),
            "memory": _memory_metadata(state),
            **state["postprocess_metadata"],
        },
    )
    return {**state, "result": result}


def _build_estimate_result(state: ReviewState) -> ReviewState:
    options = state["options"]
    config = state["config"]
    context = state["context"]
    token_analysis = state["token_analysis"]
    chunks = state["review_chunks"]
    semantic_result = state.get("semantic_result")
    content = _format_estimate_report(token_analysis, chunks, semantic_result)
    result = ReviewResult(
        content=content,
        file_path=options.target,
        review_type=options.review_type,
        timestamp=datetime.now(timezone.utc).isoformat(),
        model_used=config.selected_model,
        files=context.files,
        metadata={
            "estimateOnly": True,
            "projectName": context.project_name,
            "provider": config.provider,
            "model": config.selected_model,
            "fileCount": len(context.files),
            "docCount": len(context.docs),
            "language": options.language,
            "detectedLanguage": context.detection.language,
            "framework": options.framework,
            "detectedFramework": context.detection.framework,
            "detection": context.detection.model_dump(),
            "fileTree": context.file_tree,
            "discovery": context.discovery_metadata,
            "writerModel": options.writer_model,
            "interactive": options.interactive,
            "stdout": options.stdout,
            "tokenAnalysis": _token_analysis_metadata(token_analysis),
            "chunkPlan": _chunk_plan_metadata(chunks),
            "semantic": _semantic_metadata(semantic_result),
        },
    )
    return {**state, "result": result}


def _run_multi_pass(state: ReviewState) -> ReviewState:
    options = state["options"]
    config = state["config"]
    context = state["context"]
    runtime = state["runtime"]
    chunks = state.get("review_chunks", [])
    review_context = ReviewContext.create(context.project_name, options.review_type, context.files)
    pass_results: list[PassResult] = []
    pass_costs = []
    memory_context = _recall_memory_context(state)
    dependency_context = _prepare_dependency_context(state)
    client = create_llm_client(config)

    for chunk in chunks:
        pass_number = review_context.start_pass()
        chunk_files = _files_for_chunk(context.files, chunk)
        pass_context = review_context.generate_next_pass_context(
            [file.relative_path for file in chunk_files],
            max_context_tokens=2_000,
        )
        prompt_package = build_prompt_package(
            options,
            context,
            state["intent"],
            state["enhanced_context"],
            files_override=chunk_files,
            review_context=pass_context,
            memory_context=memory_context,
            tool_context=_dependency_context_for_prompt(options, dependency_context),
        )
        started = datetime.now(timezone.utc)
        try:
            response = client.generate_review(
                prompt_package.prompt,
                GenerationOptions(
                    on_chunk=runtime.stream_model_chunk,
                    metadata={
                        **prompt_package.metadata,
                        "pass_number": pass_number,
                        "chunk_files": chunk.files,
                    },
                    tools=dependency_context.tool_schemas if dependency_context.enabled else [],
                    tool_executor=_execute_langchain_tool_call
                    if dependency_context.enabled
                    else None,
                ),
            )
            runtime.finish_model_stream()
            review_context.update_from_review(response.content, chunk_files)
            cost_info = estimate_cost_from_usage(response.usage, response.model)
            if cost_info is not None:
                pass_costs.append(cost_info)
            pass_results.append(
                PassResult(
                    pass_number=pass_number,
                    files=[file.relative_path for file in chunk_files],
                    estimated_token_count=chunk.estimated_token_count,
                    content=response.content,
                    metadata={
                        "usage": response.usage.model_dump(exclude_none=True),
                        "model": response.model,
                        "cost": cost_info.to_metadata() if cost_info else None,
                        "modelWarnings": response.metadata.get("modelWarnings", []),
                        "resilience": response.metadata.get("resilience", {}),
                    },
                )
            )
        except Exception as exc:
            runtime.finish_model_stream()
            pass_results.append(
                PassResult(
                    pass_number=pass_number,
                    files=[file.relative_path for file in chunk_files],
                    estimated_token_count=chunk.estimated_token_count,
                    content=f"Pass {pass_number} failed: {exc}",
                    success=False,
                    error=str(exc),
                )
            )
        duration_ms = (datetime.now(timezone.utc) - started).total_seconds() * 1000
        runtime.emit(
            RunPhase.MODEL,
            f"Multi-pass review pass {pass_number} completed",
            metadata={
                "pass": pass_number,
                "files": len(chunk_files),
                "success": pass_results[-1].success,
            },
            duration_ms=duration_ms,
        )

    content, consolidation_metadata, consolidation_cost = _consolidate_pass_results(
        state,
        pass_results,
    )
    _learn_memory_from_content({**state, "pass_results": pass_results}, content)
    all_costs = [*pass_costs]
    if consolidation_cost is not None:
        all_costs.append(consolidation_cost)
    aggregate_cost = aggregate_costs(config.selected_model, all_costs)
    result = ReviewResult(
        content=content,
        file_path=options.target,
        review_type=options.review_type,
        timestamp=datetime.now(timezone.utc).isoformat(),
        model_used=config.selected_model,
        files=context.files,
        metadata={
            "projectName": context.project_name,
            "provider": config.provider,
            "model": config.selected_model,
            "usage": usage_from_cost(aggregate_cost),
            "cost": aggregate_cost.to_metadata() if aggregate_cost else None,
            "fileCount": len(context.files),
            "docCount": len(context.docs),
            "language": options.language,
            "detectedLanguage": context.detection.language,
            "framework": options.framework,
            "detectedFramework": context.detection.framework,
            "detection": context.detection.model_dump(),
            "fileTree": context.file_tree,
            "discovery": context.discovery_metadata,
            "writerModel": options.writer_model,
            "interactive": options.interactive,
            "stdout": options.stdout,
            "strategy": state["enhanced_context"].metadata.get("strategy"),
            "context_enhancers": [
                section.title for section in state["enhanced_context"].context_sections
            ],
            "tokenAnalysis": _token_analysis_metadata(state.get("token_analysis")),
            "chunkPlan": _chunk_plan_metadata(chunks),
            "semantic": _semantic_metadata(state.get("semantic_result")),
            "multiPass": {
                "totalPasses": len(pass_results),
                "passes": [item.model_dump() for item in pass_results],
                "chunkFiles": [item.files for item in pass_results],
                "consolidation": consolidation_metadata,
            },
            "toolCalling": _tool_metadata(dependency_context),
            "memory": {
                "enabled": options.use_memory,
                "contextInjected": bool(memory_context),
                "path": str(config.project_root / ".ai-code-review" / "memory.jsonl")
                if options.use_memory
                else None,
            },
        },
    )
    return {
        **state,
        "memory_context": memory_context,
        "dependency_tool_context": dependency_context,
        "pass_results": pass_results,
        "result": result,
    }


def _consolidate_pass_results(
    state: ReviewState,
    pass_results: list[PassResult],
) -> tuple[str, dict[str, Any], CostInfo | None]:
    """Create a final multi-pass report using a writer model when configured."""

    options = state["options"]
    config = state["config"]
    context = state["context"]
    successful = [item for item in pass_results if item.success and item.content.strip()]
    fallback_content = _format_multi_pass_report(options.review_type, pass_results)
    if not successful:
        return (
            fallback_content,
            {"mode": "deterministic", "model": None, "reason": "no_successful_passes"},
            None,
        )

    writer_model = options.writer_model
    if not writer_model:
        return (
            fallback_content,
            {"mode": "deterministic", "model": None, "reason": "writer_model_not_configured"},
            None,
        )

    writer_config = config.model_copy(update={"selected_model": writer_model})
    prompt = _build_consolidation_prompt(context.project_name, options.review_type, pass_results)
    try:
        response = create_llm_client(writer_config).generate_review(
            prompt,
            GenerationOptions(
                metadata={
                    "consolidation": True,
                    "pass_count": len(pass_results),
                    "chunk_files": [item.files for item in pass_results],
                }
            ),
        )
    except Exception as exc:
        return (
            fallback_content,
            {
                "mode": "deterministic",
                "model": writer_model,
                "reason": f"writer_failed: {exc}",
            },
            None,
        )

    content = response.content.strip()
    if not content:
        return (
            fallback_content,
            {"mode": "deterministic", "model": writer_model, "reason": "writer_returned_empty"},
            None,
        )
    cost = estimate_cost_from_usage(response.usage, response.model)
    return (
        content,
        {
            "mode": "writer",
            "model": response.model,
            "usage": response.usage.model_dump(exclude_none=True),
            "cost": cost.to_metadata() if cost else None,
        },
        cost,
    )


def _build_consolidation_prompt(
    project_name: str,
    review_type: str,
    pass_results: list[PassResult],
) -> str:
    lines = [
        "Consolidate the following multi-pass review results into one final report.",
        "",
        f"Project: {project_name}",
        f"Review type: {review_type}",
        f"Pass count: {len(pass_results)}",
        "",
        "Requirements:",
        "- Deduplicate repeated findings.",
        "- Preserve concrete file references.",
        "- Keep failed-pass notes separate from successful findings.",
        "- Return Markdown only.",
        "",
    ]
    for item in pass_results:
        status = "success" if item.success else f"failed: {item.error}"
        lines.extend(
            [
                f"## Pass {item.pass_number} ({status})",
                f"Files: {', '.join(item.files) or 'none'}",
                "",
                item.content,
                "",
            ]
        )
    return "\n".join(lines)


def _recall_memory_context(state: ReviewState) -> str:
    options = state["options"]
    if not options.use_memory:
        return ""
    config = state["config"]
    context = state["context"]
    store = FileMemoryStore(config.project_root / ".ai-code-review" / "memory.jsonl")
    entries = store.recall(
        f"{context.project_name} {options.review_type}",
        limit=5,
        project_root=str(config.project_root),
        review_type=options.review_type,
    )
    if not entries:
        return "No prior memory entries matched this project and review type."
    return "\n".join(f"- [{entry.category}] {entry.content}" for entry in entries)


def _learn_memory_from_content(state: ReviewState, content: str) -> None:
    options = state["options"]
    if not options.use_memory or not content.strip():
        return
    config = state["config"]
    context = state["context"]
    store = FileMemoryStore(config.project_root / ".ai-code-review" / "memory.jsonl")
    summary = content.strip()
    if len(summary) > 2_000:
        summary = f"{summary[:1997]}..."
    store.learn(
        MemoryEntry(
            category=options.review_type,
            content=summary,
            project_root=str(config.project_root),
            review_type=options.review_type,
            finding_metadata={
                "project": context.project_name,
                "file_count": len(context.files),
                "model": state.get("response").model if state.get("response") else None,
            },
            metadata={
                "project": context.project_name,
                "review_type": options.review_type,
            },
        )
    )


def _prepare_dependency_context(state: ReviewState) -> DependencyToolContext:
    options = state["options"]
    config = state["config"]
    return prepare_dependency_tool_context(
        config.project_root,
        review_type=options.review_type,
        include_dependency_analysis=options.include_dependency_analysis,
        provider=config.provider,
        model_name=config.selected_model,
    )


def _dependency_context_for_prompt(
    options: ReviewOptions,
    dependency_context: DependencyToolContext,
) -> str:
    should_include = options.include_dependency_analysis is True and options.review_type in {
        "architectural",
        "security",
    }
    if not should_include:
        return ""
    lines = [dependency_context.static_context]
    if dependency_context.skipped_reason:
        lines.append(f"Tool calling skipped: {dependency_context.skipped_reason}")
    elif dependency_context.enabled:
        lines.append("Dependency security tools are available for this review.")
    return "\n\n".join(line for line in lines if line)


def _execute_langchain_tool_call(call: Any) -> str:
    name = ""
    arguments: dict[str, Any] = {}
    if isinstance(call, dict):
        name = str(call.get("name") or call.get("tool") or "")
        raw_args = call.get("args") or call.get("arguments") or {}
        arguments = raw_args if isinstance(raw_args, dict) else {}
    else:
        name = str(getattr(call, "name", "") or getattr(call, "tool", ""))
        raw_args = getattr(call, "args", None) or getattr(call, "arguments", None) or {}
        arguments = raw_args if isinstance(raw_args, dict) else {}
    result = execute_tool_call(ToolCallSpec(name=name, arguments=arguments))
    return result.result


def _ensure_response_cost_metadata(response: LLMResponse) -> None:
    if "cost" in response.metadata:
        return
    cost_info = estimate_cost_from_usage(response.usage, response.model)
    if cost_info is not None:
        response.metadata["cost"] = cost_info.to_metadata()


def _files_for_chunk(files: list[DiscoveredFile], chunk: ReviewChunk) -> list[DiscoveredFile]:
    by_path = {file.relative_path: file for file in files}
    if chunk.review_units:
        chunk_files: list[DiscoveredFile] = []
        for unit in chunk.review_units:
            for relative_path in unit.files:
                original = by_path.get(relative_path)
                if not original:
                    continue
                line_range = (
                    unit.metadata.get("lineRange") if isinstance(unit.metadata, dict) else None
                )
                suffix = ""
                if isinstance(line_range, list) and len(line_range) == 2:
                    suffix = f":{line_range[0]}-{line_range[1]}"
                chunk_files.append(
                    DiscoveredFile(
                        path=original.path,
                        relative_path=f"{original.relative_path}{suffix}",
                        language=original.language,
                        content=unit.content or original.content,
                    )
                )
        if chunk_files:
            return chunk_files
    return [file for file in files if file.relative_path in set(chunk.files)]


def _token_analysis_metadata(token_analysis: TokenAnalysisResult | None) -> dict[str, Any]:
    if token_analysis is None:
        return {}
    return {
        "fileCount": token_analysis.file_count,
        "totalTokens": token_analysis.total_tokens,
        "totalSizeInBytes": token_analysis.total_size_in_bytes,
        "averageTokensPerByte": token_analysis.average_tokens_per_byte,
        "promptOverheadTokens": token_analysis.prompt_overhead_tokens,
        "estimatedTotalTokens": token_analysis.estimated_total_tokens,
        "contextWindowSize": token_analysis.context_window_size,
        "effectiveContextWindow": token_analysis.effective_context_window,
        "chunkTokenLimit": token_analysis.chunk_token_limit,
        "exceedsContextWindow": token_analysis.exceeds_context_window,
        "estimatedPassesNeeded": token_analysis.estimated_passes_needed,
        "chunkingRecommended": token_analysis.chunking_recommendation.chunking_recommended,
        "chunkingReason": token_analysis.chunking_recommendation.reason,
        "files": [
            {
                "path": file.path,
                "tokens": file.token_count,
                "sizeInBytes": file.size_in_bytes,
                "tokensPerByte": file.tokens_per_byte,
            }
            for file in token_analysis.files
        ],
    }


def _chunk_plan_metadata(chunks: list[ReviewChunk]) -> dict[str, Any]:
    return {
        "totalChunks": len(chunks),
        "chunks": [
            {
                "files": chunk.files,
                "estimatedTokenCount": chunk.estimated_token_count,
                "priority": chunk.priority,
                "oversized": chunk.oversized,
                "reviewUnits": [
                    {
                        "id": unit.id,
                        "kind": unit.kind,
                        "files": unit.files,
                        "estimatedTokens": unit.estimated_tokens,
                        "metadata": unit.metadata,
                    }
                    for unit in chunk.review_units
                ],
            }
            for chunk in chunks
        ],
    }


def _semantic_metadata(semantic_result: SemanticChunkingResult | None) -> dict[str, Any]:
    if semantic_result is None:
        return {"enabled": False}
    return {
        "enabled": True,
        "method": semantic_result.method,
        "fallbackUsed": semantic_result.fallback_used,
        "errors": semantic_result.errors,
        "summary": semantic_result.summary,
    }


def _tool_metadata(dependency_context: DependencyToolContext | None) -> dict[str, Any]:
    if dependency_context is None:
        return {"enabled": False}
    return {
        "enabled": dependency_context.enabled,
        "skippedReason": dependency_context.skipped_reason,
        "dependencyCount": len(dependency_context.dependencies),
        "tools": [schema.get("name") for schema in dependency_context.tool_schemas],
        "results": [result.model_dump() for result in dependency_context.tool_results],
    }


def _memory_metadata(state: ReviewState) -> dict[str, Any]:
    options = state["options"]
    config = state["config"]
    return {
        "enabled": options.use_memory,
        "contextInjected": bool(state.get("memory_context")),
        "reviewType": options.review_type,
        "projectRoot": str(config.project_root) if options.use_memory else None,
        "path": str(config.project_root / ".ai-code-review" / "memory.jsonl")
        if options.use_memory
        else None,
    }


def _format_estimate_report(
    token_analysis: TokenAnalysisResult,
    chunks: list[ReviewChunk],
    semantic_result: SemanticChunkingResult | None,
) -> str:
    lines = [
        "# Token Usage and Chunking Estimate",
        "",
        f"- Files analyzed: {token_analysis.file_count}",
        f"- Estimated code tokens: {token_analysis.total_tokens}",
        f"- Estimated total tokens: {token_analysis.estimated_total_tokens}",
        f"- Context window: {token_analysis.context_window_size}",
        f"- Effective context window: {token_analysis.effective_context_window}",
        f"- Chunk token limit: {token_analysis.chunk_token_limit}",
        f"- Chunking recommended: {token_analysis.chunking_recommendation.chunking_recommended}",
        f"- Recommendation reason: {token_analysis.chunking_recommendation.reason}",
        "",
        "## Chunk Plan",
        "",
    ]
    for chunk in chunks:
        lines.append(
            f"- Pass {chunk.priority}: {chunk.estimated_token_count} tokens, "
            f"{len(chunk.files)} files"
        )
        for file in chunk.files:
            lines.append(f"  - `{file}`")
    if semantic_result is not None:
        lines.extend(
            [
                "",
                "## Semantic Chunking",
                "",
                f"- Method: {semantic_result.method}",
                f"- Fallback used: {semantic_result.fallback_used}",
                f"- Summary: {semantic_result.summary}",
            ]
        )
    return "\n".join(lines)


def _format_multi_pass_report(review_type: str, pass_results: list[PassResult]) -> str:
    lines = [
        f"# Multi-Pass {review_type} Review Summary",
        "",
        f"Total passes: {len(pass_results)}",
        "",
    ]
    seen: set[str] = set()
    for pass_result in pass_results:
        lines.extend(
            [
                f"## Pass {pass_result.pass_number}",
                "",
                f"Files: {', '.join(pass_result.files) or 'none'}",
                "",
            ]
        )
        if not pass_result.success:
            lines.append(f"- Pass failed: {pass_result.error}")
        for line in pass_result.content.splitlines():
            normalized = line.strip().lower()
            if normalized and normalized in seen:
                continue
            if normalized:
                seen.add(normalized)
            lines.append(line)
        lines.append("")
    if any(not item.success for item in pass_results):
        lines.append(
            "Some passes failed; available findings were consolidated from successful passes."
        )
    return "\n".join(lines).strip()
