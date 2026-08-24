import { useState } from "react";

import { CaseGeneration, generateCases } from "./api";
import { CaseReviewPanel } from "./CaseReviewPanel";

export function CaseGenerationPanel({ projectId }: { projectId: number }) {
  const [designId, setDesignId] = useState(1);
  const [mappingId, setMappingId] = useState(1);
  const [generation, setGeneration] = useState<CaseGeneration | null>(null);
  const [error, setError] = useState("");

  const generate = async () => {
    try {
      setGeneration(await generateCases(projectId, designId, mappingId));
      setError("");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "候选测试用例生成失败");
    }
  };

  return <section className="panel" aria-label="候选测试用例生成">
    <h2>生成可追踪的候选测试用例</h2>
    <label>已确认测试设计编号
      <input type="number" min="1" value={designId} onChange={(event) => setDesignId(Number(event.target.value))} />
    </label>
    <label>已确认模板映射编号
      <input type="number" min="1" value={mappingId} onChange={(event) => setMappingId(Number(event.target.value))} />
    </label>
    <button onClick={() => void generate()}>生成候选测试用例</button>
    {error && <p role="alert" className="error">{error}</p>}
    {generation && <div>
      <p role="status">
        生成状态：{generation.status}；AI 运行编号：{generation.ai_run_id}；
        {generation.is_mock ? "Mock AI 运行" : "真实 AI 运行"}（{generation.ai_run_status}）
      </p>
      {generation.candidates.map((candidate) => <article key={candidate.id} className="case-card">
        <h3>{candidate.title}</h3>
        <p>目标：{candidate.objective}</p>
        <p>
          追踪：需求 {candidate.requirement_ids.join("、")}；范围 {candidate.scope_item_id}；
          风险 {candidate.risk_item_id}；{candidate.priority}
        </p>
        <p>步骤：{candidate.steps.map((step) => `${step.order}. ${step.action} → ${step.expected}`).join("；")}</p>
        <p>设计依据：{candidate.design_basis.map((basis) => basis.reason).join("；")}</p>
        {candidate.unexpressed_fields.length > 0 && <p role="note">模板未无损表达：{candidate.unexpressed_fields.join("、")}</p>}
      </article>)}
      {generation.candidates.length > 0 && <CaseReviewPanel
        projectId={projectId}
        generationId={generation.id}
        candidateIds={generation.candidates.map((candidate) => candidate.id)}
      />}
    </div>}
  </section>;
}
