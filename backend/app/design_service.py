import hashlib

from app.design_schemas import AutomationFactors, AutomationCandidate, RiskFactor
from app.requirement_schemas import SourceReference


def stable_id(prefix: str, value: str) -> str:
    return f"{prefix}-{hashlib.sha256(value.encode('utf-8')).hexdigest()[:12]}"


def calculate_risk(factors: list[RiskFactor]) -> tuple[int, str]:
    total_weight = sum(factor.weight for factor in factors)
    weighted_score = sum(factor.score * factor.weight for factor in factors)
    score = round(weighted_score / total_weight * 20)
    level = "high" if score >= 70 else "medium" if score >= 40 else "low"
    return score, level


def priority_for(
    score: int, business_criticality: int, requirement_change_level: int = 0,
    historical_failure_count: int = 0,
) -> str:
    combined = score + business_criticality * 5 + requirement_change_level * 3 + historical_failure_count * 2
    return "P0" if combined >= 90 else "P1" if combined >= 70 else "P2" if combined >= 45 else "P3"


def calculate_automation(factors: AutomationFactors) -> int:
    positive = factors.regression_value + factors.determinism + factors.environment_control + factors.saving_benefit
    penalty = factors.maintenance_cost + factors.manual_observation
    # 原始范围为 -6 到 18，平移后归一化到 0 到 100，保证边界输入仍可解释。
    return round((positive - penalty + 6) / 24 * 100)


def automation_reason(factors: AutomationFactors) -> str:
    score = calculate_automation(factors)
    if factors.manual_observation >= 4:
        return f"自动化建议分 {score}：仍需较多人工观察，建议保留人工判断。"
    if factors.maintenance_cost >= 4:
        return f"自动化建议分 {score}：开发维护成本较高，需控制维护投入。"
    return f"自动化建议分 {score}：回归价值、判定确定性和环境可控性适合评估自动化。"


def source_refs_for_requirement(requirement_id: str, references: dict[str, SourceReference]) -> list[SourceReference]:
    reference = references.get(requirement_id)
    return [reference] if reference else []
