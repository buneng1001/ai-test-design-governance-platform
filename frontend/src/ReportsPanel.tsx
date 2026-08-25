import { useState } from "react";

import { getAuditPackage } from "./api";

interface ReportsPanelProps {
  projectId: number;
}

export function ReportsPanel({ projectId }: ReportsPanelProps) {
  const [auditStatus, setAuditStatus] = useState("未检查");

  const verifyAuditPackage = async () => {
    try {
      const report = await getAuditPackage(projectId);
      const mockRuns = (report.summary.ai_runs as Array<{ is_mock: boolean }>).filter((run) => run.is_mock);
      setAuditStatus(`审计包可用，Mock AI 运行 ${mockRuns.length} 条`);
    } catch {
      setAuditStatus("审计包读取失败");
    }
  };

  return (
    <section className="panel" aria-labelledby="reports-title">
      <p className="eyebrow">交付与验收</p>
      <h2 id="reports-title">报告与审计包</h2>
      <p className="muted">三类交付物独立生成；下载内容不包含密钥、完整 Prompt 或评估真值。</p>
      <div className="report-actions">
        <a className="button-link" href={`/api/projects/${projectId}/reports/test-design/download`}>下载测试设计报告</a>
        <a className="button-link" href={`/api/projects/${projectId}/reports/execution-governance/download`}>
          下载执行与治理报告
        </a>
        <a className="button-link" href={`/api/projects/${projectId}/reports/audit-package/download`}>下载审计包</a>
        <button type="button" onClick={() => void verifyAuditPackage()}>检查 Mock 与审计摘要</button>
      </div>
      <p role="status" className="muted">{auditStatus}</p>
    </section>
  );
}
