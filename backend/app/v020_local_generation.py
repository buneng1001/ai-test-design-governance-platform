from hashlib import sha256


def local_analysis(context: dict) -> dict:
    rows = []
    for index, fragment in enumerate(context["fragments"], start=1):
        text = fragment["text"].strip()
        source = fragment["source_reference"]
        module = source.get("section") or source["filename"].rsplit(".", 1)[0]
        requirement_id = f"REL-{stable_suffix(f'{module}|{text}')[:8].upper()}"
        subject = _subject(text)
        directions = (
            ("功能测试", "正常", f"验证{subject}在有效条件下按需求完成并产生可观察结果。"),
            ("异常测试", "异常", f"验证{subject}在无效输入、依赖失败或状态冲突时可控处理并明确提示。"),
            ("功能测试", "边界", f"验证{subject}在阈值、空值、极值和临界状态下符合约束。"),
        )
        for test_type, direction, basis in directions:
            rows.append({
                "module": module[:80],
                "test_item": f"{subject}（{direction}）"[:200],
                "test_basis": basis,
                "source_reference_id": f"input-{index}",
                "test_type": test_type,
                "priority": "P1" if direction == "正常" else "P2",
                "related_requirement_id": requirement_id,
            })
    return {"rows": rows}


def local_suggestions(context: dict) -> dict:
    rows = context.get("analysis_rows", [])
    related = next((row for row in rows if row.get("selected")), rows[0] if rows else {})
    relation = related.get("id")
    subject = related.get("test_item", "当前需求范围")
    return {"suggestions": [{
        "suggestion_action": "add",
        "module": related.get("module", "未分类模块"),
        "test_item": f"{subject}的异常恢复与用户提示",
        "test_basis": "当前分析范围尚未明确异常后的恢复状态与用户可见提示。",
        "test_type": "异常测试",
        "priority": "P1",
        "related_requirement_id": related.get("related_requirement_id", relation or "REL-PENDING"),
        "related_analysis_row_id": relation,
    }]}


def local_review(context: dict) -> dict:
    labels = {
        "product_manager": ("add", "从业务价值与需求完整性检查用户可见结果是否明确。", "功能测试"),
        "project_manager": ("risk", "从依赖与交付可行性检查环境和时间约束。", "稳定性测试"),
        "test_manager": ("add", "从可测试性与覆盖角度补充异常和边界验证。", "异常测试"),
    }
    related = next(iter(context.get("analysis_rows", [])), {})
    reports = [{
        "role": role,
        "summary": labels[role][1],
        "strengths": ["当前需求点均保留了来源和关联需求 ID。"],
        "concerns": ["仍需由对应身份复核业务规则、依赖和验收口径。"],
    } for role in context.get("roles", [])]
    return {"reports": reports, "suggestions": [{
        "role": role,
        "suggestion_action": labels[role][0],
        "module": related.get("module", "整体需求"),
        "test_item": labels[role][1],
        "test_basis": f"{role} 身份基于当前需求范围的本地确定性检查。",
        "test_type": labels[role][2],
        "priority": "P1",
        "related_requirement_id": related.get("related_requirement_id", related.get("id", "REL-OVERALL")),
        "related_analysis_row_id": related.get("id"),
    } for role in context.get("roles", [])]}


def local_cases(context: dict) -> dict:
    candidates = []
    for row in context.get("selected_rows", []):
        objective = row["test_item"]
        candidates.append({
            "analysis_row_id": row["id"],
            "title": f"{objective} - 正常与可观察结果",
            "objective": objective,
            "preconditions": ["测试对象已部署并处于可执行该功能的初始状态"],
            "test_input": "使用需求范围中约定的有效输入",
            "steps": [
                {"order": 1, "action": "准备测试对象和输入", "expected": "测试对象进入可验证状态"},
                {"order": 2, "action": f"执行：{objective}", "expected": "系统产生与需求一致的可观察结果"},
            ],
            "overall_expectation": f"{objective}的行为、状态和用户提示符合已选需求来源。",
            "evidence_requirements": [],
            "design_basis": ["场景法", "需求来源追溯"],
            "priority": "P1",
            "attachment": "",
        })
    return {"candidates": candidates}


def stable_suffix(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()[:12]


def _subject(text: str) -> str:
    compact = " ".join(text.replace("\n", " ").split())
    return compact[:64] or "当前需求"
