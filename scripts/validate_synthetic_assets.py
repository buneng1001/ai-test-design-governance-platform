from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "data/synthetic/smart-collector/asset-manifest.json"


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def validate() -> list[str]:
    # 校验实际字节，避免只相信人工填写的哈希。
    manifest = load_json(MANIFEST_PATH)
    errors: list[str] = []
    for entry in manifest["assets"]:
        path = ROOT / entry["path"]
        if not path.is_file():
            errors.append(f"缺少资产：{entry['path']}")
            continue
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != entry["sha256"]:
            errors.append(f"SHA-256 不一致：{entry['path']}")
    requirements = (ROOT / "data/synthetic/smart-collector/v1/requirements.md").read_text(
        encoding="utf-8"
    )
    requirement_count = sum(line.startswith("### REQ-V1-") for line in requirements.splitlines())
    if requirement_count not in range(30, 41):
        errors.append("V1 原子需求数量不在 30–40 条范围")
    with (ROOT / "data/synthetic/smart-collector/v1/case-template.csv").open(
        encoding="utf-8"
    ) as handle:
        cases = list(csv.DictReader(handle))
    if len(cases) not in range(80, 121):
        errors.append("模板测试用例数量不在 80–120 条范围")
    expected_decisions = {"优先自动化", "适合自动化", "条件满足后自动化", "保留人工执行"}
    if {case["automation_decision"] for case in cases} != expected_decisions:
        errors.append("模板未覆盖四种自动化决定")
    truth = load_json(ROOT / "data/synthetic/smart-collector/evaluation-truth/evaluation-truth.json")
    if len(truth["review_findings"]) not in range(10, 16):
        errors.append("评估真值的评审问题数量不符合范围")
    if len(truth["risks"]) not in range(15, 26):
        errors.append("评估真值的风险数量不符合范围")
    changes = load_json(ROOT / "data/synthetic/smart-collector/v2/changes.json")["changes"]
    if len(changes) not in range(8, 13):
        errors.append("V2 变化数量不在 8–12 条范围")
    if len([entry for entry in manifest["assets"] if entry["asset_type"] == "result_input"]) < 3:
        errors.append("结果输入少于三份")
    truth_entries = [entry for entry in manifest["assets"] if entry["asset_type"] == "evaluation_truth"]
    if len(truth_entries) != 1 or truth_entries[0]["model_context"] != "excluded":
        errors.append("评估真值未明确隔离于普通模型上下文")
    return errors


def main() -> int:
    errors = validate()
    if errors:
        for error in errors:
            print(error)
        return 1
    print("合成资产校验通过：规模、格式、自动化决定、结果输入和真值隔离均有效")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
