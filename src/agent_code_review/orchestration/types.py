from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from ..discovery import DiscoveredFile

ReviewType = Literal[
    "quick-fixes",      # 快速修复，关注明显bug、代码异常、低成本优化
    "security",         # 安全审查，关注漏洞、敏感信息、注入风险等
    "architectural",    # 架构审查，关注模块划分、依赖关系、设计合理性
    "performance",      # 性能审查，关注耗时操作、重复计算、低效数据结构等
    "coding-test",      # 编程测试评估
    "unused-code"       # 未使用代码检查，关注死代码、未引用函数、未使用依赖等
]
OutputFormat = Literal["markdown", "json"]
AssessmentType = Literal["coding-challenge", "take-home", "live-coding", "code-review"]
DifficultyLevel = Literal["junior", "mid", "senior", "lead", "architect"]
ScoringSystem = Literal["numeric", "letter", "pass-fail", "custom"]
FeedbackLevel = Literal["basic", "detailed", "comprehensive"]


class ReviewOptions(BaseModel):
    """Normalized review options from the CLI."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    # 基础配置字段
    target: str = "."
    review_type: ReviewType = "quick-fixes"
    output: OutputFormat = "markdown"
    model: str | None = None
    output_dir: str | None = None
    language: str | None = None
    framework: str | None = None
    # 项目上下文控制字段
    include_tests: bool = False         # 是否将测试文件纳入上下文
    include_project_docs: bool = True   # 是否包含项目文档
    include_dependency_analysis: bool | None = None     # 是否进行依赖分析 True-强制开启 False-强制关闭 None-自动决定
    estimate: bool = False
    multi_pass: bool = False
    force_single_pass: bool = False
    context_maintenance_factor: float = 0.15
    batch_token_limit: int | None = None
    enable_semantic_chunking: bool = True
    diagram: bool = False           # 是否生成架构图或依赖图
    use_ts_prune: bool = False      # 是否使用ts-prune检查TypeScript项目的未使用导出，对TS项目的优化
    use_eslint: bool = False        # 是否使用ESLint做代码质量检查，对JS/TS项目优化
    trace_code: bool = False        # 是否进行代码追踪分析
    focused: bool = False           # 是否开启聚焦审查模式
    # homework/面试题/编程测试相关字段 - 主要用于"coding-test"场景
    assignment_file: str | None = None      # 编程任务说明文件路径
    assignment_url: str | None = None       # 编程任务说明的在线url
    assignment_text: str | None = None      # 直接传入的任务说明文本
    evaluation_template: str | None = None  # 评估报告的模版
    template_url: str | None = None         # 评估模版的在线url
    rubric_file: str | None = None          # 评分细则文件路径
    assessment_type: AssessmentType = "coding-challenge"    # 评估类型 "coding challenge"-普通算法题或编程挑战  "take-home"-homework型的项目型作业  "live-coding"-现场编程面试  "code-review"-代码审查型评估
    difficulty_level: DifficultyLevel = "mid"   # 难度等级
    time_limit: int | None = None           # 任务时间限制
    # 评分权重字段
    weight_correctness: int = 30            # "正确性"的评分权重
    weight_code_quality: int = 25           # "代码质量"的评分权重
    weight_architecture: int = 20           # "架构设计"的评分权重
    weight_performance: int = 15            # "性能"的评分权重
    weight_testing: int = 10                # "测试"的评分权重
    # 额外评估维度字段
    evaluate_documentation: bool = False    # 是否评估文档质量
    evaluate_git_history: bool = False      # 是否评估Git提交历史
    evaluate_edge_cases: bool = False       # 是否重点评估边界情况处理
    evaluate_error_handling: bool = False   # 是否评估错误处理能力
    # 评分系统字段
    scoring_system: ScoringSystem = "numeric"   # 评分方式  "numeric"-数字评分  "letter"-字母评分   "pass-fail"-通过/不通过    "custom"-自定义评分体系
    max_score: int = 100                    # 最高
    passing_threshold: int = 70             # 通过分数线
    score_breakdown: bool = True            # 是否输出分项得分
    # 反馈详细程度字段
    feedback_level: FeedbackLevel = "detailed"      # 反馈详细程度  "basic"-简要反馈，只给核心问题  "detailed"-详细反馈，指出问题和原因 "comprehensive"-综合反馈，包含问题、原因、影响、修改建议、示例等
    include_examples: bool = True           # 反馈中是否包含示例
    include_suggestions: bool = True        # 是否包含修改建议
    include_resources: bool = False         # 报告中是否包含学习资源
    # 限制条件字段
    allowed_libraries: list[str] = Field(default_factory=list)      # 允许使用的库列表
    forbidden_patterns: list[str] = Field(default_factory=list)     # 禁止出现的代码模式列表
    node_version: str | None = None         # 指定nodejs版本
    typescript_version: str | None = None   # 指定TypeScript版本
    memory_limit: int | None = None         # 表示内存限制
    execution_timeout: int | None = None    # 执行超时时间
    # AI生成检测相关字段
    enable_ai_detection: bool = False       # 是否启用AI生成检测
    ai_detection_threshold: float = 0.7     # AI检测阈值
    ai_detection_analyzers: list[str] = Field(default_factory=lambda: ["git", "documentation"])     # AI检测使用哪些分析器
    ai_detection_include_in_report: bool = True     # 是否把AI检测结果写入最终报告
    ai_detection_fail_on_detection: bool = False    # 检测到AI生成风险时是否直接判定失败
    # 运行行为控制字段
    use_memory: bool = False                # 是否使用记忆功能
    debug: bool = False                     # 是否开启调试功能
    verbose: bool = False                   # 是否开启详细日志输出
    quiet: bool = False                     # 是否开启安静模式，尽量减少控制台输出
    log_level: str | None = None            # 日志级别
    skip_key_check: bool = False            # 是否跳过API Key检查
    api_keys: dict[str, str] = Field(default_factory=dict)  # API Key字典


class ReviewResult(BaseModel):
    """Standard review result consumed by Markdown and JSON formatters."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    content: str
    file_path: str
    review_type: str
    timestamp: str
    model_used: str
    files: list[DiscoveredFile] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    output_path: Path | None = None


class PassResult(BaseModel):
    """
    One completed multi-pass review invocation.
    """

    pass_number: int
    files: list[str] = Field(default_factory=list)
    estimated_token_count: int = 0
    content: str = ""
    success: bool = True
    error: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)