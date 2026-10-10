from hashlib import sha256


def local_analysis(context: dict) -> dict:
    rows = []
    current_modules: dict[str, str] = {}
    for index, fragment in enumerate(context["fragments"], start=1):
        text = fragment["text"].lstrip("# ").strip()
        source = fragment["source_reference"]
        filename = source["filename"]
        if fragment.get("kind") == "heading":
            current_modules[filename] = text
        module = current_modules.get(filename, "未分类模块")
        rows.append({
            "module": module,
            "function_point": text[:40],
            "test_item": f"验证{text[:32]}",
            "test_point": _test_point(text),
            "source_reference_id": f"input-{index}",
            "ai_reason": "本地模式按来源片段确定性拆分；需要测试工程师复核语义。",
            "information_gap": "" if any(marker in text for marker in ("必须", "应当", "不得", "秒"))
            else "缺少明确、可量化的验收条件。",
            "status": "ready" if text else "needs_information",
        })
    return {"rows": rows}


def local_suggestions(context: dict) -> dict:
    rows = context.get("analysis_rows", [])
    related = next((row for row in rows if row.get("selected")), rows[0] if rows else {})
    relation = related.get("id")
    subject = related.get("test_point", "当前需求范围")
    return {"suggestions": [{
        "suggestion_type": "test_point",
        "priority": "medium",
        "content": f"补充验证“{subject}”对应的异常恢复与用户提示。",
        "related_analysis_row_id": relation,
        "ai_reason": "本地覆盖规则发现当前范围缺少明确的异常恢复检查。",
    }]}


def local_review(context: dict) -> dict:
    labels = {
        "product_manager": ("omission", "从业务价值与需求完整性检查用户可见结果是否明确。"),
        "project_manager": ("risk", "从依赖与交付可行性检查环境和时间约束。"),
        "test_manager": ("change", "从可测试性与覆盖角度补充异常和边界验证。"),
    }
    related = next(iter(context.get("analysis_rows", [])), {})
    return {"suggestions": [{
        "role": role,
        "finding_type": labels[role][0],
        "content": labels[role][1],
        "related_analysis_row_id": related.get("id"),
        "ai_reason": "本地角色规则基于当前分析范围给出确定性检查建议。",
    } for role in context.get("roles", [])]}


def local_cases(context: dict) -> dict:
    candidates = []
    for row in context.get("selected_rows", []):
        objective = row["test_point"]
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
            "evidence_requirements": ["保留关键操作、响应或界面截图", "记录最终状态与必要日志"],
            "design_basis": ["场景法", "需求来源追溯"],
            "priority": "P1",
        })
    return {"candidates": candidates}


def stable_suffix(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()[:12]


def _test_point(text: str) -> str:
    if any(marker in text for marker in ("必须", "应当", "不得")):
        return f"验证约束：{text[:72]}"
    return f"验证功能：{text[:72]}"
