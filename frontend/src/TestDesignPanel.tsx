import { useState } from "react";

import {
  addTestDimension,
  adjustTestRisk,
  confirmTestDesign,
  createTestDesign,
  decideAutomation,
  TestDesign,
} from "./api";

export function TestDesignPanel({ projectId }: { projectId: number }) {
  const [versionId, setVersionId] = useState(1);
  const [confirmerName, setConfirmerName] = useState("测试工程师");
  const [design, setDesign] = useState<TestDesign | null>(null);
  const [error, setError] = useState("");
  const [dimensionName, setDimensionName] = useState("");

  const create = async () => {
    try {
      setDesign(await createTestDesign(projectId, versionId));
      setError("");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "测试设计创建失败");
    }
  };

  const confirm = async () => {
    if (!design) return;
    try {
      setDesign(await confirmTestDesign(projectId, design.id, confirmerName));
      setError("");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "测试设计确认失败");
    }
  };

  const refresh = (request: Promise<TestDesign>) => {
    void request.then(setDesign).then(() => setError("")).catch((reason: unknown) => {
      setError(reason instanceof Error ? reason.message : "测试设计更新失败");
    });
  };

  return (
    <section className="panel">
      <h2>测试维度、范围、风险与自动化</h2>
      {!design && <>
        <label>已确认需求版本
          <input
            type="number"
            min="1"
            value={versionId}
            onChange={(event) => setVersionId(Number(event.target.value))}
          />
        </label>
        <button onClick={() => void create()}>生成测试设计候选</button>
      </>}
      {error && <p role="alert" className="error">{error}</p>}
      {design && <>
        <p>状态：{design.status === "confirmed" ? "设计已确认" : "等待测试工程师确认"}</p>
        <p>
          项目测试维度：{design.dimensions.filter((item) => item.status === "active").map((item) => item.name).join("、")}
        </p>
        {design.status === "draft" && <div>
          <label>新增项目测试维度
            <input value={dimensionName} onChange={(event) => setDimensionName(event.target.value)} />
          </label>
          <button onClick={() => {
            if (dimensionName.trim()) refresh(addTestDimension(projectId, design.id, dimensionName));
          }}>新增维度</button>
        </div>}
        <ul>
          {design.scope_items.map((scope) => {
            const risk = design.risks.find((item) => item.scope_item_id === scope.id);
            const automation = design.automation_candidates.find((item) => item.scope_item_id === scope.id);
            return <li key={scope.id}>
              {scope.title}；风险 {risk?.risk_level} / {risk?.priority}；自动化建议分 {automation?.suggested_score}
              {design.status === "draft" && risk && automation && <div>
                <button onClick={() => refresh(adjustTestRisk(projectId, design.id, scope.id, risk.factors))}>
                  确认风险因子
                </button>
                <button onClick={() => refresh(decideAutomation(
                  projectId, design.id, scope.id, automation.factors, "priority_automation",
                ))}>决定优先自动化</button>
              </div>}
            </li>;
          })}
        </ul>
        {design.status === "draft" && <form className="project-form" onSubmit={(event) => {
          event.preventDefault();
          void confirm();
        }}>
          <label>确认人名称<input value={confirmerName} onChange={(event) => setConfirmerName(event.target.value)} /></label>
          <button type="submit">确认测试设计</button>
        </form>}
      </>}
    </section>
  );
}
