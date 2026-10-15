import json

from app.v020_contracts import TEST_TYPES


PROMPT_VERSIONS = {
    "analysis": {"direct": "requirement-analysis.direct.v2", "skill": "requirement-analysis.skill.v2"},
    "suggestions": {"direct": "coverage-suggestions.direct.v2", "skill": "coverage-suggestions.skill.v2"},
    "review": {"direct": "role-review.direct.v2", "skill": "role-review.skill.v2"},
    "cases": {"direct": "case-generation.direct.v2", "skill": "case-generation.skill.v2"},
}
SKILL_VERSIONS = {
    "analysis": "ai-test-design-requirement-analysis.v1",
    "suggestions": "ai-test-design-requirement-analysis.v1",
    "review": "role-review-prompts.v1",
    "cases": "ai-test-design-case-generation.v1",
}


def build_prompt(page: str, mode: str, context: dict) -> str:
    test_types = "、".join(TEST_TYPES)
    contract = {
        "analysis": (
            "返回 JSON：rows 数组，每项只包含 module、test_item、test_basis、source_reference_id、"
            "test_type、priority、related_requirement_id。模块是宽泛业务模块；测试项是可验证功能/需求点，"
            "须覆盖正常、异常、边界及适用专项方向。相同逻辑需求在不同测试目的下必须复用同一 related_requirement_id；"
            "该字段只是本次分析内的关联分组 ID，不是经人工确认后获得的稳定需求 ID。"
        ),
        "suggestions": (
            "返回 JSON：suggestions 数组，每项只包含 suggestion_action(add/remove/risk)、module、test_item、"
            "test_basis、test_type、priority、related_requirement_id、related_analysis_row_id。"
        ),
        "review": (
            "先返回 reports 数组，每个已选身份包含 role、summary、strengths、concerns；再返回 suggestions 数组，"
            "每项只包含 role、suggestion_action(add/remove/risk)、module、test_item、test_basis、test_type、"
            "priority、related_requirement_id、related_analysis_row_id。"
        ),
        "cases": (
            "返回 JSON：candidates 数组，每项包含 analysis_row_id、title、objective、preconditions、test_input、"
            "steps、overall_expectation、evidence_requirements、design_basis、priority、attachment。attachment 仅在"
            "确有需补充的截图、日志或文件时写明，否则为空字符串。"
        ),
    }[page]
    method = _skill_method(page) if mode == "skill" else _direct_method(page)
    return (
        f"提示版本：{PROMPT_VERSIONS[page][mode]}。{method}\n{contract}"
        f"test_type 只能从以下常见分类中选择：{test_types}。优先级只使用 P0、P1、P2、P3。"
        "只使用输入范围中的事实与 ID，只输出 JSON，不得补造来源或输出 API Key。\n"
        + json.dumps(context, ensure_ascii=False, separators=(",", ":"))
    )

def _direct_method(page: str) -> str:
    return {
        "analysis": "直接按宽泛模块识别测试项，结合正常、异常、边界和适用专项测试方向，记录依据与来源。",
        "suggestions": "直接检查当前分析与已选范围，发现遗漏覆盖。",
        "review": "按输入中指定的审核身份直接提出风险、遗漏、冲突或修改建议。",
        "cases": "直接为每个已选测试点生成可执行、可验证的候选测试用例。",
    }[page]


def _skill_method(page: str) -> str:
    if page == "analysis":
        return (
            "执行 ai-test-design-requirement-analysis：Step 00 建立材料基线；Step 01 识别功能；"
            "Step 02 提取规则与验收条件；Step 03 正常场景；Step 04 异常场景；Step 05 边界；"
            "Step 06 隐性风险与权限；Step 07 形成测试项和测试点；Step 08 覆盖自检。"
        )
    if page == "suggestions":
        return "执行需求分析 Skill 的 Step 03～08 覆盖补全语义，重点检查异常、边界、隐性风险与孤立项。"
    if page == "review":
        return "执行独立的 role-review-prompts.v1；角色审核不是需求分析或用例生成 Skill，也不具有审批权。"
    return (
        "执行 ai-test-design-case-generation，只接收当前已选 Step 07 测试点；按测试方法生成详细步骤与逐步预期，"
        "禁止重新引入未选择范围。"
    )
