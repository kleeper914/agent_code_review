from __future__ import annotations

from pydantic import BaseModel, Field

from typing import Any, Protocol

from ..discovery import ProjectContext
from ..orchestration.types import ReviewOptions, ReviewType


class ContextSection(BaseModel):
    """
    A named context block produced before prompt rendering.

    表示一个“上下文片段”。

    在真正构造 prompt 之前，系统会先生成若干上下文块，
    例如：
    - 项目基本信息
    - 依赖分析结果
    - ESLint 检查结果
    - AI 检测结果
    - 架构图说明

    每个上下文块都有标题、内容、来源和元数据。
    """

    title: str
    content: str
    source: str = "strategy"
    metadata: dict[str, Any] = Field(default_factory=dict)


class ReviewIntent(BaseModel):
    """
    Review-type-specific instructions without model or provider details.

    表示某种审查类型的“审查意图”。

    它只描述：
    - 要做什么类型的审查
    - 审查标题是什么
    - 应该重点关注什么
    - 输出应该长什么样

    注意：
    它不关心具体使用哪个模型，也不关心 provider 是 OpenAI、Anthropic 还是 Gemini。
    """

    review_type: ReviewType
    title: str
    instructions: str
    focus_areas: list[str] = Field(default_factory=list)
    output_expectations: list[str] = Field(default_factory=list)
    schema_name: str | None = None


class EnhancedReviewContext(BaseModel):
    """
    Context sections and metadata added by a review strategy.

    表示“增强后的审查上下文”。

    ProjectContext 是项目扫描得到的基础上下文，
    EnhancedReviewContext 是具体策略额外补充的上下文。

    例如：
    - security 策略可能补充依赖漏洞信息
    - performance 策略可能补充复杂度热点文件
    - unused-code 策略可能补充 ts-prune 扫描结果
    """

    context_sections: list[ContextSection] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    tooling: dict[str, Any] = Field(default_factory=dict)
    ai_detection: dict[str, Any] = Field(default_factory=dict)


class PostprocessResult(BaseModel):
    """
    Provider-neutral response post-processing result.

    表示模型回答后处理的结果。

    provider-neutral 表示它不依赖具体模型厂商。
    不管回答来自 OpenAI、Claude、Gemini，后处理结果都统一成这个结构。
    """

    content: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class ReviewStrategy(Protocol):
    """
    Strategy boundary used by orchestration.

    这是一个策略协议接口。

    orchestration 调度层不需要知道具体策略类是谁，
    只要求策略类满足这个接口即可。

    换句话说：
    只要一个类拥有 review_type、describe_intent、
    enhance_context、postprocess_response 这些属性和方法，
    它就可以被当成 ReviewStrategy 使用。
    """

    review_type: ReviewType

    def describe_intent(self, options: ReviewOptions) -> ReviewIntent:
        """
        Return the review intent and output expectations.
        """

    def enhance_context(
        self,
        context: ProjectContext,
        options: ReviewOptions,
    ) -> EnhancedReviewContext:
        """
        Return additional context for prompt construction.
        """

    def postprocess_response(
        self,
        content: str,
        context: ProjectContext,
        options: ReviewOptions,
        enhanced_context: EnhancedReviewContext
    ) -> PostprocessResult:
        """
        Normalize the model response without calling a model.
        """


class BaseReviewStrategy:

    review_type: ReviewType

    def __init__(self, review_type: ReviewType) -> None:
        self.review_type = review_type
    
    @property
    def strategy_name(self) -> str:
        return self.__class__.__name__

    def _base_metadata(self, **extra: Any) -> dict[str, Any]:
        return {
            "strategy": self.strategy_name,
            "review_type": self.review_type,
            **extra
        }
    
    def _project_summary_section(self, context: ProjectContext) -> ContextSection:
        languages = sorted({file.language for file in context.files})
        return ContextSection(
            title="Project context",
            content=(
                f"Project: {context.project_name}\n"
                f"Target: {context.target}\n"
                f"Files: {len(context.files)}\n"
                f"Languages: {', '.join(languages) if languages else 'unknown'}"
            ),
            source="common",
            metadata={"file_count": len(context.files), "languages": languages}
        )
    
    def postprocess_response(
        self,
        content: str,
        context: ProjectContext,
        options: ReviewOptions,
        enhanced_context: EnhancedReviewContext,
    ) -> PostprocessResult:
        return PostprocessResult(
            content=content,
            metadata={
                "parsed_schema": {
                    "reviewType": self.review_type,
                    "schema": self.describe_intent(options).schema_name,
                },
                "tooling": enhanced_context.tooling,
                "ai_detection": enhanced_context.ai_detection,
            },
        )