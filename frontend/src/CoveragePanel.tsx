import { FormEvent, useState } from "react";

import { CoverageSummary, getCoverage } from "./api";

interface Props {
  projectId: number;
}

export function CoveragePanel({ projectId }: Props) {
  const [versionId, setVersionId] = useState("");
  const [designId, setDesignId] = useState("");
  const [reviewBatchId, setReviewBatchId] = useState("");
  const [executionBatchId, setExecutionBatchId] = useState("");
  const [coverage, setCoverage] = useState<CoverageSummary | null>(null);
  const [selectedMetric, setSelectedMetric] = useState("");
  const [error, setError] = useState("");

  const loadCoverage = async (event: FormEvent) => {
    event.preventDefault();
    try {
      setError("");
      const result = await getCoverage(
        projectId, Number(versionId), Number(designId), Number(reviewBatchId),
        executionBatchId ? Number(executionBatchId) : undefined,
      );
      setCoverage(result);
      setSelectedMetric(Object.keys(result.metrics)[0] ?? "");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "治理指标加载失败");
    }
  };

  const metric = coverage?.metrics[selectedMetric];
  return <section className="panel">
    <h2>治理指标与缺口</h2>
    <p className="muted">指标只统计已确认追踪关系；选择指标可展开未覆盖项、质量问题和执行证据。</p>
    <form className="project-form" onSubmit={loadCoverage}>
      <label>需求版本 ID<input value={versionId} onChange={(event) => setVersionId(event.target.value)} required /></label>
      <label>测试设计 ID<input value={designId} onChange={(event) => setDesignId(event.target.value)} required /></label>
      <label>
        用例评审批次 ID
        <input value={reviewBatchId} onChange={(event) => setReviewBatchId(event.target.value)} required />
      </label>
      <label>
        执行批次 ID（可选）
        <input value={executionBatchId} onChange={(event) => setExecutionBatchId(event.target.value)} />
      </label>
      <button type="submit">查看治理指标</button>
    </form>
    {error && <p role="alert" className="error">{error}</p>}
    {coverage && <div role="status">
      <label>展开指标<select value={selectedMetric} onChange={(event) => setSelectedMetric(event.target.value)}>
        {Object.entries(coverage.metrics).map(([key, item]) => (
          <option key={key} value={key}>{item.label} {item.percentage}%</option>
        ))}
      </select></label>
      {metric && <div>
        <p>{metric.label}：{metric.numerator}/{metric.denominator}（{metric.percentage}%）</p>
        <p>未覆盖项：{metric.uncovered_items.join("、") || "无"}</p>
        <p>高风险缺口：{metric.high_risk_gaps.join("、") || "无"}</p>
        <p>关联质量问题：{metric.quality_issues.map((issue) => `#${issue.id} ${issue.phenomenon}`).join("；") || "无"}</p>
        <p>执行证据：{metric.execution_evidence.map((item) => item.evidence_references.join("、")).join("；") || "无"}</p>
      </div>}
    </div>}
  </section>;
}
