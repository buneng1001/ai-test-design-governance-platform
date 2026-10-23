def completed_events(mode: str) -> list[dict]:
    detail = "本地模式跳过外部模型调用，生成确定性结果。" if mode == "local" else "模型调用完成。"
    return [{"stage": stage, "status": "completed", "detail": detail if stage == "调用模型" else "已完成"}
            for stage in ("准备输入", "调用模型", "校验输出", "保存结果", "完成")]


def failed_events(mode: str, message: str) -> list[dict]:
    return [
        {"stage": "准备输入", "status": "completed", "detail": "已完成"},
        {"stage": "调用模型", "status": "failed", "detail": message if mode != "local" else "本地生成失败"},
        {"stage": "失败", "status": "failed", "detail": message},
    ]


def result_summary(page: str, items: list[dict]) -> dict:
    return {"count": len(items), "label": {
        "understanding": "资料理解块", "analysis": "需求分析项", "suggestions": "新增建议",
        "review": "审核建议", "cases": "候选用例",
    }[page]}


def next_step(page: str) -> str:
    return {
        "understanding": "检查资料理解结果，然后开始需求分析。",
        "analysis": "筛选并勾选将用于生成测试用例的范围。",
        "suggestions": "逐条接纳或拒绝建议；接纳项会回流需求分析表且默认不勾选。",
        "review": "逐条决定是否接纳，或直接进入测试用例。",
        "cases": "预览、编辑并选择纳入的候选用例，然后导出。",
    }[page]
