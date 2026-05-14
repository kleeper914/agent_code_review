from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, TypedDict

from ..config import ResolvedConfig, resolve_config
from ..discovery import ProjectContext, discover_project_context

from . import models
from .prompts import build_review_prompt
from .reports import save_review_result
from .types import ReviewOptions, ReviewResult


class ReviewState(TypedDict, total=False):
    options: ReviewOptions
    config: ResolvedConfig
    context: ProjectContext
    prompt: str
    response: str
    result: ReviewResult


def run_review(options: ReviewOptions, config: ResolvedConfig | None = None) -> ReviewResult:
    resolved_config = config or resolve_config(
        cli_model=options.model,
        cli_output_dir=options.output_dir,
        cli_output_format=options.output,
        cli_api_keys=options.api_keys,
        debug=options.debug,
        skip_key_check=options.skip_key_check
    )

    state: ReviewState = {"options": options, "config": resolved_config}
    final_state = _run_langgraph_workflow(state)
    result = final_state["result"]
    output_path = save_review_result(result, resolved_config.output_dir, options.output)
    result.output_path = output_path
    result.metadata["outputPath"] = str(output_path)
    return result


def _run_langgraph_workflow(state: ReviewState) -> ReviewState:
    try:
        from langgraph.graph import START, END, StateGraph

        workflow = StateGraph(ReviewState)
        workflow.add_node("discover", _discover_context)
        workflow.add_node("prompt", _build_prompt)
        workflow.add_node("invoke", _invoke_model)
        workflow.add_node("result", _build_result)
        workflow.add_edge(START, "discover")
        workflow.add_edge("discover", "prompt")
        workflow.add_edge("prompt", "invoke")
        workflow.add_edge("invoke", "result")
        workflow.add_edge("result", END)
        return workflow.compile().invoke(state)
    except Exception as exc:
        if exc.__class__.__name__ not in {"ImportError", "ModuleNotFoundError"}:
            raise
        return _build_result(_invoke_model(_build_prompt(_discover_context(state))))


def _discover_context(state: ReviewState) -> ReviewState:
    options = state["options"]
    config = state["config"]
    context = discover_project_context(
        target=options.target,
        project_root=config.project_root,
        include_tests=options.include_tests,
        include_project_docs=options.include_project_docs
    )

    if not context.files:
        raise ValueError(f"No supported files found for review in {options.target}")
    return {**state, "context": context}

def _build_prompt(state: ReviewState) -> ReviewState:
    return {**state, "prompt": build_review_prompt(state["options"], state["context"])}

def _invoke_model(state: ReviewState) -> ReviewState:
    chat_model = models.create_chat_model(state["config"])
    message = chat_model.invoke(state["prompt"])
    content = getattr(message, "content", message)
    if isinstance(content, list):
        content = "\n".join(str(item) for item in content)
    return {**state, "response": str(content)}

def _build_result(state: ReviewState) -> ReviewState:
    options = state["options"]
    config = state["config"]
    context = state["context"]
    result = ReviewResult(
        content=state["response"],
        file_path=options.target,
        review_type=options.review_type,
        timestamp=datetime.now(timezone.utc).isoformat(),
        model_used=config.selected_model,
        files=context.files,
        metadata={
            "projectName": context.project_name,
            "provider": config.provider,
            "fileCount": len(context.files),
            "docCount": len(context.docs),
        },
    )
    return {**state, "result": result}