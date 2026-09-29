import { useState } from "react";

import { AIRunPanel } from "./AIRunPanel";
import { AssetProvenancePanel } from "./AssetProvenancePanel";
import { ChangeImpactPanel } from "./ChangeImpactPanel";
import { CoveragePanel } from "./CoveragePanel";
import { ExecutionBatchPanel } from "./ExecutionBatchPanel";
import { ExecutionResultPanel } from "./ExecutionResultPanel";
import { ReportsPanel } from "./ReportsPanel";
import { TaskPublicationPanel } from "./TaskPublicationPanel";
import { TemplateMappingPanel } from "./TemplateMappingPanel";

/**
 * 将历史治理能力保留在按需展开的工作区，避免它们成为五页签主流程的前置条件。
 */
export function AdvancedGovernancePanel({ projectId }: { projectId: number }) {
  const [opened, setOpened] = useState(false);

  return <details className="advanced-governance" onToggle={(event) => setOpened(event.currentTarget.open)}>
    <summary>高级治理与历史详情</summary>
    <p className="field-help">
      此处保留资产来源、AI 审计、执行批次、治理指标、变更影响和详细报告；它们均不阻塞五页签主流程。
    </p>
    {opened && <div className="advanced-governance-content">
      <AssetProvenancePanel projectId={projectId} />
      <AIRunPanel projectId={projectId} />
      <TemplateMappingPanel projectId={projectId} />
      <TaskPublicationPanel projectId={projectId} />
      <ExecutionBatchPanel projectId={projectId} />
      <ExecutionResultPanel projectId={projectId} />
      <CoveragePanel projectId={projectId} />
      <ChangeImpactPanel projectId={projectId} />
      <ReportsPanel projectId={projectId} />
    </div>}
  </details>;
}
