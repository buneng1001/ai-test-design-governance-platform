REQUIREMENT_TABLE_HEADERS = [
    "总序号", "模块", "测试项", "测试项依据", "测试项来源", "测试类型", "优先级", "关联需求ID",
]

DEFAULT_CASE_HEADERS = [
    "用例编号", "测试用例标题", "优先级", "预置条件", "输入", "操作步骤", "预期结果", "测试类型",
    "模块", "测试项", "附件", "软件版本",
]

TEST_TYPES = (
    "冒烟测试", "功能测试", "性能测试", "接口测试", "自动化测试", "安全性测试", "压力测试", "负载测试",
    "兼容性测试", "稳定性测试", "易用性测试", "异常测试", "边界测试", "回归测试", "蓝牙测试", "Wi-Fi测试", "IMU测试",
    "弱网测试", "功耗测试", "安装或升级测试", "文档测试", "APP测试", "WEB测试", "嵌入式测试", "硬件测试",
    "传感器或驱动测试", "云端服务测试",
)


def normalize_analysis_row(item: dict, index: int | None = None) -> dict:
    """兼容旧版分析结果，并给当前结果集补齐统一需求点表字段。"""
    row = dict(item)
    test_item = row.get("test_item") or row.get("test_point") or row.get("function_point") or row.get("content", "")
    row.update({
        "function_point": row.get("function_point") or test_item,
        "test_item": test_item,
        "test_point": row.get("test_point") or test_item,
        "test_basis": row.get("test_basis") or row.get("ai_reason", "历史结果未单列测试项依据"),
        "test_source": row.get("test_source") or row.get("source", "历史结果"),
        "test_type": row.get("test_type") if row.get("test_type") in TEST_TYPES else "功能测试",
        "priority": row.get("priority") if row.get("priority") in {"P0", "P1", "P2", "P3"} else "P2",
        "related_requirement_id": row.get("related_requirement_id") or row.get("source_reference_id") or row.get("id", ""),
        "total_index": index if index is not None else row.get("total_index"),
        "origin": row.get("origin", "analysis"),
        "mode": row.get("mode", "legacy"),
    })
    return row


def analysis_table_row(item: dict, index: int) -> dict:
    return {
        "total_index": index,
        "module": item.get("module", ""),
        "test_item": item.get("test_item", item.get("content", "")),
        "test_basis": item.get("test_basis", item.get("ai_reason", "")),
        "test_source": item.get("test_source", item.get("source", "")),
        "test_type": item.get("test_type", "功能测试"),
        "priority": item.get("priority", "P2"),
        "related_requirement_id": item.get("related_requirement_id", item.get("related_analysis_row_id") or ""),
    }
