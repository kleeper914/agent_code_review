"""Cost estimation helpers backed by the enhanced model registry."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .registry import ModelInfo, TieredPricing, get_model_info
from .types import TokenUsage


@dataclass(frozen=True)
class CostInfo:
    """Provider-neutral cost summary for one model invocation."""

    input_tokens: int
    output_tokens: int
    total_tokens: int
    estimated_cost: float
    formatted_cost: str
    pricing_source: str
    model: str
    input_cost: float
    output_cost: float
    per_pass_costs: list[dict[str, Any]] = field(default_factory=list)

    def to_metadata(self) -> dict[str, Any]:
        metadata = {
            "inputTokens": self.input_tokens,
            "outputTokens": self.output_tokens,
            "totalTokens": self.total_tokens,
            "estimatedCost": self.estimated_cost,
            "formattedCost": self.formatted_cost,
            "pricingSource": self.pricing_source,
            "model": self.model,
            "inputCost": self.input_cost,
            "outputCost": self.output_cost,
        }
        if self.per_pass_costs:
            metadata["perPassCosts"] = self.per_pass_costs
        return metadata


def estimate_cost_from_usage(usage: TokenUsage, model_key: str) -> CostInfo | None:
    input_tokens = usage.input_tokens
    output_tokens = usage.output_tokens
    if input_tokens is None or output_tokens is None:
        return None
    return calculate_model_cost(model_key, input_tokens=input_tokens, output_tokens=output_tokens)


def calculate_model_cost(
    model_key: str,
    *,
    input_tokens: int,
    output_tokens: int,
) -> CostInfo | None:
    model = get_model_info(model_key)
    if input_tokens < 0 or output_tokens < 0:
        raise ValueError("Token counts cannot be negative")

    if model.tiered_pricing:
        input_cost = _calculate_tiered_token_cost(input_tokens, model.tiered_pricing, "input")
        output_cost = _calculate_tiered_token_cost(output_tokens, model.tiered_pricing, "output")
        pricing_source = "tiered"
    elif (
        model.input_price_per_million is not None
        and model.output_price_per_million is not None
    ):
        input_cost = (input_tokens / 1_000_000) * model.input_price_per_million
        output_cost = (output_tokens / 1_000_000) * model.output_price_per_million
        pricing_source = "simple"
    else:
        return None

    total = input_cost + output_cost
    return CostInfo(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=input_tokens + output_tokens,
        estimated_cost=total,
        formatted_cost=format_cost(total),
        pricing_source=pricing_source,
        model=model.key,
        input_cost=input_cost,
        output_cost=output_cost,
    )


def aggregate_costs(model_key: str, costs: list[CostInfo]) -> CostInfo | None:
    if not costs:
        return None
    input_tokens = sum(cost.input_tokens for cost in costs)
    output_tokens = sum(cost.output_tokens for cost in costs)
    estimated_cost = sum(cost.estimated_cost for cost in costs)
    input_cost = sum(cost.input_cost for cost in costs)
    output_cost = sum(cost.output_cost for cost in costs)
    return CostInfo(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=input_tokens + output_tokens,
        estimated_cost=estimated_cost,
        formatted_cost=format_cost(estimated_cost),
        pricing_source="aggregate",
        model=model_key,
        input_cost=input_cost,
        output_cost=output_cost,
        per_pass_costs=[cost.to_metadata() for cost in costs],
    )


def usage_from_cost(cost: CostInfo | None) -> dict[str, int]:
    if cost is None:
        return {}
    return {
        "input_tokens": cost.input_tokens,
        "output_tokens": cost.output_tokens,
        "total_tokens": cost.total_tokens,
    }


def cost_for_response_metadata(
    model_key: str,
    usage: TokenUsage,
    existing_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    metadata = dict(existing_metadata or {})
    cost = estimate_cost_from_usage(usage, model_key)
    if cost is not None:
        metadata["cost"] = cost.to_metadata()
    return metadata


def format_cost(cost: float) -> str:
    if cost < 0.01:
        return f"${cost:.6f} USD"
    if cost < 1:
        return f"${cost:.4f} USD"
    return f"${cost:.2f} USD"


def _calculate_tiered_token_cost(
    tokens: int,
    tiers: tuple[TieredPricing, ...],
    token_type: str,
) -> float:
    sorted_tiers = sorted(tiers, key=lambda tier: tier.token_threshold)
    total = 0.0
    for index, tier in enumerate(sorted_tiers):
        tier_start = tier.token_threshold
        tier_end = (
            sorted_tiers[index + 1].token_threshold if index < len(sorted_tiers) - 1 else None
        )
        tier_tokens = _tokens_in_tier(tokens, tier_start, tier_end)
        if token_type == "input":
            price = tier.input_price_per_million
        else:
            price = tier.output_price_per_million
        total += (tier_tokens / 1_000_000) * price
    return total


def _tokens_in_tier(tokens: int, tier_start: int, tier_end: int | None) -> int:
    if tokens <= tier_start:
        return 0
    if tier_end is None:
        return tokens - tier_start
    return max(0, min(tokens, tier_end) - tier_start)


def model_pricing_available(model: ModelInfo) -> bool:
    return bool(model.tiered_pricing) or (
        model.input_price_per_million is not None
        and model.output_price_per_million is not None
    )
