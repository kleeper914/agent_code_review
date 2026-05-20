"""LangGraph-backed minimal review orchestration."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, TypedDict

from ..config import ResolvedConfig, resolve_config
from ..discovery import ProjectContext, discover_project_context
from ..llm_clients import GenerationOptions, LLMResponse, create_llm_client
from ..prompts import PromptPackage, build_prompt_package
from ..runtime import RunLevel, RunPhase, RuntimeContext, create_runtime
from ..strategies import EnhancedReviewContext, ReviewIntent, ReviewStrategy, get_strategy

from .reports import save_review_result
from .types import ReviewOptions, ReviewResult


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
    started = datetime.now(timezone.utc)
    output_path = save_review_result(result, resolved_config.output_dir, options.output)
    duration_ms = (datetime.now(timezone.utc) - started).total_seconds() * 1000
    result.output_path = output_path
    result.metadata["outputPath"] = str(output_path)
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
        workflow.add_node("select_strategy", _select_strategy)
        workflow.add_node("enhance_context", _enhance_context)
        workflow.add_node("prompt", _build_prompt)
        workflow.add_node("invoke", _invoke_model)
        workflow.add_node("postprocess", _postprocess_response)
        workflow.add_node("result", _build_result)
        workflow.add_edge(START, "discover")
        workflow.add_edge("discover", "select_strategy")
        workflow.add_edge("select_strategy", "enhance_context")
        workflow.add_edge("enhance_context", "prompt")
        workflow.add_edge("prompt", "invoke")
        workflow.add_edge("invoke", "postprocess")
        workflow.add_edge("postprocess", "result")
        workflow.add_edge("result", END)
        return workflow.compile().invoke(state)
    except Exception as exc:
        if exc.__class__.__name__ not in {"ImportError", "ModuleNotFoundError"}:
            raise
        return _build_result(
            _postprocess_response(
                _invoke_model(
                    _build_prompt(
                        _enhance_context(_select_strategy(_discover_context(state)))
                    )
                )
            )
        )


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
        },
        duration_ms=duration_ms,
    )
    return {**state, "context": context}


def _select_strategy(state: ReviewState) -> ReviewState:
    options = state["options"]
    strategy = get_strategy(options.review_type)
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
    prompt_package = build_prompt_package(
        state["options"],
        state["context"],
        state["intent"],
        state["enhanced_context"],
    )
    prompt = prompt_package.prompt
    duration_ms = (datetime.now(timezone.utc) - started).total_seconds() * 1000
    state["runtime"].emit(
        RunPhase.PROMPT,
        "Prompt prepared",
        metadata={"promptChars": len(prompt), "reviewType": state["options"].review_type},
        duration_ms=duration_ms,
    )
    return {**state, "prompt_package": prompt_package, "prompt": prompt}


def _invoke_model(state: ReviewState) -> ReviewState:
    started = datetime.now(timezone.utc)
    runtime = state["runtime"]
    config = state["config"]
    try:
        client = create_llm_client(config)
        try:
            response = client.generate_review(
                state["prompt"],
                GenerationOptions(
                    on_chunk=runtime.stream_model_chunk,
                    metadata=state["prompt_package"].metadata,
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
    duration_ms = (datetime.now(timezone.utc) - started).total_seconds() * 1000
    runtime.emit(
        RunPhase.MODEL,
        "Model invoked",
        metadata={
            "model": response.model,
            "provider": config.provider,
            "usage": response.usage.model_dump(exclude_none=True),
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
            "fileCount": len(context.files),
            "docCount": len(context.docs),
            "strategy": enhanced_context.metadata.get("strategy"),
            "context_enhancers": [
                section.title for section in enhanced_context.context_sections
            ],
            "prompt": prompt_package.metadata,
            **state["postprocess_metadata"],
        },
    )
    return {**state, "result": result}
